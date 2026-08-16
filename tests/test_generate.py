"""End-to-end /generate endpoint test (Phase 18/19)."""

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
        {"type": "mukhda", "start": 0.0, "end": 3.0,
         "lyrics": "जय शिव शंभो", "visual_intensity": "high"},
    ],
}


def _plan(n: int = 2, duration: float = 1.5) -> dict:
    scenes = []
    for i in range(1, n + 1):
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
                "transition": "crossfade",
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
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-ac", "1", "-ar", "22050", str(path),
        ],
        check=True,
    )


def _probe(path: Path) -> dict:
    assert ffprobe is not None
    out = subprocess.check_output(
        [ffprobe, "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        text=True,
    )
    return json.loads(out)


@pytest.fixture()
def fake_llm():
    fake = _QueuedFakeLLM()
    app.dependency_overrides[get_llm_engine] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm_engine, None)


def _project_with_audio_and_lyrics(client, tmp_path: Path) -> str:
    r = client.post(
        "/api/projects",
        json={
            "name": "MVP",
            "deity": "Shiva",
            "style": "shiva-himalayan",
            "aspect_ratio": "1:1",
            "resolution": "320x320",
        },
    )
    pid = r.json()["id"]
    wav = tmp_path / "aud.wav"
    _make_wav(wav, seconds=3.0)
    r = client.post(
        f"/api/projects/{pid}/audio",
        files={"file": ("bhajan.wav", io.BytesIO(wav.read_bytes()), "audio/wav")},
    )
    assert r.status_code == 201
    client.post(f"/api/projects/{pid}/lyrics", json={"text": "जय शिव शंभो"})
    return pid


def test_generate_end_to_end_produces_final_video(client, fake_llm, tmp_path):
    pid = _project_with_audio_and_lyrics(client, tmp_path)

    # Two LLM calls: analyse, then plan-scenes.
    fake_llm.push(_ANALYSIS)
    fake_llm.push(_plan(2))

    r = client.post(
        f"/api/projects/{pid}/generate",
        # Skip transcription because we're not gating the real whisper
        # model behind the integration flag here.
        json={"run_transcription": False, "target_scene_count": 2},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["project_id"] == pid
    assert body["scene_count"] == 2
    assert body["subtitles_burned"] is False

    # Progress log covers every stage
    stages = [p["stage"] for p in body["progress"]]
    assert stages == [
        "transcribe",
        "analyze",
        "plan-scenes",
        "generate-images",
        "generate-videos",
        "render",
    ]
    statuses = {p["stage"]: p["status"] for p in body["progress"]}
    assert statuses["transcribe"] == "skipped"
    assert statuses["analyze"] == "ok"
    assert statuses["plan-scenes"] == "ok"
    assert statuses["generate-images"] == "ok"
    assert statuses["generate-videos"] == "ok"
    assert statuses["render"] == "ok"

    # Final MP4 on disk
    p = Path(body["path"])
    assert p.exists() and p.suffix == ".mp4"
    info = _probe(p)
    codecs = {s["codec_type"]: s["codec_name"] for s in info["streams"]}
    assert codecs["video"] == "h264"
    assert codecs["audio"] == "aac"


def test_generate_precheck_no_audio_returns_409(client, fake_llm):
    r = client.post("/api/projects", json={"name": "no-audio"})
    pid = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/generate")
    assert r.status_code == 409
    body = r.json()
    assert body["detail"]["stage"] == "precheck"


def test_generate_precheck_no_lyrics_returns_409(client, fake_llm, tmp_path):
    r = client.post(
        "/api/projects",
        json={"name": "no-lyrics", "aspect_ratio": "1:1", "resolution": "320x320"},
    )
    pid = r.json()["id"]
    wav = tmp_path / "a.wav"
    _make_wav(wav, seconds=1.5)
    r = client.post(
        f"/api/projects/{pid}/audio",
        files={"file": ("a.wav", io.BytesIO(wav.read_bytes()), "audio/wav")},
    )
    assert r.status_code == 201

    r = client.post(f"/api/projects/{pid}/generate")
    assert r.status_code == 409
    assert r.json()["detail"]["stage"] == "precheck"


def test_generate_missing_project_returns_404(client, fake_llm):
    r = client.post("/api/projects/does-not-exist/generate")
    assert r.status_code == 404


def test_generate_llm_failure_reports_stage(client, fake_llm, tmp_path):
    """Simulate an LLM returning schema-invalid JSON in the analysis stage."""
    pid = _project_with_audio_and_lyrics(client, tmp_path)
    fake_llm.push({"theme": "x"})  # missing required fields → 500 with stage=analyze
    r = client.post(
        f"/api/projects/{pid}/generate",
        json={"run_transcription": False},
    )
    assert r.status_code == 500
    assert r.json()["detail"]["stage"] == "analyze"
