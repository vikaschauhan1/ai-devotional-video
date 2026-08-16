"""End-to-end generation orchestrator (Phase 18/19).

Chains every real pipeline stage in a single blocking call:

  transcribe (optional) → analyze → plan-scenes → generate-images
  → generate-videos → render

Each stage records its outcome in the returned progress list so the
frontend can display a step-by-step timeline. Failures short-circuit
and surface as a domain error; the caller decides how to expose them
(the API turns them into 4xx / 5xx per the shared error convention).

Phase 17 wraps this in a background asyncio job (see
``backend/app/services/jobs.py``). The ``progress_callback`` argument
lets the job runner persist per-stage progress incrementally without
this module needing to know anything about the DB Job table.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import AssetKind, MediaAsset, Project
from backend.app.services.images import (
    ImageGenerationServiceError,
    generate_project_images,
)
from backend.app.services.lyrics import (
    LyricsAnalysisError,
    analyze_lyrics,
)
from backend.app.services.render import (
    CompositeServiceError,
    render_project_final,
)
from backend.app.services.scenes import (
    ScenePlanServiceError,
    plan_project_scenes,
)
from backend.app.services.transcription import transcribe_project
from backend.app.services.videos import (
    VideoGenerationServiceError,
    generate_project_videos,
)
from models.image.base import ImageGenerationEngine
from models.llm.base import LLMEngine
from models.video.base import VideoGenerationEngine
from pipeline.transcription import TranscriptionError

log = logging.getLogger(__name__)


class GenerationError(RuntimeError):
    """Raised when any stage of the end-to-end pipeline fails.

    Carries the failing ``stage`` name so the API layer can translate it
    into a useful error message without parsing strings.
    """

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"{stage}: {message}")
        self.stage = stage
        self.reason = message


@dataclass(slots=True)
class GenerationStep:
    stage: str
    status: str  # "ok" | "skipped" | "failed" | "running"
    detail: str = ""


@dataclass(slots=True)
class GenerationOutcome:
    project_id: str
    final_asset_id: str
    final_path: str
    duration: float
    width: int
    height: int
    fps: int
    size_bytes: int
    subtitles_burned: bool
    scene_count: int
    progress: list[GenerationStep] = field(default_factory=list)


# Order of pipeline stages — used to compute ``progress`` as a float.
_STAGES: tuple[str, ...] = (
    "transcribe",
    "analyze",
    "plan-scenes",
    "generate-images",
    "generate-videos",
    "render",
)


ProgressCallback = Callable[[GenerationStep], Awaitable[None]]


async def _report(cb: ProgressCallback | None, step: GenerationStep) -> None:
    if cb is None:
        return
    try:
        await cb(step)
    except Exception:  # noqa: BLE001 - progress errors must not kill the job
        log.exception("progress callback raised (non-fatal)")


def _has_audio(db: Session, project_id: str) -> bool:
    return (
        db.query(MediaAsset)
        .filter(
            MediaAsset.project_id == project_id,
            MediaAsset.kind == AssetKind.AUDIO,
        )
        .first()
        is not None
    )


def _has_transcript(db: Session, project_id: str) -> bool:
    """Real ASR transcripts store no ``meta.kind``; lyrics analyses and
    scene plans do. This function distinguishes them.
    """
    assets = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.project_id == project_id,
            MediaAsset.kind == AssetKind.TRANSCRIPT,
        )
        .all()
    )
    return any((a.meta or {}).get("kind") is None for a in assets)


async def generate_project_end_to_end(
    *,
    db: Session,
    settings: Settings,
    project: Project,
    llm_engine: LLMEngine,
    image_engine: ImageGenerationEngine,
    video_engine: VideoGenerationEngine,
    run_transcription: bool,
    target_scene_count: int,
    style_preset_override: str | None,
    burn_subtitles: bool,
    fps: int,
    xfade_seconds: float,
    subtitle_font_size: int = 32,
    subtitle_font_name: str = "Noto Sans Devanagari",
    subtitle_alignment: int = 2,
    subtitle_margin_v: int = 60,
    progress_callback: ProgressCallback | None = None,
) -> GenerationOutcome:
    """Run every pipeline stage. Raises ``GenerationError`` on the first failure.

    ``progress_callback`` is invoked after each stage completes with the
    ``GenerationStep`` that summarises that stage. Errors raised from the
    callback are logged but never propagated to the caller.
    """
    progress: list[GenerationStep] = []

    async def _log_step(step: GenerationStep) -> None:
        progress.append(step)
        await _report(progress_callback, step)

    if not _has_audio(db, project.id):
        raise GenerationError(
            "precheck", "no audio uploaded — POST /audio first"
        )
    if not (project.lyrics and project.lyrics.strip()):
        raise GenerationError(
            "precheck", "no lyrics uploaded — POST /lyrics first"
        )

    # ── 1. Transcribe ───────────────────────────────────────
    if run_transcription and not _has_transcript(db, project.id):
        try:
            transcribe_project(
                db=db,
                settings=settings,
                project=project,
                language=None,
                beam_size=5,
                vad_filter=True,
            )
            await _log_step(GenerationStep("transcribe", "ok"))
        except TranscriptionError as exc:
            log.warning("transcription skipped: %s", exc)
            await _log_step(
                GenerationStep("transcribe", "skipped", str(exc))
            )
    else:
        await _log_step(
            GenerationStep(
                "transcribe",
                "skipped",
                "not requested"
                if not run_transcription
                else "already present",
            )
        )

    # ── 2. Lyrics analysis ──────────────────────────────────
    try:
        analysis, _ = await analyze_lyrics(
            db=db, settings=settings, project=project, engine=llm_engine
        )
        await _log_step(
            GenerationStep(
                "analyze",
                "ok",
                f"language={analysis.language}, sections={len(analysis.sections)}",
            )
        )
    except LyricsAnalysisError as exc:
        raise GenerationError("analyze", str(exc)) from exc

    # ── 3. Scene plan ───────────────────────────────────────
    try:
        plan, _, _ = await plan_project_scenes(
            db=db,
            settings=settings,
            project=project,
            engine=llm_engine,
            style_preset_override=style_preset_override,
            target_scene_count=target_scene_count,
            reference_hints=None,
        )
        await _log_step(
            GenerationStep(
                "plan-scenes",
                "ok",
                f"style={plan.style_preset}, scenes={len(plan.scenes)}",
            )
        )
    except ScenePlanServiceError as exc:
        raise GenerationError("plan-scenes", str(exc)) from exc

    # ── 4. Images ───────────────────────────────────────────
    try:
        pairs_img = await generate_project_images(
            db=db,
            settings=settings,
            project=project,
            engine=image_engine,
            force=True,
        )
        await _log_step(
            GenerationStep(
                "generate-images",
                "ok",
                f"generated {len(pairs_img)} image(s)",
            )
        )
    except ImageGenerationServiceError as exc:
        raise GenerationError("generate-images", str(exc)) from exc

    # ── 5. Videos ───────────────────────────────────────────
    try:
        pairs_vid = await generate_project_videos(
            db=db,
            settings=settings,
            project=project,
            engine=video_engine,
            force=True,
            fps=fps,
        )
        await _log_step(
            GenerationStep(
                "generate-videos",
                "ok",
                f"generated {len(pairs_vid)} clip(s)",
            )
        )
    except VideoGenerationServiceError as exc:
        raise GenerationError("generate-videos", str(exc)) from exc

    # ── 6. Composite ────────────────────────────────────────
    try:
        asset, result = render_project_final(
            db=db,
            settings=settings,
            project=project,
            burn_subtitles=burn_subtitles,
            fps=fps,
            xfade_seconds=xfade_seconds,
            subtitle_font_size=subtitle_font_size,
            subtitle_font_name=subtitle_font_name,
            subtitle_alignment=subtitle_alignment,
            subtitle_margin_v=subtitle_margin_v,
        )
        await _log_step(
            GenerationStep(
                "render",
                "ok",
                f"{result.duration:.1f}s @ {result.width}x{result.height}",
            )
        )
    except CompositeServiceError as exc:
        raise GenerationError("render", str(exc)) from exc

    meta = asset.meta or {}
    return GenerationOutcome(
        project_id=project.id,
        final_asset_id=asset.id,
        final_path=asset.path,
        duration=float(result.duration),
        width=int(result.width),
        height=int(result.height),
        fps=int(result.fps),
        size_bytes=asset.size_bytes or 0,
        subtitles_burned=bool(meta.get("subtitles_burned")),
        scene_count=int(meta.get("scene_count", 0)),
        progress=progress,
    )


def stage_to_progress(stage: str) -> float:
    """Rough 0..1 progress for a given stage name (frontend cosmetic)."""
    try:
        idx = _STAGES.index(stage)
    except ValueError:
        return 0.0
    return (idx + 1) / len(_STAGES)
