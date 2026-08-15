"""API tests for the Phase-5 backend skeleton."""

from __future__ import annotations


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert set(body["engines"].keys()) >= {"llm", "image", "video", "lipsync", "tts", "asr"}


def test_project_crud_roundtrip(client):
    # Create
    payload = {
        "name": "Shiva bhajan",
        "deity": "Shiva",
        "style": "shiva-himalayan",
        "language": "hi",
        "aspect_ratio": "9:16",
        "lip_sync_enabled": False,
    }
    r = client.post("/api/projects", json=payload)
    assert r.status_code == 201, r.text
    proj = r.json()
    pid = proj["id"]
    assert len(pid) == 32
    assert proj["deity"] == "Shiva"

    # Read
    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Shiva bhajan"

    # List
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert any(p["id"] == pid for p in r.json())

    # Update
    r = client.patch(f"/api/projects/{pid}", json={"lip_sync_enabled": True})
    assert r.status_code == 200
    assert r.json()["lip_sync_enabled"] is True

    # Delete
    r = client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204

    # Now missing
    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 404


def test_project_create_validates_aspect_ratio(client):
    r = client.post("/api/projects", json={"name": "x", "aspect_ratio": "4:3"})
    assert r.status_code == 422


def test_pipeline_endpoints_return_501_but_not_before_project_check(client):
    # Nonexistent project -> 404 (not 501) — verify with an unimplemented endpoint
    r = client.post("/api/projects/does-not-exist/plan-scenes")
    assert r.status_code == 404

    # Real project -> 501 for still-unimplemented pipeline stages.
    # /audio, /lyrics, /transcribe and /analyze are implemented in later
    # phases and have their own tests.
    r = client.post("/api/projects", json={"name": "t"})
    pid = r.json()["id"]

    for path in ("plan-scenes", "generate"):
        r = client.post(f"/api/projects/{pid}/{path}")
        assert r.status_code == 501, f"{path}: {r.status_code}"


def test_scenes_empty_for_new_project(client):
    r = client.post("/api/projects", json={"name": "s"})
    pid = r.json()["id"]
    r = client.get(f"/api/projects/{pid}/scenes")
    assert r.status_code == 200
    assert r.json() == []


def test_job_not_found(client):
    r = client.get("/api/jobs/deadbeef")
    assert r.status_code == 404
