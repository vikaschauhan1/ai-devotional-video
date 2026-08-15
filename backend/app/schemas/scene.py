"""Scene schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SceneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    index: int
    start: float
    end: float
    lyrics: str | None = None
    prompt: str | None = None
    negative_prompt: str | None = None
    camera: str | None = None
    lighting: str | None = None
    mood: str | None = None
    transition: str | None = None
    image_path: str | None = None
    video_path: str | None = None
    created_at: datetime
