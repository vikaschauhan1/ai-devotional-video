"""Lyrics-analysis pipeline schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SectionType(StrEnum):
    INTRO = "intro"
    MUKHDA = "mukhda"
    ANTARA = "antara"
    BRIDGE = "bridge"
    MANTRA = "mantra"
    DOHA = "doha"
    CHANT = "chant"
    ALAP = "alap"
    OUTRO = "outro"


class VisualIntensity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LyricsSection(BaseModel):
    type: SectionType
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    lyrics: str = Field(min_length=1)
    visual_intensity: VisualIntensity = VisualIntensity.MEDIUM

    @field_validator("end")
    @classmethod
    def end_after_start(cls, v: float, info) -> float:
        start = info.data.get("start", 0.0)
        # end==start is allowed when we have no timing (unknown).
        if v < start:
            raise ValueError("end must be >= start")
        return v


class LyricsAnalysis(BaseModel):
    """Structured output of the lyrics analyzer.

    ``model_config`` allows StrEnum values to be serialized as their
    string form when returned by the API.
    """

    model_config = ConfigDict(use_enum_values=True)

    theme: str = Field(min_length=1, max_length=200)
    deity: str | None = Field(default=None, max_length=64)
    language: str = Field(min_length=2, max_length=8)
    mood: str = Field(min_length=1, max_length=64)
    sections: list[LyricsSection] = Field(min_length=1)


class LyricsUploadRequest(BaseModel):
    """Body for POST /projects/{id}/lyrics."""

    text: str = Field(min_length=1)


class LyricsUploadResponse(BaseModel):
    project_id: str
    lyrics_length: int


class LyricsAnalysisResponse(BaseModel):
    project_id: str
    engine: str
    model: str
    analysis: LyricsAnalysis
    analysis_asset_id: str
    analysis_path: str
