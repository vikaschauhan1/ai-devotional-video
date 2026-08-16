"""Scene-plan service: pulls context, calls the agent, persists results."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from agent.prompts import resolve_style_preset
from agent.scenes import ScenePlanningError, plan_scenes
from backend.app.core.settings import Settings
from backend.app.db.models import AssetKind, MediaAsset, Project, Scene
from backend.app.schemas.scenes import ScenePlan
from models.llm.base import LLMEngine

log = logging.getLogger(__name__)


class ScenePlanServiceError(RuntimeError):
    pass


def _load_latest_lyrics_analysis(
    db: Session, project_id: str
) -> tuple[MediaAsset, dict] | None:
    """Return the most recent lyrics-analysis asset + parsed dict."""
    q = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.project_id == project_id,
            MediaAsset.kind == AssetKind.TRANSCRIPT,
        )
        .order_by(MediaAsset.created_at.desc())
        .all()
    )
    for asset in q:
        if (asset.meta or {}).get("kind") != "lyrics_analysis":
            continue
        try:
            data = json.loads(Path(asset.path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("skipping unreadable lyrics-analysis asset: %s", asset.path)
            continue
        return asset, data
    return None


def _latest_audio_duration(db: Session, project_id: str) -> float | None:
    latest = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.project_id == project_id,
            MediaAsset.kind == AssetKind.AUDIO,
        )
        .order_by(MediaAsset.created_at.desc())
        .first()
    )
    if latest is None:
        return None
    dur = (latest.meta or {}).get("duration")
    return float(dur) if isinstance(dur, int | float) else None


def _clear_existing_scenes(db: Session, project_id: str) -> int:
    n = (
        db.query(Scene)
        .filter(Scene.project_id == project_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return n


async def plan_project_scenes(
    *,
    db: Session,
    settings: Settings,
    project: Project,
    engine: LLMEngine,
    style_preset_override: str | None,
    target_scene_count: int,
    reference_hints: list[str] | None,
) -> tuple[ScenePlan, MediaAsset, int]:
    """Run scene planning and persist the result.

    Returns ``(plan, plan_asset, existing_scenes_replaced_count)``.
    """
    hit = _load_latest_lyrics_analysis(db, project.id)
    if hit is None:
        raise ScenePlanServiceError(
            "no lyrics analysis found for this project — run /analyze first"
        )
    analysis_asset, analysis = hit

    preset = resolve_style_preset(
        style_preset_override or project.style,
        project.deity,
    )
    audio_duration = _latest_audio_duration(db, project.id)

    try:
        plan = await plan_scenes(
            engine=engine,
            lyrics_analysis=analysis,
            audio_duration=audio_duration,
            preset=preset,
            aspect_ratio=project.aspect_ratio,
            target_scene_count=target_scene_count,
            reference_hints=reference_hints,
        )
    except ScenePlanningError as exc:
        raise ScenePlanServiceError(str(exc)) from exc

    # Replace any earlier scene rows for this project so re-planning
    # keeps the DB coherent with the latest plan.
    replaced = _clear_existing_scenes(db, project.id)
    for s in plan.scenes:
        db.add(
            Scene(
                project_id=project.id,
                index=s.scene_id,
                start=s.start,
                end=s.end,
                lyrics=s.lyrics,
                prompt=s.prompt,
                negative_prompt=s.negative_prompt,
                camera=s.camera,
                lighting=s.lighting,
                mood=s.mood,
                transition=s.transition,
            )
        )
    db.commit()

    # Persist the plan JSON next to the lyrics analysis.
    dest_dir = (settings.storage_root / "scenes" / project.id).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"scene-plan-{uuid.uuid4().hex}.json"
    dest.write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    plan_asset = MediaAsset(
        project_id=project.id,
        kind=AssetKind.TRANSCRIPT,  # no dedicated bucket yet; distinguished via meta.kind
        path=str(dest),
        original_filename=None,
        mime_type="application/json",
        size_bytes=dest.stat().st_size,
        meta={
            "kind": "scene_plan",
            "engine": engine.name,
            "style_preset": plan.style_preset,
            "scene_count": len(plan.scenes),
            "source_analysis_asset_id": analysis_asset.id,
        },
    )
    db.add(plan_asset)
    db.commit()
    db.refresh(plan_asset)
    return plan, plan_asset, replaced
