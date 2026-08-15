"""Abstract base for video-generation engines.

The MVP ships a ``ProceduralVideoEngine`` implementation (FFmpeg
zoompan + xfade over generated stills) that runs on any host. Real
neural T2V / I2V models such as Wan 2.x, SVD, or AnimateDiff plug in
behind the same interface as soon as a CUDA GPU is available.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class VideoGenerationRequest:
    prompt: str
    duration: float
    # Optional first-frame conditioning (image-to-video)
    image_path: Path | None = None
    negative_prompt: str | None = None
    width: int = 720
    height: int = 1280
    fps: int = 24
    seed: int | None = None
    camera_hint: str | None = None  # e.g. "slow push-in", "pan-left"
    extras: dict = field(default_factory=dict)


@dataclass(slots=True)
class VideoGenerationResult:
    path: Path
    duration: float
    fps: int
    engine: str
    metadata: dict = field(default_factory=dict)


class VideoGenerationEngine(ABC):
    """Interface every video-generation adapter must implement."""

    name: str = "abstract"

    @abstractmethod
    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        raise NotImplementedError
