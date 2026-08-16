"""TTS engine factory."""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.settings import get_settings
from models.tts.base import TTSEngine


class _StubTTSEngine(TTSEngine):
    """Never touches disk. Raises if asked to synthesise — the pipeline
    never calls TTS unless the user opts in, so this is safe to be the
    default."""

    name = "stub"

    async def generate(self, request):
        raise NotImplementedError(
            "TTS is disabled. Set TTS_ENGINE=piper in .env and install a voice."
        )


@lru_cache
def get_tts_engine() -> TTSEngine:
    s = get_settings()
    name = s.tts_engine.lower()
    if name == "piper":
        from models.tts.piper import PiperTTSEngine  # noqa: PLC0415

        default_voice = s.tts_model or "hi_IN-priyamvada-medium"
        return PiperTTSEngine(
            storage_root=s.storage_root, default_voice=default_voice
        )
    return _StubTTSEngine()


def reset_tts_engine_cache() -> None:
    get_tts_engine.cache_clear()
