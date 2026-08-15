"""Transcription request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TranscriptSegmentOut(BaseModel):
    start: float
    end: float
    text: str


class TranscriptionRequest(BaseModel):
    """Optional overrides for the /transcribe endpoint."""

    language: str | None = Field(
        default=None,
        description="ISO code ('hi', 'sa', 'en'); omit to auto-detect.",
        max_length=8,
    )
    beam_size: int = Field(default=5, ge=1, le=10)
    vad_filter: bool = True


class TranscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    audio_asset_id: str
    transcript_asset_id: str
    language: str
    language_probability: float
    duration: float
    model: str
    segments: list[TranscriptSegmentOut]
    text: str
    transcript_path: str
