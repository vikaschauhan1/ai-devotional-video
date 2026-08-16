"""Piper TTS adapter (Phase 22).

Piper is a fast, local, ONNX-based TTS runtime. Voices are separate
files: an ONNX model + a JSON config, both downloaded once and
referenced by path.

The adapter is lazy: no voice is loaded until ``generate`` is called.
Voice files live at ``settings.storage_root / "voices" / <voice-id>/`` OR
at ``PIPER_VOICES_DIR`` if set in the environment.

Voice file layout (Piper convention):

    <voice-id>.onnx
    <voice-id>.onnx.json

For Hindi devotional narration, ``hi_IN-priyamvada-medium`` is a good
starting point. Download from
https://huggingface.co/rhasspy/piper-voices/tree/main/hi/hi_IN/priyamvada/medium

License: MIT (Piper) + individual voice licenses (mostly OFL/MIT).
"""

from __future__ import annotations

import logging
import os
import wave
from pathlib import Path

from models.tts.base import TTSEngine, TTSRequest, TTSResult

log = logging.getLogger(__name__)


class PiperError(RuntimeError):
    pass


def _voices_dir(storage_root: Path) -> Path:
    override = os.environ.get("PIPER_VOICES_DIR")
    if override:
        return Path(override)
    return storage_root / "voices"


def _resolve_voice(voices_dir: Path, voice_id: str) -> tuple[Path, Path]:
    """Return (model_path, config_path) for a voice id."""
    model = voices_dir / f"{voice_id}.onnx"
    config = voices_dir / f"{voice_id}.onnx.json"
    if not model.is_file() or not config.is_file():
        raise PiperError(
            f"voice {voice_id!r} not found under {voices_dir}. "
            f"Download {voice_id}.onnx and {voice_id}.onnx.json from "
            f"https://huggingface.co/rhasspy/piper-voices."
        )
    return model, config


class PiperTTSEngine(TTSEngine):
    name = "piper"

    def __init__(
        self,
        *,
        storage_root: Path,
        default_voice: str = "hi_IN-priyamvada-medium",
    ) -> None:
        self.storage_root = Path(storage_root)
        self.default_voice = default_voice
        self._cache: dict[str, object] = {}

    def _load(self, voice_id: str):
        cached = self._cache.get(voice_id)
        if cached is not None:
            return cached
        try:
            from piper import PiperVoice  # noqa: PLC0415
        except ImportError as exc:
            raise PiperError(
                "piper-tts not installed. Run: uv pip install piper-tts"
            ) from exc

        voices_dir = _voices_dir(self.storage_root)
        model_path, config_path = _resolve_voice(voices_dir, voice_id)
        log.info("loading Piper voice %s from %s", voice_id, model_path)
        voice = PiperVoice.load(str(model_path), config_path=str(config_path))
        self._cache[voice_id] = voice
        return voice

    async def generate(self, request: TTSRequest) -> TTSResult:
        voice_id = request.voice or self.default_voice
        voice = self._load(voice_id)
        text = request.text.strip()
        if not text:
            raise PiperError("empty text")

        dest_dir = (
            self.storage_root / "generated_audio"
        ).resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Piper writes to a wave.Wave_write; we hand it a file we open here.
        dest = dest_dir / f"tts-{abs(hash(text)) & 0xFFFFFFFF:08x}.wav"

        with wave.open(str(dest), "wb") as fh:
            # PiperVoice.synthesize_wav(text, wav_file, **kwargs) writes
            # a fully formed WAV. length_scale is inverse of speed.
            length_scale = 1.0 / max(0.25, min(request.speed, 4.0))
            voice.synthesize_wav(  # type: ignore[attr-defined]
                text,
                fh,
                length_scale=length_scale,
            )

        # Read sample rate back from the file (Piper picks it from the voice).
        with wave.open(str(dest), "rb") as fh:
            sample_rate = fh.getframerate()

        return TTSResult(
            path=dest,
            language=request.language,
            sample_rate=sample_rate,
            engine=self.name,
            metadata={
                "voice": voice_id,
                "speed": request.speed,
                "characters": len(text),
            },
        )
