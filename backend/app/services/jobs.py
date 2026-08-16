"""In-process async job runner (Phase 17).

Turns a blocking ``generate_project_end_to_end`` call into a background
asyncio task. Job state is persisted in the ``jobs`` table so the
frontend can poll ``GET /api/jobs/{job_id}``.

This is deliberately simple: no Redis, no RQ, no Celery. It works for
a single uvicorn worker on one host, which is exactly what the local
MVP needs. When you outgrow that, replace ``kick_off_generate_job``
with an RQ enqueue; nothing else in the codebase changes because the
``progress_callback`` contract is already the right shape.

Caveats (documented, intentional):
* If the uvicorn process crashes mid-run, orphaned QUEUED / ANALYZING
  jobs will not resume — Phase 17-prod is where that gets fixed.
* Cancellation via ``POST /api/jobs/{id}/cancel`` flips the DB state
  but does NOT interrupt an in-flight subprocess (ffmpeg / whisper).
  The task will finish naturally; the frontend just stops polling.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict
from typing import cast

from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.settings import Settings
from backend.app.db.models import Job, JobStatus, Project
from backend.app.db.session import engine as sqlalchemy_engine
from backend.app.services.generate import (
    GenerationError,
    GenerationOutcome,
    GenerationStep,
    generate_project_end_to_end,
    stage_to_progress,
)
from models.image.base import ImageGenerationEngine
from models.llm.base import LLMEngine
from models.video.base import VideoGenerationEngine

log = logging.getLogger(__name__)


# Session factory used by background tasks. We deliberately do NOT reuse
# the FastAPI request-scoped session — background tasks outlive the
# request, and SQLAlchemy sessions aren't thread-safe across event loops.
_BackgroundSession = sessionmaker(
    bind=sqlalchemy_engine, autoflush=False, autocommit=False, future=True
)


def _stage_to_status(stage: str) -> JobStatus:
    """Map an in-progress stage to the coarse-grained Job state machine."""
    return {
        "transcribe":       JobStatus.ANALYZING,
        "analyze":          JobStatus.ANALYZING,
        "plan-scenes":      JobStatus.PLANNING,
        "generate-images":  JobStatus.GENERATING_IMAGES,
        "generate-videos":  JobStatus.GENERATING_VIDEO,
        "render":           JobStatus.COMPOSITING,
    }.get(stage, JobStatus.QUEUED)


def create_job(
    *, db: Session, project_id: str, kind: str, params: dict
) -> Job:
    """Persist a QUEUED job row and return it."""
    job = Job(
        project_id=project_id,
        kind=kind,
        status=JobStatus.QUEUED,
        progress=0.0,
        message="queued",
        result={"stages": [], "params": params},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


async def _run_generate_job(
    *,
    job_id: str,
    settings: Settings,
    params: dict,
    llm_engine: LLMEngine,
    image_engine: ImageGenerationEngine,
    video_engine: VideoGenerationEngine,
) -> None:
    """The actual background task body."""
    session = _BackgroundSession()
    try:
        job = session.get(Job, job_id)
        if job is None:
            log.error("background job %s vanished before start", job_id)
            return
        project = session.get(Project, job.project_id)
        if project is None:
            _mark_failed(session, job, "precheck", "project deleted")
            return

        start = time.monotonic()

        async def _on_step(step: GenerationStep) -> None:
            """Persist each stage as it completes."""
            # Re-fetch inside a fresh transaction so we're not surprised by
            # a session that pytest-teardown might have already closed.
            fresh = session.get(Job, job_id)
            if fresh is None:
                return
            if fresh.status == JobStatus.CANCELLED:
                # The user cancelled; note it and let the caller continue
                # (we can't actually stop ffmpeg from here — see module
                # docstring).
                return
            fresh.status = _stage_to_status(step.stage)
            fresh.message = f"{step.stage}: {step.status}"
            fresh.progress = stage_to_progress(step.stage)
            result = dict(fresh.result or {})
            stages = list(result.get("stages") or [])
            stages.append(asdict(step))
            result["stages"] = stages
            fresh.result = result
            session.commit()

        try:
            outcome: GenerationOutcome = await generate_project_end_to_end(
                db=session,
                settings=settings,
                project=project,
                llm_engine=llm_engine,
                image_engine=image_engine,
                video_engine=video_engine,
                run_transcription=bool(params.get("run_transcription", True)),
                target_scene_count=int(params.get("target_scene_count", 6)),
                style_preset_override=cast(
                    str | None, params.get("style_preset")
                ),
                burn_subtitles=bool(params.get("burn_subtitles", False)),
                fps=int(params.get("fps", 24)),
                xfade_seconds=float(params.get("xfade_seconds", 0.6)),
                subtitle_font_size=int(params.get("subtitle_font_size", 32)),
                subtitle_font_name=str(
                    params.get("subtitle_font_name") or "Noto Sans Devanagari"
                ),
                subtitle_alignment=int(params.get("subtitle_alignment", 2)),
                subtitle_margin_v=int(params.get("subtitle_margin_v", 60)),
                progress_callback=_on_step,
            )
        except GenerationError as exc:
            _mark_failed(session, job, exc.stage, exc.reason)
            return
        except Exception as exc:  # noqa: BLE001 - surface unexpected as failure
            log.exception("unexpected error in job %s", job_id)
            _mark_failed(session, job, "unknown", str(exc))
            return

        elapsed = time.monotonic() - start
        fresh = session.get(Job, job_id)
        if fresh is None:
            return
        result = dict(fresh.result or {})
        result["final"] = {
            "project_id": outcome.project_id,
            "final_asset_id": outcome.final_asset_id,
            "path": outcome.final_path,
            "url": _storage_url_from_settings(settings, outcome.final_path),
            "duration": outcome.duration,
            "width": outcome.width,
            "height": outcome.height,
            "fps": outcome.fps,
            "size_bytes": outcome.size_bytes,
            "subtitles_burned": outcome.subtitles_burned,
            "scene_count": outcome.scene_count,
        }
        result["elapsed_seconds"] = round(elapsed, 2)
        fresh.result = result
        fresh.status = JobStatus.COMPLETED
        fresh.progress = 1.0
        fresh.message = f"completed in {elapsed:.1f}s"
        session.commit()
        log.info("job %s completed in %.1fs", job_id, elapsed)
    finally:
        session.close()


def _mark_failed(
    session: Session, job: Job, stage: str, reason: str
) -> None:
    job.status = JobStatus.FAILED
    job.error = f"{stage}: {reason}"
    result = dict(job.result or {})
    result["failed_stage"] = stage
    result["failure_reason"] = reason
    job.result = result
    session.commit()


def _storage_url_from_settings(settings: Settings, absolute_path: str) -> str:
    """Duplicate of pipeline.py::_storage_url without the FastAPI dep.

    Keeps this module dependency-free of the routes package.
    """
    from pathlib import Path

    if not absolute_path:
        return ""
    try:
        root = settings.storage_root.resolve()
        p = Path(absolute_path).resolve()
    except (OSError, ValueError):
        return ""
    if not p.is_relative_to(root):
        return ""
    return "/storage/" + str(p.relative_to(root)).replace("\\", "/")


def kick_off_generate_job(
    *,
    db: Session,
    settings: Settings,
    project: Project,
    params: dict,
    llm_engine: LLMEngine,
    image_engine: ImageGenerationEngine,
    video_engine: VideoGenerationEngine,
) -> Job:
    """Create the Job row and schedule the background task.

    Engines are passed in by the caller (typically a FastAPI endpoint
    with ``Depends(get_llm_engine)`` etc.) so tests can override them
    via ``app.dependency_overrides`` the same way sync endpoints do.

    Returns the freshly-created Job (still ``QUEUED``).
    """
    job = create_job(
        db=db, project_id=project.id, kind="generate", params=params
    )
    loop = asyncio.get_event_loop()
    loop.create_task(
        _run_generate_job(
            job_id=job.id,
            settings=settings,
            params=params,
            llm_engine=llm_engine,
            image_engine=image_engine,
            video_engine=video_engine,
        )
    )
    return job
