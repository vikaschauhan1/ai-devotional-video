"""Procedural video engine + /generate-videos endpoint tests (Phase 12/13).

The procedural engine calls real FFmpeg — no ML. Scenes generated in
the test suite are deliberately tiny (1.0s, 320x240) so ffmpeg runs in
sub-second per clip.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

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


def _plan(n: int = 2, duration: float = 1.0) -> dict:
    scenes = []
    for i in range(1, n + 1):
        scenes.append(
            {
                "scene_id": i,
                "start": (i - 1) * duration,
                "end": i * duration,
                "lyrics": "जय शिव शंभो" if i == 1 else "",
                "prompt": f"Cinematic Shiva scene {i}",
                "negative_prompt": "text, watermark",
                "camera": "slow push-in" if i % 2 else "pan-right",
                "lighting": "golden sunrise",
                "mood": "devotional",
                "transition": "crossfade",
            }
        )
    return {
        "theme": "Shiva",
        "aspect_ratio": "1:1",  # 1:1 keeps tests small and equal-sided
        "style_preset": "shiva-himalayan",
        "scenes": scenes,
    }


@pytest.fixture()
def fake_llm():
    fake = _QueuedFakeLLM()
    app.dependency_overrides[get_llm_engine] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm_engine, None)


def _prepare_with_images(
    client, fake_llm, n_scenes: int, aspect: str = "1:1"
) -> str:
    """Create project → lyrics → analyze → plan-scenes → generate-images."""
    r = client.post(
        "/api/projects",
        json={
            "name": "Vid",
            "deity": "Shiva",
            "style": "shiva-himalayan",
            "aspect_ratio": aspect,
            "resolution": "320x320" if aspect == "1:1" else "auto",
        },
    )
    pid = r.json()["id"]
    client.post(f"/api/projects/{pid}/lyrics", json={"text": "जय शिव शंभो"})
    fake_llm.push(_ANALYSIS)
    assert client.post(f"/api/projects/{pid}/analyze").status_code == 201
    fake_llm.push(_plan(n_scenes))
    assert client.post(f"/api/projects/{pid}/plan-scenes").status_code == 201
    r = client.post(f"/api/projects/{pid}/generate-images")
    assert r.status_code == 201, r.text
    return pid


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
            "-select_streams",
            "v:0",
            str(path),
        ],
        text=True,
    )
    return json.loads(out)


def test_generate_videos_produces_mp4_per_scene(client, fake_llm):
    pid = _prepare_with_images(client, fake_llm, n_scenes=2, aspect="1:1")

    r = client.post(
        f"/api/projects/{pid}/generate-videos",
        json={"fps": 24},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["engine"] == "procedural"
    assert body["scenes_total"] == 2
    assert body["scenes_generated"] == 2

    for entry in body["videos"]:
        p = Path(entry["video_path"])
        assert p.exists() and p.suffix == ".mp4"
        assert entry["size_bytes"] > 0
        info = _probe(p)
        stream = info["streams"][0]
        assert stream["codec_name"] == "h264"
        assert stream["pix_fmt"] == "yuv420p"
        assert int(stream["width"]) == 320
        assert int(stream["height"]) == 320
        assert float(info["format"]["duration"]) > 0.5

    # Idempotent by default
    r2 = client.post(f"/api/projects/{pid}/generate-videos")
    assert r2.status_code == 201
    assert r2.json()["scenes_generated"] == 0

    # force=true re-renders
    r3 = client.post(f"/api/projects/{pid}/generate-videos", json={"force": True})
    assert r3.status_code == 201
    assert r3.json()["scenes_generated"] == 2


def test_generate_videos_updates_scene_video_path(client, fake_llm):
    pid = _prepare_with_images(client, fake_llm, n_scenes=2)
    r = client.post(f"/api/projects/{pid}/generate-videos")
    assert r.status_code == 201

    scenes = client.get(f"/api/projects/{pid}/scenes").json()
    for s in scenes:
        assert s["video_path"] is not None
        assert Path(s["video_path"]).exists()


def test_generate_videos_without_images_returns_409(client, fake_llm):
    """Scenes exist but their image_path is empty → 409."""
    r = client.post(
        "/api/projects",
        json={"name": "N", "aspect_ratio": "1:1", "resolution": "320x320"},
    )
    pid = r.json()["id"]
    client.post(f"/api/projects/{pid}/lyrics", json={"text": "abc"})
    fake_llm.push(_ANALYSIS)
    assert client.post(f"/api/projects/{pid}/analyze").status_code == 201
    fake_llm.push(_plan(1))
    assert client.post(f"/api/projects/{pid}/plan-scenes").status_code == 201
    # Skip /generate-images on purpose
    r = client.post(f"/api/projects/{pid}/generate-videos")
    assert r.status_code == 409
    assert "no image" in r.json()["detail"].lower()


def test_generate_videos_without_scenes_returns_409(client):
    r = client.post("/api/projects", json={"name": "empty"})
    pid = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/generate-videos")
    assert r.status_code == 409
    assert "no scenes" in r.json()["detail"].lower()


def test_generate_videos_missing_project_returns_404(client):
    r = client.post("/api/projects/does-not-exist/generate-videos")
    assert r.status_code == 404


def test_procedural_engine_requires_image_path(tmp_path):
    """Bypass the service and call the engine directly with no image."""
    import asyncio

    from models.video.base import VideoGenerationRequest
    from models.video.procedural import (
        ProceduralVideoEngine,
        ProceduralVideoError,
    )

    engine = ProceduralVideoEngine(storage_root=tmp_path)

    async def run():
        with pytest.raises(ProceduralVideoError, match="image_path"):
            await engine.generate(
                VideoGenerationRequest(prompt="x", duration=1.0)
            )

    asyncio.run(run())


def test_procedural_engine_rejects_missing_image(tmp_path):
    import asyncio

    from models.video.base import VideoGenerationRequest
    from models.video.procedural import (
        ProceduralVideoEngine,
        ProceduralVideoError,
    )

    engine = ProceduralVideoEngine(storage_root=tmp_path)

    async def run():
        with pytest.raises(ProceduralVideoError, match="image not found"):
            await engine.generate(
                VideoGenerationRequest(
                    prompt="x",
                    duration=1.0,
                    image_path=tmp_path / "does-not-exist.png",
                )
            )

    asyncio.run(run())


def test_procedural_engine_generates_real_mp4_directly(tmp_path):
    """Direct-call sanity check without the whole pipeline."""
    import asyncio

    from models.video.base import VideoGenerationRequest
    from models.video.procedural import ProceduralVideoEngine

    src = tmp_path / "src.png"
    Image.new("RGB", (256, 256), (200, 120, 40)).save(src)

    engine = ProceduralVideoEngine(storage_root=tmp_path)

    async def run():
        return await engine.generate(
            VideoGenerationRequest(
                prompt="test",
                duration=0.8,
                image_path=src,
                width=256,
                height=256,
                fps=24,
                camera_hint="pan-left",
                extras={"scene_id": "test", "project_id": "unit"},
            )
        )

    res = asyncio.run(run())
    assert res.path.exists()
    assert res.path.suffix == ".mp4"
    info = _probe(res.path)
    assert info["streams"][0]["codec_name"] == "h264"
    assert float(info["format"]["duration"]) > 0.4
