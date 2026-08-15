"""Application settings loaded from environment / .env.

Values here mirror ``.env.example`` at the repo root. Import via
``from backend.app.core.settings import get_settings``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime settings.

    Loaded from environment first, then from ``.env`` at the repo root
    if present. Unknown keys are ignored so ``.env`` can carry future
    values without breaking older code.
    """

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── App ───────────────────────────────────────────────
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_log_level: str = "INFO"

    # ── Persistence ───────────────────────────────────────
    database_url: str = "sqlite:///./data/app.db"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # ── Storage ───────────────────────────────────────────
    storage_root: Path = REPO_ROOT / "storage"
    max_upload_mb: int = 200

    # ── Adapters ──────────────────────────────────────────
    llm_engine: str = "stub"
    llm_model: str = "qwen2.5:3b-instruct"
    llm_base_url: str = "http://127.0.0.1:11434"

    image_engine: str = "placeholder"
    image_model: str = "stabilityai/sdxl-turbo"

    video_engine: str = "procedural"
    video_model: str = ""

    lipsync_engine: str = "noop"
    lipsync_model: str = ""

    tts_engine: str = "stub"
    tts_model: str = ""

    # ── ASR ───────────────────────────────────────────────
    whisper_model: str = "small"
    whisper_compute_type: str = "int8"
    whisper_device: str = "cpu"

    # ── Frontend ──────────────────────────────────────────
    next_public_api_base: str = Field(default="http://127.0.0.1:8000")

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    def ensure_dirs(self) -> None:
        """Create local directories the app expects to exist."""
        (self.repo_root / "data").mkdir(parents=True, exist_ok=True)
        for sub in (
            "uploads",
            "audio",
            "transcripts",
            "references",
            "scenes",
            "generated_images",
            "generated_videos",
            "lipsync",
            "final",
        ):
            (self.storage_root / sub).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
