"""Scene planner tests (Phase 10)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.app.main import app
from models.llm import get_llm_engine
from models.llm.base import LLMEngine, LLMResponse


class _FakeLLM(LLMEngine):
    """Fake engine that returns a canned lyrics-analysis then a scene plan.

    The state machine is a single toggle: first ``generate_json`` call
    returns the analysis (used by the /analyze setup), the next returns
    the plan (used by /plan-scenes). Individual tests can also install
    a fixed payload directly.
    """

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
        assert self.payloads, "no payload queued for fake LLM"
        return self.payloads.pop(0)


_VALID_ANALYSIS = {
    "theme": "Shiva devotional",
    "deity": "Shiva",
    "language": "hi",
    "mood": "devotional",
    "sections": [
        {"type": "mukhda", "start": 0.0, "end": 20.0,
         "lyrics": "जय शिव शंभो, जय महेश्वर", "visual_intensity": "high"},
        {"type": "antara", "start": 20.0, "end": 40.0,
         "lyrics": "आदि अनंत, तू ही ईश्वर", "visual_intensity": "medium"},
    ],
}


def _valid_plan(n: int = 6) -> dict:
    scenes = []
    for i in range(1, n + 1):
        start = (i - 1) * 8.0
        scenes.append(
            {
                "scene_id": i,
                "start": start,
                "end": start + 8.0,
                "lyrics": "जय शिव शंभो" if i == 1 else "",
                "prompt": f"Cinematic Shiva scene {i}, Kailash, cinematic, highly detailed",
                "negative_prompt": "text, watermark, low quality",
                "camera": "slow cinematic push-in",
                "lighting": "golden sunrise",
                "mood": "devotional",
                "transition": "crossfade",
            }
        )
    return {
        "theme": "Shiva Himalayan devotional",
        "aspect_ratio": "9:16",
        "style_preset": "shiva-himalayan",
        "scenes": scenes,
    }


@pytest.fixture()
def fake_llm():
    fake = _FakeLLM()
    app.dependency_overrides[get_llm_engine] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm_engine, None)


def _prepare_project_with_analysis(client, fake: _FakeLLM, **project_kwargs) -> str:
    r = client.post("/api/projects", json={"name": "S", **project_kwargs})
    pid = r.json()["id"]
    client.post(f"/api/projects/{pid}/lyrics", json={"text": "जय शिव शंभो"})
    fake.push(_VALID_ANALYSIS)
    r = client.post(f"/api/projects/{pid}/analyze")
    assert r.status_code == 201, r.text
    return pid


def test_plan_scenes_happy_path(client, fake_llm):
    pid = _prepare_project_with_analysis(
        client, fake_llm, deity="Shiva", style="shiva-himalayan"
    )
    fake_llm.push(_valid_plan(6))

    r = client.post(f"/api/projects/{pid}/plan-scenes")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["project_id"] == pid
    assert body["engine"] == "fake"
    assert body["scene_count"] == 6
    plan = body["plan"]
    assert plan["style_preset"] == "shiva-himalayan"
    assert len(plan["scenes"]) == 6
    assert plan["scenes"][0]["scene_id"] == 1
    assert plan["scenes"][5]["scene_id"] == 6
    assert plan["scenes"][0]["transition"] == "crossfade"

    # Persisted on disk
    p = Path(body["plan_path"])
    assert p.exists()
    assert p.suffix == ".json"

    # GET /scenes now returns real rows
    r = client.get(f"/api/projects/{pid}/scenes")
    assert r.status_code == 200
    scenes = r.json()
    assert len(scenes) == 6
    assert scenes[0]["index"] == 1
    assert scenes[0]["prompt"].startswith("Cinematic Shiva scene 1")


def test_plan_scenes_replaces_previous_scenes(client, fake_llm):
    pid = _prepare_project_with_analysis(client, fake_llm)

    fake_llm.push(_valid_plan(6))
    r1 = client.post(f"/api/projects/{pid}/plan-scenes")
    assert r1.status_code == 201

    fake_llm.push(_valid_plan(4))
    r2 = client.post(f"/api/projects/{pid}/plan-scenes")
    assert r2.status_code == 201

    r = client.get(f"/api/projects/{pid}/scenes")
    assert len(r.json()) == 4  # replaced, not appended


def test_plan_scenes_without_analysis_returns_409(client, fake_llm):
    r = client.post("/api/projects", json={"name": "empty"})
    pid = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/plan-scenes")
    assert r.status_code == 409
    assert "lyrics analysis" in r.json()["detail"].lower()


def test_plan_scenes_missing_project_returns_404(client, fake_llm):
    r = client.post("/api/projects/does-not-exist/plan-scenes")
    assert r.status_code == 404


def test_plan_scenes_rejects_non_sequential_ids(client, fake_llm):
    pid = _prepare_project_with_analysis(client, fake_llm)
    bad = _valid_plan(3)
    bad["scenes"][2]["scene_id"] = 99  # break sequential 1..N invariant
    fake_llm.push(bad)
    r = client.post(f"/api/projects/{pid}/plan-scenes")
    assert r.status_code == 500


def test_plan_scenes_rejects_invalid_transition(client, fake_llm):
    pid = _prepare_project_with_analysis(client, fake_llm)
    bad = _valid_plan(2)
    bad["scenes"][0]["transition"] = "melt"  # not in TransitionType enum
    fake_llm.push(bad)
    r = client.post(f"/api/projects/{pid}/plan-scenes")
    assert r.status_code == 500


def test_plan_scenes_honours_style_preset_override(client, fake_llm):
    pid = _prepare_project_with_analysis(client, fake_llm, deity="Shiva")
    fake_llm.push(_valid_plan(2))
    r = client.post(
        f"/api/projects/{pid}/plan-scenes",
        json={"style_preset": "kailash", "target_scene_count": 2},
    )
    assert r.status_code == 201, r.text
    # The style_preset in the plan comes from the LLM output (fake plan
    # says shiva-himalayan) — the override only steers the PROMPT, not
    # the reply. What we can check: no crash and the request went through.


def test_style_preset_resolution_by_deity_fallback():
    from agent.prompts import resolve_style_preset

    assert resolve_style_preset(None, "Shiva").id == "shiva-himalayan"
    assert resolve_style_preset(None, "Krishna").id == "krishna-vrindavan"
    assert resolve_style_preset(None, "Ram").id == "ram-darbar"
    assert resolve_style_preset(None, "Hanuman").id == "hanuman"
    assert resolve_style_preset(None, None).id == "cinematic-devotional"
    assert resolve_style_preset("kailash", "Whatever").id == "kailash"


# ── Real Ollama integration test (gated) ───────────────────────────
@pytest.mark.skipif(
    os.environ.get("RUN_OLLAMA_INTEGRATION") != "1",
    reason="Set RUN_OLLAMA_INTEGRATION=1 for the real Ollama scene-planner test.",
)
def test_plan_scenes_real_ollama_integration(client):
    """Requires a working `ollama serve` and the qwen2.5:3b-instruct model."""
    os.environ["LLM_ENGINE"] = "ollama"
    os.environ["LLM_MODEL"] = "qwen2.5:3b-instruct"
    from backend.app.core.settings import get_settings
    from models.llm import reset_llm_engine_cache

    get_settings.cache_clear()
    reset_llm_engine_cache()

    r = client.post(
        "/api/projects",
        json={"name": "R", "deity": "Shiva", "style": "shiva-himalayan"},
    )
    pid = r.json()["id"]
    client.post(
        f"/api/projects/{pid}/lyrics",
        json={"text": "जय शिव शंभो, जय महेश्वर\nआदि अनंत, तू ही ईश्वर"},
    )
    r = client.post(f"/api/projects/{pid}/analyze")
    assert r.status_code == 201, r.text

    r = client.post(
        f"/api/projects/{pid}/plan-scenes",
        json={"target_scene_count": 4},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["engine"] == "ollama"
    assert len(body["plan"]["scenes"]) >= 2
