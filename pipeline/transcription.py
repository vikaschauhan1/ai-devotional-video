"""faster-whisper based transcription.

Runs entirely locally. The model is loaded lazily on first call and
cached in-process so subsequent transcriptions reuse it (loading a
Whisper model takes several seconds).

Model, compute type and device are read from settings (WHISPER_MODEL,
WHISPER_COMPUTE_TYPE, WHISPER_DEVICE). On CPU-only hardware the sane
defaults are ``small`` + ``int8`` which needs ~250 MB VRAM/RAM and
transcribes at roughly real-time on modern laptops.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faster_whisper import WhisperModel  # noqa: F401

log = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    """Raised when transcription cannot produce a usable result."""


@dataclass(slots=True, frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(slots=True)
class TranscriptionResult:
    language: str
    language_probability: float
    duration: float
    model: str
    segments: list[TranscriptSegment] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(s.text.strip() for s in self.segments if s.text.strip())

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "language_probability": self.language_probability,
            "duration": self.duration,
            "model": self.model,
            "segments": [
                {"start": s.start, "end": s.end, "text": s.text}
                for s in self.segments
            ],
        }


# ── Process-wide cached model ─────────────────────────────
# Loading a Whisper model is expensive (~4-8 s + ~250 MB RSS for `small`).
# Keep one loaded per (name, device, compute_type) tuple for the lifetime
# of the process. Guarded by a lock so concurrent requests can't race
# and load two copies.
_MODEL_CACHE: dict[tuple[str, str, str], object] = {}
_MODEL_LOCK = threading.Lock()


def _get_model(name: str, device: str, compute_type: str) -> object:
    key = (name, device, compute_type)
    model = _MODEL_CACHE.get(key)
    if model is not None:
        return model
    with _MODEL_LOCK:
        model = _MODEL_CACHE.get(key)
        if model is not None:
            return model
        from faster_whisper import WhisperModel

        log.info(
            "loading Whisper model name=%s device=%s compute=%s",
            name,
            device,
            compute_type,
        )
        model = WhisperModel(
            name,
            device=device,
            compute_type=compute_type,
        )
        _MODEL_CACHE[key] = model
        return model


def transcribe(
    audio_path: Path,
    *,
    model_name: str,
    device: str = "cpu",
    compute_type: str = "int8",
    language: str | None = None,
    beam_size: int = 5,
    vad_filter: bool = True,
) -> TranscriptionResult:
    """Run faster-whisper on ``audio_path`` and return structured output.

    ``language`` may be an ISO code ("hi", "sa", "en") or None to
    auto-detect. Sanskrit is not natively supported by Whisper, so
    Sanskrit lyrics are typically detected as ``hi``; that is fine for
    scene planning and is handled downstream when appropriate.
    """
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise TranscriptionError(f"audio not found: {audio_path}")

    model = _get_model(model_name, device, compute_type)

    try:
        segments_iter, info = model.transcribe(  # type: ignore[attr-defined]
            str(audio_path),
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
        )
    except Exception as exc:  # noqa: BLE001 - re-raise as domain error
        raise TranscriptionError(f"whisper failed: {exc}") from exc

    segments: list[TranscriptSegment] = []
    # ``segments_iter`` is a generator; iterate once, streaming.
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=float(seg.start),
                end=float(seg.end),
                text=text,
            )
        )

    return TranscriptionResult(
        language=str(info.language),
        language_probability=float(info.language_probability),
        duration=float(info.duration),
        model=model_name,
        segments=segments,
    )
