"""Shared schema pieces."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Message(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    version: str
    engines: dict[str, str]


class JobStatusEnum(StrEnum):
    QUEUED = "QUEUED"
    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    GENERATING_IMAGES = "GENERATING_IMAGES"
    GENERATING_VIDEO = "GENERATING_VIDEO"
    LIP_SYNC = "LIP_SYNC"
    COMPOSITING = "COMPOSITING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
