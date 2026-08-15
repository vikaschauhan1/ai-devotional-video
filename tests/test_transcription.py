"""Transcription endpoint tests.

Fast tests mock the underlying ``pipeline.transcription.transcribe``
function so the suite never downloads a Whisper model. The full model
run is guarded behind ``RUN_WHISPER_INTEGRATION=1`` for local
verification.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline.transcription import TranscriptionResult, TranscriptSegment

ffmpeg = shutil.which("ffmpeg")
pytestmark = pytest.mark.skipif(ffmpeg is None, reason="ffmpeg not on PATH")


def _make_wav(path: Path, seconds: float = 2.0) -> None:
    assert ffmpeg is not None
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
            f"sine=frequency=440:duration={seconds}",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(path),
        ],
        check=True,
    )


def _create_project_with_audio(client, tmp_path: Path) -> tuple[str, bytes]:
    wav = tmp_path / "sine.wav"
    _make_wav(wav, seconds=2.0)
    wav_bytes = wav.read_bytes()

    r = client.post("/api/projects", json={"name": "T"})
    assert r.status_code == 201
    pid = r.json()["id"]

    r = client.post(
        f"/api/projects/{pid}/audio",
        files={"file": ("bhajan.wav", io.BytesIO(wav_bytes), "audio/wav")},
    )
    assert r.status_code == 201, r.text
    return pid, wav_bytes


def _fake_transcribe_result() -> TranscriptionResult:
    return TranscriptionResult(
        language="hi",
        language_probability=0.98,
        duration=2.0,
        model="small",
        segments=[
            TranscriptSegment(start=0.0, end=1.0, text="जय शिव शंभो"),
            TranscriptSegment(start=1.0, end=2.0, text="जय महेश्वर"),
        ],
    )


def test_transcribe_returns_segments_and_persists_asset(client, tmp_path):
    pid, _ = _create_project_with_audio(client, tmp_path)

    with patch(
        "backend.app.services.transcription.transcribe",
        return_value=_fake_transcribe_result(),
    ):
        r = client.post(f"/api/projects/{pid}/transcribe")

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["project_id"] == pid
    assert body["language"] == "hi"
    assert body["language_probability"] == pytest.approx(0.98)
    assert len(body["segments"]) == 2
    assert body["segments"][0]["text"] == "जय शिव शंभो"
    assert "जय शिव शंभो" in body["text"]

    # Transcript JSON exists on disk
    tp = Path(body["transcript_path"])
    assert tp.exists()
    assert tp.suffix == ".json"

    # Second call still works (creates a new transcript asset)
    with patch(
        "backend.app.services.transcription.transcribe",
        return_value=_fake_transcribe_result(),
    ):
        r2 = client.post(f"/api/projects/{pid}/transcribe")
    assert r2.status_code == 201
    assert r2.json()["transcript_asset_id"] != body["transcript_asset_id"]


def test_transcribe_no_audio_returns_409(client):
    r = client.post("/api/projects", json={"name": "empty"})
    pid = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/transcribe")
    assert r.status_code == 409
    assert "no audio" in r.json()["detail"].lower()


def test_transcribe_missing_project_returns_404(client):
    r = client.post("/api/projects/does-not-exist/transcribe")
    assert r.status_code == 404


def test_transcribe_engine_error_returns_500(client, tmp_path):
    pid, _ = _create_project_with_audio(client, tmp_path)

    def boom(*args, **kwargs):
        from pipeline.transcription import TranscriptionError

        raise TranscriptionError("whisper failed: simulated")

    with patch("backend.app.services.transcription.transcribe", side_effect=boom):
        r = client.post(f"/api/projects/{pid}/transcribe")
    assert r.status_code == 500


@pytest.mark.skipif(
    os.environ.get("RUN_WHISPER_INTEGRATION") != "1",
    reason="Set RUN_WHISPER_INTEGRATION=1 to run the real Whisper model (downloads weights).",
)
def test_transcribe_real_whisper_integration(client, tmp_path):
    """Real Whisper run against a 2-second sine wave. Expects an empty or
    trivial transcript (there are no words to hear), but proves that the
    model loads, VAD runs, and the response shape is right."""
    pid, _ = _create_project_with_audio(client, tmp_path)
    r = client.post(
        f"/api/projects/{pid}/transcribe",
        json={"language": "en", "beam_size": 1, "vad_filter": False},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["duration"] == pytest.approx(2.0, abs=0.5)
    assert body["model"]
