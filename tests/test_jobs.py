"""Async /generate-async endpoint + Job polling tests (Phase 17).

Uses ffmpeg + a FakeLLM the same way test_generate.py does, but exercises
the background-task path. Because uvicorn isn't involved (we're using
FastAPI's TestClient), the asyncio background task is scheduled on the
same event loop that serves the request. We poll ``GET /api/jobs/{id}``
until the job reaches a terminal state.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import time
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
            "name": "AsyncMVP",
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


def _poll_until_terminal(
    client, job_id: str, *, timeout: float = 30.0
) -> dict:
    """Poll GET /api/jobs/{id} until status is COMPLETED / FAILED / CANCELLED."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


def test_generate_async_queues_and_completes(client, fake_llm, tmp_path):
    pid = _project_with_audio_and_lyrics(client, tmp_path)
    fake_llm.push(_ANALYSIS)
    fake_llm.push(_plan(2))

    r = client.post(
        f"/api/projects/{pid}/generate-async",
        json={"run_transcription": False, "target_scene_count": 2},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["project_id"] == pid
    assert body["status"] == "QUEUED"
    job_id = body["job_id"]

    final = _poll_until_terminal(client, job_id)
    assert final["status"] == "COMPLETED", final
    assert final["progress"] == 1.0

    # Result has the stages timeline + the final asset info + elapsed time
    result = final["result"]
    stages = result["stages"]
    assert [s["stage"] for s in stages] == [
        "transcribe",
        "analyze",
        "plan-scenes",
        "generate-images",
        "generate-videos",
        "render",
    ]
    assert result["final"]["scene_count"] == 2
    assert Path(result["final"]["path"]).exists()
    assert result["final"]["url"].startswith("/storage/")
    assert result["elapsed_seconds"] >= 0


def test_generate_async_precheck_no_audio_returns_409(client, fake_llm):
    r = client.post("/api/projects", json={"name": "no-audio"})
    pid = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/generate-async")
    assert r.status_code == 409
    assert r.json()["detail"]["stage"] == "precheck"


def test_generate_async_missing_project_returns_404(client, fake_llm):
    r = client.post("/api/projects/does-not-exist/generate-async")
    assert r.status_code == 404


def test_generate_async_llm_failure_marks_job_failed(client, fake_llm, tmp_path):
    pid = _project_with_audio_and_lyrics(client, tmp_path)
    fake_llm.push({"theme": "x"})  # schema-invalid → LyricsAnalysisError

    r = client.post(
        f"/api/projects/{pid}/generate-async",
        json={"run_transcription": False},
    )
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    final = _poll_until_terminal(client, job_id)
    assert final["status"] == "FAILED", final
    assert final["error"] and "analyze" in final["error"]
    assert final["result"]["failed_stage"] == "analyze"
