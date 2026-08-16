"""Reference-image uploads (Phase 10 finish)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from backend.app.core.settings import Settings

_ALLOWED_IMAGE_TYPES: dict[str, set[str]] = {
    ".png":  {"image/png", "application/octet-stream"},
    ".jpg":  {"image/jpeg", "application/octet-stream"},
    ".jpeg": {"image/jpeg", "application/octet-stream"},
    ".webp": {"image/webp", "application/octet-stream"},
}
_SAFE_EXT = re.compile(r"^\.[a-z0-9]{1,8}$")


@dataclass(slots=True, frozen=True)
class StoredReference:
    path: Path
    original_filename: str
    extension: str
    size_bytes: int
    mime_type: str


def _ext(filename: str | None) -> str:
    if not filename:
        raise HTTPException(400, "filename missing")
    ext = Path(filename).suffix.lower()
    if not _SAFE_EXT.fullmatch(ext) or ext not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            415,
            f"extension {ext or '(none)'} not allowed; "
            f"accepted: {sorted(_ALLOWED_IMAGE_TYPES)}",
        )
    return ext


def _check_ct(ext: str, ct: str | None) -> str:
    v = (ct or "application/octet-stream").lower().split(";", 1)[0].strip()
    if v not in _ALLOWED_IMAGE_TYPES[ext]:
        raise HTTPException(415, f"content-type {v!r} does not match {ext}")
    return v


async def save_reference(
    *,
    settings: Settings,
    project_id: str,
    upload: UploadFile,
    label: str | None = None,
) -> StoredReference:
    ext = _ext(upload.filename)
    ct = _check_ct(ext, upload.content_type)

    base = (settings.storage_root / "references" / project_id).resolve()
    references_root = (settings.storage_root / "references").resolve()
    if not base.is_relative_to(references_root):
        raise HTTPException(400, "invalid project id")
    base.mkdir(parents=True, exist_ok=True)

    stem = re.sub(r"[^a-z0-9-]+", "-", (label or "ref").lower()).strip("-") or "ref"
    dest = base / f"{stem}-{uuid.uuid4().hex}{ext}"

    max_bytes = settings.max_upload_mb * 1024 * 1024
    written = 0
    try:
        with dest.open("wb") as fh:
            while chunk := await upload.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    fh.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        f"file exceeds {settings.max_upload_mb} MB",
                    )
                fh.write(chunk)
    finally:
        await upload.close()

    if written == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "empty upload")

    return StoredReference(
        path=dest,
        original_filename=upload.filename or f"upload{ext}",
        extension=ext,
        size_bytes=written,
        mime_type=ct,
    )
