"""Composite the final MP4 for a project."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import AssetKind, MediaAsset, Project, Scene
from pipeline.compositor import (
    ClipInput,
    CompositionResult,
    CompositorError,
    composite,
)

log = logging.getLogger(__name__)


_ASPECT_TO_SIZE: dict[str, tuple[int, int]] = {
    "9:16": (720, 1280),
    "16:9": (1280, 720),
    "1:1":  (1024, 1024),
}


class CompositeServiceError(RuntimeError):
    pass


def _pick_size(project: Project) -> tuple[int, int]:
    if project.resolution and project.resolution.lower() != "auto":
        parts = project.resolution.lower().split("x")
        if len(parts) == 2:
            try:
                return int(parts[0]), int(parts[1])
            except ValueError:
                log.warning("ignoring bad resolution %r", project.resolution)
    return _ASPECT_TO_SIZE.get(project.aspect_ratio, (720, 1280))


def _latest_audio(db: Session, project_id: str) -> MediaAsset | None:
    return (
        db.query(MediaAsset)
        .filter(
            MediaAsset.project_id == project_id,
            MediaAsset.kind == AssetKind.AUDIO,
        )
        .order_by(MediaAsset.created_at.desc())
        .first()
    )


def _latest_transcript_segments(db: Session, project_id: str) -> list[dict] | None:
    assets = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.project_id == project_id,
            MediaAsset.kind == AssetKind.TRANSCRIPT,
        )
        .order_by(MediaAsset.created_at.desc())
        .all()
    )
    for asset in assets:
        meta = asset.meta or {}
        # Ignore lyrics-analysis / scene-plan artefacts stored under the same kind.
        if meta.get("kind") in {"lyrics_analysis", "scene_plan"}:
            continue
        try:
            data = json.loads(Path(asset.path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        seg = data.get("segments") or []
        if isinstance(seg, list) and seg:
            return seg
    return None


def render_project_final(
    *,
    db: Session,
    settings: Settings,
    project: Project,
    burn_subtitles: bool,
    fps: int,
    xfade_seconds: float,
    subtitle_font_size: int = 32,
    subtitle_font_name: str = "Noto Sans Devanagari",
    subtitle_alignment: int = 2,
    subtitle_margin_v: int = 60,
) -> tuple[MediaAsset, CompositionResult]:
    """Composite all per-scene MP4s + audio into a final project video."""

    scenes = (
        db.query(Scene)
        .filter(Scene.project_id == project.id)
        .order_by(Scene.index.asc())
        .all()
    )
    if not scenes:
        raise CompositeServiceError("no scenes — run /plan-scenes first")

    missing_video = [s.index for s in scenes if not s.video_path]
    if missing_video:
        raise CompositeServiceError(
            f"scenes {missing_video} have no video — run /generate-videos first"
        )

    width, height = _pick_size(project)
    clips = [
        ClipInput(path=Path(str(s.video_path)), transition=(s.transition or "crossfade"))
        for s in scenes
    ]

    audio_asset = _latest_audio(db, project.id)
    audio_path = Path(audio_asset.path) if audio_asset else None

    subtitle_segments: list[dict] | None = None
    if burn_subtitles:
        subtitle_segments = _latest_transcript_segments(db, project.id)
        if subtitle_segments is None:
            log.info("no transcript available; skipping burned subtitles")

    dest_dir = (settings.storage_root / "final" / project.id).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"final-{uuid.uuid4().hex}.mp4"

    try:
        result = composite(
            clips=clips,
            audio_path=audio_path,
            output_path=dest,
            width=width,
            height=height,
            fps=fps,
            xfade_seconds=xfade_seconds,
            subtitle_segments=subtitle_segments,
            subtitle_font_size=subtitle_font_size,
            subtitle_font_name=subtitle_font_name,
            subtitle_alignment=subtitle_alignment,
            subtitle_margin_v=subtitle_margin_v,
        )
    except CompositorError as exc:
        raise CompositeServiceError(str(exc)) from exc

    asset = MediaAsset(
        project_id=project.id,
        kind=AssetKind.FINAL,
        path=str(result.path),
        original_filename=None,
        mime_type="video/mp4",
        size_bytes=result.path.stat().st_size,
        meta={
            "duration": result.duration,
            "width": result.width,
            "height": result.height,
            "fps": result.fps,
            "subtitles_burned": bool(subtitle_segments),
            "audio_asset_id": audio_asset.id if audio_asset else None,
            "scene_count": len(scenes),
        },
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset, result
