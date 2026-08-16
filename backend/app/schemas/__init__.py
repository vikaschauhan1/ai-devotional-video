"""Pydantic schemas exposed through the API."""

from backend.app.schemas.audio import AudioMetadataOut, AudioUploadResponse
from backend.app.schemas.common import (
    HealthResponse,
    JobStatusEnum,
    Message,
)
from backend.app.schemas.images import (
    GeneratedImage,
    GenerateImagesRequest,
    GenerateImagesResponse,
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
from backend.app.schemas.scenes import (
    PlanScenesRequest,
    PlanScenesResponse,
    SceneOut,
    ScenePlan,
    TransitionType,
)
from backend.app.schemas.transcription import (
    TranscriptionRequest,
    TranscriptionResponse,
    TranscriptSegmentOut,
)
from backend.app.schemas.videos import (
    GeneratedVideo,
    GenerateVideosRequest,
    GenerateVideosResponse,
)

__all__ = [
    "AudioMetadataOut",
    "AudioUploadResponse",
    "GenerateImagesRequest",
    "GenerateImagesResponse",
    "GenerateVideosRequest",
    "GenerateVideosResponse",
    "GeneratedImage",
    "GeneratedVideo",
    "HealthResponse",
    "JobRead",
    "JobStatusEnum",
    "LyricsAnalysis",
    "LyricsAnalysisResponse",
    "LyricsSection",
    "LyricsUploadRequest",
    "LyricsUploadResponse",
    "Message",
    "PlanScenesRequest",
    "PlanScenesResponse",
    "ProjectCreate",
    "ProjectRead",
    "ProjectUpdate",
    "SceneOut",
    "ScenePlan",
    "SceneRead",
    "SectionType",
    "TranscriptSegmentOut",
    "TranscriptionRequest",
    "TranscriptionResponse",
    "TransitionType",
    "VisualIntensity",
]
