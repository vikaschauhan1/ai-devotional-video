"""Video-engine factory.

Returns the concrete adapter chosen via ``settings.video_engine``.
Only ``procedural`` (FFmpeg Ken-Burns from stills) is implemented on
this machine. Unknown values fall back to the procedural engine so a
stale ``.env`` cannot brick the app.
"""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.settings import get_settings
from models.video.base import VideoGenerationEngine
from models.video.procedural import ProceduralVideoEngine


@lru_cache
def get_video_engine() -> VideoGenerationEngine:
    s = get_settings()
    name = s.video_engine.lower()
    if name in {"procedural", "stub", "none", ""}:
        return ProceduralVideoEngine(storage_root=s.storage_root)
    # Future: wan, svd, animatediff. Fall back to procedural until those
    # adapters exist so the pipeline never dead-ends.
    return ProceduralVideoEngine(storage_root=s.storage_root)


def reset_video_engine_cache() -> None:
    get_video_engine.cache_clear()
