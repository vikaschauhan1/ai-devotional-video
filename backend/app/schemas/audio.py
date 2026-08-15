"""Audio-upload response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AudioMetadataOut(BaseModel):
    duration: float
    sample_rate: int
    channels: int
    codec: str
    bitrate: int | None = None
    format_name: str
    size_bytes: int


class AudioUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    project_id: str
    path: str
    original_filename: str
    mime_type: str
    size_bytes: int
    metadata: AudioMetadataOut
