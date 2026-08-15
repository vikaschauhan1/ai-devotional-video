"""Job schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.app.schemas.common import JobStatusEnum


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    kind: str
    status: JobStatusEnum
    progress: float
    message: str | None = None
    error: str | None = None
    result: dict | None = None
    created_at: datetime
    updated_at: datetime
