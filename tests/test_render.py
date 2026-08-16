"""Compositor + /render endpoint tests (Phase 16).

Runs real FFmpeg through the full pipeline: audio upload → analyse →
plan → images → videos → render. Everything is tiny so it finishes in
a few seconds.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.app.main import app
from models.llm import get_llm_engine
from models.llm.base import LLMEngine, LLMResponse

ffmpeg = shutil.which("ffmpeg")
ffprobe = shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(
    ffmpeg is None or ffprobe is None,
    reason="ffmpeg/ffprobe not on PATH",
)


class _QueuedFakeLLM(LLMEngine):
    name = "fake"

    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def push(self, payload: dict) -> None:
        self.payloads.append(payload)

    async def generate(self, prompt, *, system=None, temperature=0.4, max_tokens=1024):
        return LLMResponse(text="[fake]")

    async def generate_json(
        self, prompt, *, schema, system=None, temperature=0.2, max_tokens=2048
    ):
        assert self.payloads, "no payload queued"
        return self.payloads.pop(0)


_ANALYSIS = {
    "theme": "Shiva devotional",
    "deity": "Shiva",
    "language": "hi",
    "mood": "devotional",
    "sections": [
        {"type": "mukhda", "start": 0.0, "end": 4.0,
         "lyrics": "जय शिव शंभो", "visual_intensity": "high"},
    ],
}


def _plan(n: int = 2, duration: float = 1.5, transitions: list[str] | None = None) -> dict:
    scenes = []
    default_transitions = transitions or ["crossfade"] * n
    for i in range(1, n + 1):
        tr = (
            default_transitions[i - 1]
            if i - 1 < len(default_transitions)
            else "crossfade"
        )
        scenes.append(
            {
                "scene_id": i,
                "start": (i - 1) * duration,
                "end": i * duration,
                "lyrics": "जय शिव शंभो" if i == 1 else "",
                "prompt": f"Scene {i}",
                "negative_prompt": "text",
                "camera": "slow push-in" if i % 2 else "pan-right",
                "lighting": "golden",
                "mood": "devotional",
                "transition": tr,
            }
        )
    return {
        "theme": "Shiva",
        "aspect_ratio": "1:1",
        "style_preset": "shiva-himalayan",
        "scenes": scenes,
    }


def _make_wav(path: Path, seconds: float = 3.0) -> None:
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
            "22050",
            str(path),
        ],
        check=True,
    )


def _probe(path: Path) -> dict:
    assert ffprobe is not None
    out = subprocess.check_output(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        text=True,
    )
    return json.loads(out)


@pytest.fixture()
def fake_llm():
    fake = _QueuedFakeLLM()
    app.dependency_overrides[get_llm_engine] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm_engine, None)


def _prepare_full(client, fake_llm, tmp_path: Path, n_scenes: int = 2) -> str:
    """Project → audio → lyrics → analyze → plan → images → videos.

    All tiny (1:1 320x320, ~1.5s scenes, ~3s WAV audio).
    """
    r = client.post(
        "/api/projects",
        json={
            "name": "R",
            "deity": "Shiva",
            "style": "shiva-himalayan",
            "aspect_ratio": "1:1",
            "resolution": "320x320",
        },
    )
    pid = r.json()["id"]

    # Audio
    wav = tmp_path / "aud.wav"
    _make_wav(wav, seconds=3.0)
    r = client.post(
        f"/api/projects/{pid}/audio",
        files={"file": ("bhajan.wav", io.BytesIO(wav.read_bytes()), "audio/wav")},
    )
    assert r.status_code == 201, r.text

    # Lyrics + analyze + plan + images + videos
    client.post(f"/api/projects/{pid}/lyrics", json={"text": "जय शिव शंभो"})
    fake_llm.push(_ANALYSIS)
    assert client.post(f"/api/projects/{pid}/analyze").status_code == 201
    fake_llm.push(_plan(n_scenes, transitions=["crossfade", "cut", "dip-to-black"][:n_scenes]))
    assert client.post(f"/api/projects/{pid}/plan-scenes").status_code == 201
    assert client.post(f"/api/projects/{pid}/generate-images").status_code == 201
    assert client.post(f"/api/projects/{pid}/generate-videos").status_code == 201
    return pid


def test_render_produces_final_mp4_with_audio(client, fake_llm, tmp_path):
    pid = _prepare_full(client, fake_llm, tmp_path, n_scenes=2)

    r = client.post(f"/api/projects/{pid}/render")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["project_id"] == pid
    assert body["scene_count"] == 2
    assert body["subtitles_burned"] is False

    p = Path(body["path"])
    assert p.exists() and p.suffix == ".mp4"
    assert body["size_bytes"] > 0

    info = _probe(p)
    codecs = {s["codec_type"]: s["codec_name"] for s in info["streams"]}
    assert codecs.get("video") == "h264"
    assert codecs.get("audio") == "aac"

    video_stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert int(video_stream["width"]) == 320
    assert int(video_stream["height"]) == 320
    assert float(info["format"]["duration"]) > 1.5


def test_render_status_returns_latest(client, fake_llm, tmp_path):
    pid = _prepare_full(client, fake_llm, tmp_path, n_scenes=2)

    # No final yet -> 404
    r = client.get(f"/api/projects/{pid}/render")
    assert r.status_code == 404

    # POST creates one
    assert client.post(f"/api/projects/{pid}/render").status_code == 201

    # GET returns it
    r = client.get(f"/api/projects/{pid}/render")
    assert r.status_code == 200
    body = r.json()
    assert body["scene_count"] == 2
    assert Path(body["path"]).exists()


def test_render_burn_subtitles_writes_srt_and_burns(client, fake_llm, tmp_path, monkeypatch):
    """Force a transcript to exist for this project (mocked whisper output)."""
    pid = _prepare_full(client, fake_llm, tmp_path, n_scenes=2)

    # Fake a transcript by patching the transcribe() call and hitting /transcribe.
    from pipeline.transcription import TranscriptionResult, TranscriptSegment

    def fake_transcribe(*args, **kwargs):
        return TranscriptionResult(
            language="hi",
            language_probability=0.99,
            duration=3.0,
            model="fake",
            segments=[
                TranscriptSegment(start=0.0, end=1.5, text="जय शिव शंभो"),
                TranscriptSegment(start=1.5, end=3.0, text="जय महेश्वर"),
            ],
        )

    monkeypatch.setattr(
        "backend.app.services.transcription.transcribe", fake_transcribe
    )
    r = client.post(f"/api/projects/{pid}/transcribe")
    assert r.status_code == 201

    r = client.post(f"/api/projects/{pid}/render", json={"burn_subtitles": True})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["subtitles_burned"] is True

    # SRT was written next to the final mp4
    p = Path(body["path"])
    srt = p.with_suffix(".srt")
    assert srt.exists()
    content = srt.read_text(encoding="utf-8")
    assert "जय शिव शंभो" in content


def test_render_without_videos_returns_409(client, fake_llm, tmp_path):
    """Have scenes but no videos → 409."""
    r = client.post(
        "/api/projects",
        json={"name": "n", "aspect_ratio": "1:1", "resolution": "320x320"},
    )
    pid = r.json()["id"]
    client.post(f"/api/projects/{pid}/lyrics", json={"text": "x"})
    fake_llm.push(_ANALYSIS)
    assert client.post(f"/api/projects/{pid}/analyze").status_code == 201
    fake_llm.push(_plan(1))
    assert client.post(f"/api/projects/{pid}/plan-scenes").status_code == 201
    # Skip /generate-images and /generate-videos

    r = client.post(f"/api/projects/{pid}/render")
    assert r.status_code == 409


def test_render_without_scenes_returns_409(client):
    r = client.post("/api/projects", json={"name": "empty"})
    pid = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/render")
    assert r.status_code == 409


def test_render_missing_project_returns_404(client):
    r = client.post("/api/projects/does-not-exist/render")
    assert r.status_code == 404


def test_compositor_srt_writer_handles_devanagari(tmp_path):
    from pipeline.compositor import _write_srt

    dest = tmp_path / "subs.srt"
    _write_srt(
        [
            {"start": 0.0,   "end": 2.5, "text": "जय शिव शंभो"},
            {"start": 2.5,   "end": 5.0, "text": "जय महेश्वर"},
        ],
        dest,
    )
    content = dest.read_text(encoding="utf-8")
    assert "जय शिव शंभो" in content
    assert "00:00:00,000 --> 00:00:02,500" in content
    assert content.rstrip().endswith("जय महेश्वर")
