"""Project request / response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AspectRatio = Literal["9:16", "16:9", "1:1"]


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    deity: str | None = Field(default=None, max_length=64)
    style: str | None = Field(default=None, max_length=64)
    language: str = Field(default="auto", max_length=16)
    aspect_ratio: AspectRatio = "9:16"
    resolution: str = Field(default="auto", max_length=16)
    lip_sync_enabled: bool = False
    lyrics: str | None = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    deity: str | None = None
    style: str | None = None
    language: str | None = None
    aspect_ratio: AspectRatio | None = None
    resolution: str | None = None
    lip_sync_enabled: bool | None = None
    lyrics: str | None = None


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime
