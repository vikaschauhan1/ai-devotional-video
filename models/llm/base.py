"""Abstract base for text/instruct LLMs (scene planning, lyrics analysis)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class LLMResponse:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMEngine(ABC):
    """Interface every LLM adapter must implement."""

    name: str = "abstract"

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        *,
        schema: dict,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> dict:
        """Return a JSON object validated against ``schema``.

        Adapters must retry / repair invalid JSON internally. The caller
        can rely on the returned dict conforming to ``schema``.
        """
        raise NotImplementedError
