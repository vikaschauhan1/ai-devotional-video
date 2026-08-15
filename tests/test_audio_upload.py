"""Audio upload + ffprobe metadata tests (Phase 7).

Generates real WAV files at test time via ``ffmpeg lavfi sine`` so we
exercise the actual ffprobe path — no ML, no external downloads.
"""

from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import pytest

ffmpeg = shutil.which("ffmpeg")
pytestmark = pytest.mark.skipif(ffmpeg is None, reason="ffmpeg not on PATH")


def _make_wav(path: Path, seconds: float = 1.0, freq: int = 440) -> None:
    """Synthesize a mono 44.1kHz WAV via ffmpeg's built-in sine generator."""
    assert ffmpeg is not None  # narrowed by skipif above
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={freq}:duration={seconds}",
            "-ac",
            "1",
            "-ar",
            "44100",
            str(path),
        ],
        check=True,
    )


@pytest.fixture()
def wav_bytes(tmp_path: Path) -> bytes:
    p = tmp_path / "sine.wav"
    _make_wav(p, seconds=1.5)
    return p.read_bytes()


def _create_project(client, name: str = "Audio test") -> str:
    r = client.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_upload_valid_wav_persists_metadata(client, wav_bytes):
    pid = _create_project(client)
    r = client.post(
        f"/api/projects/{pid}/audio",
        files={"file": ("bhajan.wav", io.BytesIO(wav_bytes), "audio/wav")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["project_id"] == pid
    assert body["original_filename"] == "bhajan.wav"
    assert body["mime_type"] in {"audio/wav", "audio/x-wav", "audio/wave"}
    assert body["size_bytes"] == len(wav_bytes)

    meta = body["metadata"]
    assert 1.2 <= meta["duration"] <= 1.8  # allow small ffprobe rounding
    assert meta["sample_rate"] == 44100
    assert meta["channels"] == 1
    assert meta["codec"] in {"pcm_s16le", "pcm_s24le", "pcm_f32le"}
    assert meta["size_bytes"] == len(wav_bytes)

    # File actually on disk under storage/audio/<pid>/
    p = Path(body["path"])
    assert p.exists() and p.stat().st_size == len(wav_bytes)
    assert p.parent.name == pid
    assert p.parent.parent.name == "audio"
    assert p.name != "bhajan.wav"  # renamed to a safe UUID


def test_upload_rejects_disallowed_extension(client, wav_bytes):
    pid = _create_project(client)
    r = client.post(
        f"/api/projects/{pid}/audio",
        files={"file": ("bhajan.exe", io.BytesIO(wav_bytes), "audio/wav")},
    )
    assert r.status_code == 415


def test_upload_rejects_mismatched_content_type(client, wav_bytes):
    pid = _create_project(client)
    r = client.post(
        f"/api/projects/{pid}/audio",
        files={"file": ("bhajan.wav", io.BytesIO(wav_bytes), "image/png")},
    )
    assert r.status_code == 415


def test_upload_rejects_non_audio_bytes(client):
    pid = _create_project(client)
    # Real WAV extension + audio content-type, but the bytes are junk.
    # save_upload() accepts it (extension + content-type ok), then ffprobe
    # rejects it and the endpoint cleans up.
    r = client.post(
        f"/api/projects/{pid}/audio",
        files={"file": ("bhajan.wav", io.BytesIO(b"not audio"), "audio/wav")},
    )
    assert r.status_code == 400
    assert "audio invalid" in r.json()["detail"].lower()


def test_upload_requires_existing_project(client, wav_bytes):
    r = client.post(
        "/api/projects/does-not-exist/audio",
        files={"file": ("bhajan.wav", io.BytesIO(wav_bytes), "audio/wav")},
    )
    assert r.status_code == 404


def test_upload_empty_file_rejected(client):
    pid = _create_project(client)
    r = client.post(
        f"/api/projects/{pid}/audio",
        files={"file": ("bhajan.wav", io.BytesIO(b""), "audio/wav")},
    )
    assert r.status_code == 400
