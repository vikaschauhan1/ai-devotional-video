"""Image-generation schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateImagesRequest(BaseModel):
    """Optional body for POST /projects/{id}/generate-images."""

    force: bool = Field(
        default=False,
        description="Re-render even scenes that already have an image_path.",
    )


class GeneratedImage(BaseModel):
    scene_index: int
    image_path: str
    size_bytes: int
    seed: int


class GenerateImagesResponse(BaseModel):
    project_id: str
    engine: str
    scenes_total: int
    scenes_generated: int
    images: list[GeneratedImage]
