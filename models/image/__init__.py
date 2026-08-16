"""Image-engine factory.

Returns the concrete adapter chosen via ``settings.image_engine``.
Falls back to ``placeholder`` for unknown values so misconfigurations
don't crash the whole app — the placeholder engine is safe and honest.
"""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.settings import get_settings
from models.image.base import ImageGenerationEngine
from models.image.placeholder import PlaceholderImageEngine


@lru_cache
def get_image_engine() -> ImageGenerationEngine:
    s = get_settings()
    name = s.image_engine.lower()
    if name in {"placeholder", "stub", "none", ""}:
        return PlaceholderImageEngine(storage_root=s.storage_root)
    # Future: openvino_sdxl, diffusers_cpu. Until those adapters exist,
    # anything else silently maps to the placeholder so a stale .env can't
    # take the whole pipeline down. Logged via engine.name in responses.
    return PlaceholderImageEngine(storage_root=s.storage_root)


def reset_image_engine_cache() -> None:
    get_image_engine.cache_clear()
