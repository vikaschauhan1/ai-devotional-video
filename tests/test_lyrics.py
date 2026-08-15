"""Lyrics upload + LLM analysis tests.

The fast suite injects a fake LLMEngine via FastAPI dependency override
so no real Ollama traffic happens. A gated integration test hits real
Ollama when ``RUN_OLLAMA_INTEGRATION=1``.
"""

from __future__ import annotations

import os

import pytest

from backend.app.main import app
from models.llm import get_llm_engine
from models.llm.base import LLMEngine, LLMResponse


class _FakeLLM(LLMEngine):
    name = "fake"

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    async def generate(self, prompt, *, system=None, temperature=0.4, max_tokens=1024):
        return LLMResponse(text="[fake]")

    async def generate_json(
        self, prompt, *, schema, system=None, temperature=0.2, max_tokens=2048
    ):
        return self.payload


_VALID_ANALYSIS = {
    "theme": "Shiva devotional",
    "deity": "Shiva",
    "language": "hi",
    "mood": "devotional",
    "sections": [
        {
            "type": "mukhda",
            "start": 0.0,
            "end": 20.0,
            "lyrics": "जय शिव शंभो, जय महेश्वर",
            "visual_intensity": "high",
        },
        {
            "type": "antara",
            "start": 20.0,
            "end": 40.0,
            "lyrics": "आदि अनंत, तू ही ईश्वर",
            "visual_intensity": "medium",
        },
    ],
}


@pytest.fixture()
def override_llm():
    """Yield a helper that installs a FakeLLM producing the given payload."""

    def _install(payload: dict) -> _FakeLLM:
        fake = _FakeLLM(payload)
        app.dependency_overrides[get_llm_engine] = lambda: fake
        return fake

    yield _install
    app.dependency_overrides.pop(get_llm_engine, None)


def _create_project(client, **kwargs) -> str:
    r = client.post("/api/projects", json={"name": "L", **kwargs})
    assert r.status_code == 201
    return r.json()["id"]


def test_upload_lyrics_saves_to_project(client):
    pid = _create_project(client)
    text = "जय शिव शंभो, जय महेश्वर\nआदि अनंत, तू ही ईश्वर"
    r = client.post(f"/api/projects/{pid}/lyrics", json={"text": text})
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] == pid
    assert body["lyrics_length"] == len(text.strip())

    # Confirmed on the project resource itself
    r = client.get(f"/api/projects/{pid}")
    assert r.json()["lyrics"] == text.strip()


def test_upload_lyrics_missing_project_returns_404(client):
    r = client.post("/api/projects/does-not-exist/lyrics", json={"text": "hi"})
    assert r.status_code == 404


def test_upload_lyrics_rejects_empty_text(client):
    pid = _create_project(client)
    r = client.post(f"/api/projects/{pid}/lyrics", json={"text": ""})
    assert r.status_code == 422


def test_analyze_returns_structured_analysis(client, override_llm):
    override_llm(_VALID_ANALYSIS)
    pid = _create_project(client, deity="Shiva", language="hi")
    client.post(
        f"/api/projects/{pid}/lyrics",
        json={"text": "जय शिव शंभो, जय महेश्वर\nआदि अनंत, तू ही ईश्वर"},
    )

    r = client.post(f"/api/projects/{pid}/analyze")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["project_id"] == pid
    assert body["engine"] == "fake"
    a = body["analysis"]
    assert a["deity"] == "Shiva"
    assert a["language"] == "hi"
    assert len(a["sections"]) == 2
    assert a["sections"][0]["type"] == "mukhda"
    assert a["sections"][0]["visual_intensity"] == "high"

    # JSON was persisted on disk under storage/scenes/<pid>/
    from pathlib import Path

    p = Path(body["analysis_path"])
    assert p.exists()
    assert p.suffix == ".json"


def test_analyze_without_lyrics_returns_409(client, override_llm):
    override_llm(_VALID_ANALYSIS)
    pid = _create_project(client)
    r = client.post(f"/api/projects/{pid}/analyze")
    assert r.status_code == 409


def test_analyze_missing_project_returns_404(client, override_llm):
    override_llm(_VALID_ANALYSIS)
    r = client.post("/api/projects/does-not-exist/analyze")
    assert r.status_code == 404


def test_analyze_rejects_schema_invalid_llm_output(client, override_llm):
    # LLM returns something missing required fields -> service raises
    # LyricsAnalysisError -> 500
    override_llm({"theme": "x"})  # missing language, mood, sections
    pid = _create_project(client)
    client.post(f"/api/projects/{pid}/lyrics", json={"text": "abc"})
    r = client.post(f"/api/projects/{pid}/analyze")
    assert r.status_code == 500


def test_analyze_rejects_invalid_section_type(client, override_llm):
    bad = dict(_VALID_ANALYSIS)
    bad["sections"] = [
        {
            "type": "chorus",  # not in allowed StrEnum
            "start": 0.0,
            "end": 1.0,
            "lyrics": "x",
            "visual_intensity": "medium",
        }
    ]
    override_llm(bad)
    pid = _create_project(client)
    client.post(f"/api/projects/{pid}/lyrics", json={"text": "abc"})
    r = client.post(f"/api/projects/{pid}/analyze")
    assert r.status_code == 500


# ── Real Ollama integration test (gated) ───────────────────────────
@pytest.mark.skipif(
    os.environ.get("RUN_OLLAMA_INTEGRATION") != "1",
    reason="Set RUN_OLLAMA_INTEGRATION=1 to hit a running ollama with the pulled model.",
)
def test_analyze_real_ollama_integration(client):
    """Requires a running `ollama serve` and the qwen2.5:3b-instruct model."""
    import os as _os

    _os.environ["LLM_ENGINE"] = "ollama"
    _os.environ["LLM_MODEL"] = "qwen2.5:3b-instruct"
    from backend.app.core.settings import get_settings
    from models.llm import reset_llm_engine_cache

    get_settings.cache_clear()
    reset_llm_engine_cache()

    pid = _create_project(client, deity="Shiva", language="hi")
    client.post(
        f"/api/projects/{pid}/lyrics",
        json={"text": "जय शिव शंभो, जय महेश्वर\nआदि अनंत, तू ही ईश्वर"},
    )
    r = client.post(f"/api/projects/{pid}/analyze")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["engine"] == "ollama"
    a = body["analysis"]
    assert isinstance(a["sections"], list) and len(a["sections"]) >= 1
    assert a["language"] in {"hi", "sa"}
