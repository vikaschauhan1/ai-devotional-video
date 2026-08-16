"""Placeholder image engine + /generate-images endpoint tests (Phase 11).

The placeholder engine is real code (Pillow-based), so these tests run
it end-to-end. There's no ML download involved.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from backend.app.main import app
from models.llm import get_llm_engine
from models.llm.base import LLMEngine, LLMResponse


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
        {"type": "mukhda", "start": 0.0, "end": 20.0,
         "lyrics": "जय शिव शंभो", "visual_intensity": "high"},
    ],
}


def _plan(n: int = 3) -> dict:
    scenes = []
    for i in range(1, n + 1):
        scenes.append(
            {
                "scene_id": i,
                "start": (i - 1) * 8.0,
                "end": i * 8.0,
                "lyrics": "जय शिव शंभो" if i == 1 else "",
                "prompt": f"Cinematic Shiva scene {i}, Kailash, cinematic",
                "negative_prompt": "text, watermark, low quality",
                "camera": "slow cinematic push-in",
                "lighting": "golden sunrise",
                "mood": "devotional",
                "transition": "crossfade",
            }
        )
    return {
        "theme": "Shiva",
        "aspect_ratio": "9:16",
        "style_preset": "shiva-himalayan",
        "scenes": scenes,
    }


@pytest.fixture()
def fake_llm():
    fake = _QueuedFakeLLM()
    app.dependency_overrides[get_llm_engine] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm_engine, None)


def _prepare(client, fake_llm, n_scenes: int, **project_kwargs) -> str:
    r = client.post(
        "/api/projects",
        json={"name": "Img", "deity": "Shiva", "style": "shiva-himalayan", **project_kwargs},
    )
    pid = r.json()["id"]
    client.post(f"/api/projects/{pid}/lyrics", json={"text": "जय शिव शंभो"})
    fake_llm.push(_ANALYSIS)
    assert client.post(f"/api/projects/{pid}/analyze").status_code == 201
    fake_llm.push(_plan(n_scenes))
    assert client.post(f"/api/projects/{pid}/plan-scenes").status_code == 201
    return pid


def test_generate_images_produces_real_png_per_scene(client, fake_llm):
    pid = _prepare(client, fake_llm, n_scenes=3)

    r = client.post(f"/api/projects/{pid}/generate-images")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["engine"] == "placeholder"
    assert body["scenes_total"] == 3
    assert body["scenes_generated"] == 3
    assert len(body["images"]) == 3

    for entry in body["images"]:
        p = Path(entry["image_path"])
        assert p.exists() and p.suffix == ".png"
        assert entry["size_bytes"] > 0
        with Image.open(p) as im:
            assert im.format == "PNG"
            # 9:16 default → 720x1280
            assert im.size == (720, 1280)

    # A second call is a no-op unless force=true
    r2 = client.post(f"/api/projects/{pid}/generate-images")
    assert r2.status_code == 201
    assert r2.json()["scenes_generated"] == 0

    r3 = client.post(f"/api/projects/{pid}/generate-images", json={"force": True})
    assert r3.status_code == 201
    assert r3.json()["scenes_generated"] == 3


def test_generate_images_uses_correct_dimensions_for_aspect_ratio(client, fake_llm):
    pid = _prepare(client, fake_llm, n_scenes=1, aspect_ratio="16:9")
    r = client.post(f"/api/projects/{pid}/generate-images")
    assert r.status_code == 201
    p = Path(r.json()["images"][0]["image_path"])
    with Image.open(p) as im:
        assert im.size == (1280, 720)

    pid2 = _prepare(client, fake_llm, n_scenes=1, aspect_ratio="1:1")
    r = client.post(f"/api/projects/{pid2}/generate-images")
    assert r.status_code == 201
    p = Path(r.json()["images"][0]["image_path"])
    with Image.open(p) as im:
        assert im.size == (1024, 1024)


def test_generate_images_without_scenes_returns_409(client, fake_llm):
    r = client.post("/api/projects", json={"name": "empty"})
    pid = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/generate-images")
    assert r.status_code == 409
    assert "no scenes" in r.json()["detail"].lower()


def test_generate_images_missing_project_returns_404(client, fake_llm):
    r = client.post("/api/projects/does-not-exist/generate-images")
    assert r.status_code == 404


def test_generate_images_updates_scene_image_path(client, fake_llm):
    pid = _prepare(client, fake_llm, n_scenes=2)
    client.post(f"/api/projects/{pid}/generate-images")

    r = client.get(f"/api/projects/{pid}/scenes")
    scenes = r.json()
    assert len(scenes) == 2
    for s in scenes:
        assert s["image_path"] is not None
        assert Path(s["image_path"]).exists()


def test_placeholder_engine_seed_is_deterministic_by_prompt():
    from models.image.base import ImageGenerationRequest
    from models.image.placeholder import _seed_from

    r1 = ImageGenerationRequest(prompt="Kailash sunrise")
    r2 = ImageGenerationRequest(prompt="Kailash sunrise")
    r3 = ImageGenerationRequest(prompt="Kailash sunset")

    assert _seed_from(r1) == _seed_from(r2)
    assert _seed_from(r1) != _seed_from(r3)
    # explicit seed wins
    r4 = ImageGenerationRequest(prompt="Kailash sunrise", seed=42)
    assert _seed_from(r4) == 42
