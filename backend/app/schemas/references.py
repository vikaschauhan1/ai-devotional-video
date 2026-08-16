"""Reference-image schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    path: str
    url: str = ""
    label: str | None = None
    original_filename: str | None
    mime_type: str | None
    size_bytes: int | None
    created_at: datetime
