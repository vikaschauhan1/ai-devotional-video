"""End-to-end generation schemas (Phase 18/19)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GenerateRequest(BaseModel):
    run_transcription: bool = Field(
        default=True,
        description="Run faster-whisper if no transcript exists yet.",
    )
    target_scene_count: int = Field(default=6, ge=2, le=20)
    style_preset: str | None = Field(default=None, max_length=64)
    burn_subtitles: bool = False
    fps: int = Field(default=24, ge=12, le=60)
    xfade_seconds: float = Field(default=0.6, ge=0.0, le=3.0)


class GenerationStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: str
    status: str
    detail: str = ""


class GenerateResponse(BaseModel):
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
    progress: list[GenerationStepOut]
