"""Final-render schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RenderFinalRequest(BaseModel):
    burn_subtitles: bool = Field(
        default=False,
        description="Burn transcript segments as subtitles into the video.",
    )
    fps: int = Field(default=24, ge=12, le=60)
    xfade_seconds: float = Field(default=0.6, ge=0.0, le=3.0)


class RenderFinalResponse(BaseModel):
    project_id: str
    final_asset_id: str
    path: str
    duration: float
    width: int
    height: int
    fps: int
    size_bytes: int
    subtitles_burned: bool
    scene_count: int
