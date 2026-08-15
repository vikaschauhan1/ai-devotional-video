"""Engine factories.

Import ``get_llm_engine()`` in code that needs an LLM; it picks the
concrete adapter based on ``settings.llm_engine`` so calls don't need
to care which one is loaded.
"""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.settings import get_settings
from models.llm.base import LLMEngine
from models.llm.ollama import OllamaLLMEngine
from models.llm.stub import StubLLMEngine


@lru_cache
def get_llm_engine() -> LLMEngine:
    s = get_settings()
    name = s.llm_engine.lower()
    if name == "ollama":
        return OllamaLLMEngine(model=s.llm_model, base_url=s.llm_base_url)
    if name in {"stub", "placeholder", "none"}:
        return StubLLMEngine(model=s.llm_model)
    raise ValueError(f"unknown LLM_ENGINE: {s.llm_engine}")


def reset_llm_engine_cache() -> None:
    """Only used by tests that need a fresh engine after env changes."""
    get_llm_engine.cache_clear()
