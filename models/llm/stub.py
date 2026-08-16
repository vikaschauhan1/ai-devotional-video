"""Deterministic stub LLM used in tests and as a safe default.

This is *not* a fake pretending to be a real LLM. It is a documented
development shim so the pipeline can run end-to-end when a real LLM
isn't available. It never calls out over the network. It always returns
a minimal but valid song-structure JSON for the lyrics analyzer, so
downstream code (scene planner, storage, API contracts) can be tested.

Set ``LLM_ENGINE=ollama`` in ``.env`` to switch to the real adapter.
"""

from __future__ import annotations

import json

from models.llm.base import LLMEngine, LLMResponse

_FALLBACK_ANALYSIS = {
    "theme": "devotional",
    "deity": None,
    "language": "hi",
    "mood": "devotional",
    "sections": [
        {
            "type": "mukhda",
            "start": 0.0,
            "end": 0.0,
            "lyrics": "",
            "visual_intensity": "medium",
        }
    ],
}


class StubLLMEngine(LLMEngine):
    name = "stub"

    def __init__(self, *, model: str = "stub") -> None:
        self.model = model

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        # Echo enough to be useful in tests without pretending to reason.
        return LLMResponse(text=f"[stub] {prompt[:200]}")

    async def generate_json(
        self,
        prompt: str,
        *,
        schema: dict,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> dict:
        # Return the fallback analysis. Adapters do not attempt to fake
        # the actual meaning of the lyrics.
        _ = schema
        return json.loads(json.dumps(_FALLBACK_ANALYSIS))
