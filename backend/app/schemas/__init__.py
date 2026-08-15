"""Pydantic schemas exposed through the API."""

from backend.app.schemas.audio import AudioMetadataOut, AudioUploadResponse
from backend.app.schemas.common import (
    HealthResponse,
    JobStatusEnum,
    Message,
)
from backend.app.schemas.job import JobRead
from backend.app.schemas.lyrics import (
    LyricsAnalysis,
    LyricsAnalysisResponse,
    LyricsSection,
    LyricsUploadRequest,
    LyricsUploadResponse,
    SectionType,
    VisualIntensity,
)
from backend.app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from backend.app.schemas.scene import SceneRead
from backend.app.schemas.transcription import (
    TranscriptionRequest,
    TranscriptionResponse,
    TranscriptSegmentOut,
)

__all__ = [
    "AudioMetadataOut",
    "AudioUploadResponse",
    "HealthResponse",
    "JobRead",
    "JobStatusEnum",
    "LyricsAnalysis",
    "LyricsAnalysisResponse",
    "LyricsSection",
    "LyricsUploadRequest",
    "LyricsUploadResponse",
    "Message",
    "ProjectCreate",
    "ProjectRead",
    "ProjectUpdate",
    "SceneRead",
    "SectionType",
    "TranscriptSegmentOut",
    "TranscriptionRequest",
    "TranscriptionResponse",
    "VisualIntensity",
]
