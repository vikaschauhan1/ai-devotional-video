"""Lip-sync engine factory."""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.settings import get_settings
from models.lipsync.base import LipSyncEngine, LipSyncRequest, LipSyncResult


class _NoOpLipSyncEngine(LipSyncEngine):
    """Identity: returns the input video path unchanged. Default engine."""

    name = "noop"

    async def synchronize(self, request: LipSyncRequest) -> LipSyncResult:
        return LipSyncResult(
            path=request.video_path,
            engine=self.name,
            metadata={"note": "lip-sync disabled"},
        )


@lru_cache
def get_lipsync_engine() -> LipSyncEngine:
    s = get_settings()
    name = s.lipsync_engine.lower()
    if name == "wav2lip":
        from models.lipsync.wav2lip import Wav2LipEngine  # noqa: PLC0415

        return Wav2LipEngine(storage_root=s.storage_root)
    return _NoOpLipSyncEngine()


def reset_lipsync_engine_cache() -> None:
    get_lipsync_engine.cache_clear()
