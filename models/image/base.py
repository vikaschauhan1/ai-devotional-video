"""Abstract base for image-generation engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ImageGenerationRequest:
    prompt: str
    negative_prompt: str | None = None
    width: int = 1024
    height: int = 1024
    seed: int | None = None
    reference_image: Path | None = None
    # Free-form extras a specific adapter may honour (steps, guidance, …)
    extras: dict = field(default_factory=dict)


@dataclass(slots=True)
class ImageGenerationResult:
    path: Path
    seed: int
    engine: str
    metadata: dict = field(default_factory=dict)


class ImageGenerationEngine(ABC):
    """Interface every image-generation adapter must implement."""

    name: str = "abstract"

    @abstractmethod
    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        raise NotImplementedError
