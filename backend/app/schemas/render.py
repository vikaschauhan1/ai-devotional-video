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
    subtitle_font_size: int = Field(default=32, ge=8, le=128)
    subtitle_font_name: str = Field(default="Noto Sans Devanagari", max_length=64)
    subtitle_alignment: int = Field(
        default=2, description="ASS alignment: 2 bottom-centre, 8 top-centre"
    )
    subtitle_margin_v: int = Field(default=60, ge=0, le=500)


class RenderFinalResponse(BaseModel):
    project_id: str
    final_asset_id: str
    path: str
    url: str = ""
    duration: float
    width: int
    height: int
    fps: int
    size_bytes: int
    subtitles_burned: bool
    scene_count: int
