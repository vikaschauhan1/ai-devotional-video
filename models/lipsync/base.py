"""Abstract base for lip-sync engines (MuseTalk, Wav2Lip, no-op)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class LipSyncRequest:
    video_path: Path
    audio_path: Path
    # Face bounding-box hint (x, y, w, h) as fractions of frame size,
    # if the caller already knows where the singer is on screen.
    face_bbox: tuple[float, float, float, float] | None = None
    extras: dict = field(default_factory=dict)


@dataclass(slots=True)
class LipSyncResult:
    path: Path
    engine: str
    metadata: dict = field(default_factory=dict)


class LipSyncEngine(ABC):
    """Interface every lip-sync adapter must implement."""

    name: str = "abstract"

    @abstractmethod
    async def synchronize(self, request: LipSyncRequest) -> LipSyncResult:
        raise NotImplementedError
