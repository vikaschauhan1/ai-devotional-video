"""Image-generation orchestrator.

Iterates over the scenes for a project, calls the configured
``ImageGenerationEngine`` for each, stores the resulting PNGs on disk,
updates ``Scene.image_path``, and creates a ``MediaAsset`` row per image.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import AssetKind, MediaAsset, Project, Scene
from models.image.base import ImageGenerationEngine, ImageGenerationRequest

log = logging.getLogger(__name__)

_ASPECT_TO_SIZE: dict[str, tuple[int, int]] = {
    "9:16": (720, 1280),
    "16:9": (1280, 720),
    "1:1":  (1024, 1024),
}


class ImageGenerationServiceError(RuntimeError):
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


async def generate_project_images(
    *,
    db: Session,
    settings: Settings,
    project: Project,
    engine: ImageGenerationEngine,
    force: bool = False,
) -> list[tuple[Scene, MediaAsset]]:
    """Generate one image per scene for ``project``.

    Skips scenes that already have an ``image_path`` unless ``force`` is
    True. Returns the list of ``(scene, asset)`` pairs newly generated.
    """
    scenes = (
        db.query(Scene)
        .filter(Scene.project_id == project.id)
        .order_by(Scene.index.asc())
        .all()
    )
    if not scenes:
        raise ImageGenerationServiceError(
            "no scenes to render — run /plan-scenes first"
        )

    width, height = _pick_size(project)
    style_preset = project.style or ""
    generated: list[tuple[Scene, MediaAsset]] = []

    for scene in scenes:
        if scene.image_path and not force:
            log.debug("scene %d already has image, skipping", scene.index)
            continue

        request = ImageGenerationRequest(
            prompt=scene.prompt or "cinematic devotional scene",
            negative_prompt=scene.negative_prompt,
            width=width,
            height=height,
            extras={
                "project_id": project.id,
                "scene_id": scene.index,
                "mood": scene.mood or "devotional",
                "style_preset": style_preset,
                "camera": scene.camera or "",
                "lighting": scene.lighting or "",
            },
        )
        result = await engine.generate(request)

        scene.image_path = str(result.path)
        asset = MediaAsset(
            project_id=project.id,
            kind=AssetKind.SCENE_IMAGE,
            path=str(result.path),
            original_filename=None,
            mime_type="image/png",
            size_bytes=result.path.stat().st_size,
            meta={
                "scene_index": scene.index,
                "engine": engine.name,
                "seed": result.seed,
                **result.metadata,
            },
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        generated.append((scene, asset))

    return generated
