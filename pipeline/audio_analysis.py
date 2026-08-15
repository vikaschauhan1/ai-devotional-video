"""FFprobe-based audio metadata extraction.

Uses a subprocess argument list (never a shell string) so filenames with
spaces or exotic characters cannot inject additional commands.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


class AudioAnalysisError(RuntimeError):
    """Raised when ffprobe fails or returns unusable metadata."""


@dataclass(slots=True, frozen=True)
class AudioMetadata:
    duration: float
    sample_rate: int
    channels: int
    codec: str
    bitrate: int | None
    format_name: str
    size_bytes: int

    def to_dict(self) -> dict:
        return {
            "duration": self.duration,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "codec": self.codec,
            "bitrate": self.bitrate,
            "format_name": self.format_name,
            "size_bytes": self.size_bytes,
        }


def _ffprobe_binary() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise AudioAnalysisError(
            "ffprobe not found on PATH. Install ffmpeg (which bundles ffprobe)."
        )
    return path


def probe(audio_path: Path) -> AudioMetadata:
    """Return metadata for the audio file at ``audio_path``.

    Never invokes a shell. All arguments are passed as a list so a file
    name like ``$(rm -rf ~).mp3`` is treated as a literal filename.
    """
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise AudioAnalysisError(f"audio file not found: {audio_path}")

    ffprobe = _ffprobe_binary()
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-select_streams",
        "a:0",
        str(audio_path),
    ]
    log.debug("running ffprobe: %s", cmd)
    try:
        proc = subprocess.run(  # noqa: S603 - argument list, no shell
            cmd,
            capture_output=True,
            check=True,
            text=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        raise AudioAnalysisError(
            f"ffprobe failed ({exc.returncode}): {exc.stderr.strip()[:500]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioAnalysisError("ffprobe timed out after 30s") from exc

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AudioAnalysisError("ffprobe returned invalid JSON") from exc

    streams = payload.get("streams") or []
    if not streams:
        raise AudioAnalysisError("no audio stream found in file")
    stream = streams[0]
    fmt = payload.get("format") or {}

    try:
        duration = float(fmt.get("duration") or stream.get("duration") or 0.0)
        sample_rate = int(stream.get("sample_rate") or 0)
        channels = int(stream.get("channels") or 0)
    except (TypeError, ValueError) as exc:
        raise AudioAnalysisError("ffprobe returned non-numeric metadata") from exc

    if duration <= 0 or sample_rate <= 0 or channels <= 0:
        raise AudioAnalysisError(
            "unusable metadata: "
            f"duration={duration}, sample_rate={sample_rate}, channels={channels}"
        )

    bitrate_raw = fmt.get("bit_rate") or stream.get("bit_rate")
    bitrate = int(bitrate_raw) if bitrate_raw is not None else None

    return AudioMetadata(
        duration=duration,
        sample_rate=sample_rate,
        channels=channels,
        codec=str(stream.get("codec_name") or "unknown"),
        bitrate=bitrate,
        format_name=str(fmt.get("format_name") or "unknown"),
        size_bytes=audio_path.stat().st_size,
    )
