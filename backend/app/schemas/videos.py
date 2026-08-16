"""Video-generation schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateVideosRequest(BaseModel):
    force: bool = Field(
        default=False,
        description="Re-render even scenes that already have a video_path.",
    )
    fps: int = Field(default=24, ge=12, le=60)


class GeneratedVideo(BaseModel):
    scene_index: int
    video_path: str
    duration: float
    fps: int
    size_bytes: int


class GenerateVideosResponse(BaseModel):
    project_id: str
    engine: str
    scenes_total: int
    scenes_generated: int
    videos: list[GeneratedVideo]
