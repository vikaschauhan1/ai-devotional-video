"""Reference-image upload tests."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image


def _png_bytes(size=(64, 64), color=(200, 120, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _make_project(client) -> str:
    r = client.post("/api/projects", json={"name": "R"})
    return r.json()["id"]


def test_upload_reference_and_list(client):
    pid = _make_project(client)
    png = _png_bytes()
    r = client.post(
        f"/api/projects/{pid}/references",
        files={"file": ("shiva.png", io.BytesIO(png), "image/png")},
        params={"label": "shiva reference"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["project_id"] == pid
    assert body["label"] == "shiva reference"
    assert Path(body["path"]).exists()

    r = client.get(f"/api/projects/{pid}/references")
    assert r.status_code == 200
    lst = r.json()
    assert len(lst) == 1
    assert lst[0]["id"] == body["id"]


def test_upload_reference_rejects_bad_extension(client):
    pid = _make_project(client)
    r = client.post(
        f"/api/projects/{pid}/references",
        files={"file": ("bad.exe", io.BytesIO(b"x"), "image/png")},
    )
    assert r.status_code == 415


def test_upload_reference_missing_project(client):
    r = client.post(
        "/api/projects/does-not-exist/references",
        files={"file": ("x.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    assert r.status_code == 404


def test_delete_reference(client):
    pid = _make_project(client)
    r = client.post(
        f"/api/projects/{pid}/references",
        files={"file": ("x.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    ref_id = r.json()["id"]
    r = client.delete(f"/api/projects/{pid}/references/{ref_id}")
    assert r.status_code == 204
    assert client.get(f"/api/projects/{pid}/references").json() == []
