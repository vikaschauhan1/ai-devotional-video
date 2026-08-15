"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.core.settings import get_settings
from backend.app.schemas import HealthResponse

router = APIRouter()

_VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    s = get_settings()
    return HealthResponse(
        status="ok",
        version=_VERSION,
        engines={
            "llm": s.llm_engine,
            "image": s.image_engine,
            "video": s.video_engine,
            "lipsync": s.lipsync_engine,
            "tts": s.tts_engine,
            "asr": f"faster-whisper:{s.whisper_model}",
        },
    )
