"""Abstract bases for speech and singing generation.

``TTSEngine`` is regular text-to-speech (Piper, IndicF5, …). Its output
sounds like *narration*, not classical Indian devotional singing.

``SingingGenerationEngine`` is a separate interface with no default
implementation. This is deliberate — the project must never present a
TTS voice as devotional singing. Real singing generation is a future
extension.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class TTSRequest:
    text: str
    language: str  # BCP-47-ish: "hi", "sa", "en", "ta", …
    voice: str | None = None
    speed: float = 1.0
    extras: dict = field(default_factory=dict)


@dataclass(slots=True)
class TTSResult:
    path: Path
    language: str
    sample_rate: int
    engine: str
    metadata: dict = field(default_factory=dict)


class TTSEngine(ABC):
    """Interface every TTS adapter must implement."""

    name: str = "abstract"

    @abstractmethod
    async def generate(self, request: TTSRequest) -> TTSResult:
        raise NotImplementedError


class SingingGenerationEngine(ABC):
    """Reserved interface for future devotional-singing engines.

    Deliberately *not* implemented in the MVP. Any adapter added here
    must produce actual singing / musical output, not narrated TTS.
    """

    name: str = "abstract"

    @abstractmethod
    async def generate(
        self,
        lyrics: str,
        *,
        language: str,
        raga: str | None = None,
        tempo_bpm: float | None = None,
        reference_audio: Path | None = None,
    ) -> Path:
        raise NotImplementedError
