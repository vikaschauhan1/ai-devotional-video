"""Video-generation orchestrator.

Iterates over the scenes for a project, calls the configured
``VideoGenerationEngine`` for each (feeding the scene's generated
image and desired duration), stores the resulting MP4s on disk,
updates ``Scene.video_path``, and creates a ``MediaAsset`` row per clip.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import AssetKind, MediaAsset, Project, Scene
from models.video.base import VideoGenerationEngine, VideoGenerationRequest

log = logging.getLogger(__name__)


_ASPECT_TO_SIZE: dict[str, tuple[int, int]] = {
    "9:16": (720, 1280),
    "16:9": (1280, 720),
    "1:1":  (1024, 1024),
}


class VideoGenerationServiceError(RuntimeError):
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


def _scene_duration(scene: Scene, min_seconds: float = 3.0) -> float:
    """Prefer scene.end - scene.start; clamp to sensible range."""
    span = float(scene.end) - float(scene.start)
    if span <= 0:
        return 6.0  # sane default when scene planner returned no timing
    return max(min_seconds, min(span, 20.0))


async def generate_project_videos(
    *,
    db: Session,
    settings: Settings,
    project: Project,
    engine: VideoGenerationEngine,
    force: bool = False,
    fps: int = 24,
) -> list[tuple[Scene, MediaAsset]]:
    """Generate one MP4 clip per scene for ``project``.

    Requires ``Scene.image_path`` to be present on every scene (i.e.
    ``/generate-images`` must have run first). Skips scenes that already
    have a ``video_path`` unless ``force`` is True.
    """
    scenes = (
        db.query(Scene)
        .filter(Scene.project_id == project.id)
        .order_by(Scene.index.asc())
        .all()
    )
    if not scenes:
        raise VideoGenerationServiceError(
            "no scenes to render — run /plan-scenes first"
        )

    missing = [s.index for s in scenes if not s.image_path]
    if missing:
        raise VideoGenerationServiceError(
            f"scenes {missing} have no image — run /generate-images first"
        )

    width, height = _pick_size(project)
    generated: list[tuple[Scene, MediaAsset]] = []

    for scene in scenes:
        if scene.video_path and not force:
            log.debug("scene %d already has video, skipping", scene.index)
            continue

        duration = _scene_duration(scene)
        req = VideoGenerationRequest(
            prompt=scene.prompt or "",
            duration=duration,
            image_path=scene.image_path,  # type: ignore[arg-type]
            negative_prompt=scene.negative_prompt,
            width=width,
            height=height,
            fps=fps,
            camera_hint=scene.camera or "",
            extras={
                "project_id": project.id,
                "scene_id": scene.index,
                "mood": scene.mood or "",
                "lighting": scene.lighting or "",
            },
        )
        result = await engine.generate(req)

        scene.video_path = str(result.path)
        asset = MediaAsset(
            project_id=project.id,
            kind=AssetKind.SCENE_VIDEO,
            path=str(result.path),
            original_filename=None,
            mime_type="video/mp4",
            size_bytes=result.path.stat().st_size,
            meta={
                "scene_index": scene.index,
                "engine": engine.name,
                "duration": result.duration,
                "fps": result.fps,
                **result.metadata,
            },
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        generated.append((scene, asset))

    return generated
