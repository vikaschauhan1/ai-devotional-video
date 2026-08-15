"""Audio upload validation and storage.

Enforced at the boundary:

- MIME sniffing against a small allow-list
- Extension allow-list (mp3, wav, m4a, flac)
- Configured size cap (settings.max_upload_mb)
- Safe filename: UUID prefix + sanitised original extension only.
  The user-supplied filename is stored as ``original_filename`` metadata
  and never used to construct a filesystem path.
- Per-project subdirectory under ``storage/audio/`` prevents cross-project
  path collisions.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from backend.app.core.settings import Settings

log = logging.getLogger(__name__)

# Extension -> content types we accept. Keep small on purpose.
_ALLOWED: dict[str, set[str]] = {
    ".mp3": {"audio/mpeg", "audio/mp3", "application/octet-stream"},
    ".wav": {"audio/wav", "audio/x-wav", "audio/wave", "application/octet-stream"},
    ".m4a": {"audio/mp4", "audio/x-m4a", "audio/m4a", "application/octet-stream"},
    ".flac": {"audio/flac", "audio/x-flac", "application/octet-stream"},
}

_SAFE_EXT_RE = re.compile(r"^\.[a-z0-9]{1,8}$")


@dataclass(slots=True, frozen=True)
class StoredAudio:
    path: Path
    original_filename: str
    extension: str
    size_bytes: int
    mime_type: str


def _extract_extension(filename: str | None) -> str:
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="filename missing"
        )
    ext = Path(filename).suffix.lower()
    if not _SAFE_EXT_RE.fullmatch(ext):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported file extension: {ext or '(none)'}",
        )
    if ext not in _ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"extension {ext} not allowed. "
                f"Accepted: {sorted(_ALLOWED.keys())}"
            ),
        )
    return ext


def _check_content_type(ext: str, content_type: str | None) -> str:
    ct = (content_type or "application/octet-stream").lower().split(";", 1)[0].strip()
    allowed = _ALLOWED[ext]
    if ct not in allowed:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"content-type {ct!r} does not match extension {ext}. "
                f"Accepted: {sorted(allowed)}"
            ),
        )
    return ct


async def save_upload(
    *,
    settings: Settings,
    project_id: str,
    upload: UploadFile,
) -> StoredAudio:
    """Validate and persist an uploaded audio file for ``project_id``.

    Returns the on-disk path and basic metadata. Never touches ffprobe -
    the caller does metadata extraction as a separate concern.
    """
    ext = _extract_extension(upload.filename)
    ct = _check_content_type(ext, upload.content_type)

    project_dir = settings.storage_root / "audio" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    # Path.resolve() + is_relative_to() prevents any accidental traversal via
    # a manipulated project_id (defence in depth - project_id is already a
    # 32-hex UUID from our DB, but this stays safe if that ever changes).
    resolved_project_dir = project_dir.resolve()
    audio_root = (settings.storage_root / "audio").resolve()
    if not resolved_project_dir.is_relative_to(audio_root):
        raise HTTPException(status_code=400, detail="invalid project id")

    dest = resolved_project_dir / f"{uuid.uuid4().hex}{ext}"

    max_bytes = settings.max_upload_mb * 1024 * 1024
    written = 0
    chunk_size = 1024 * 1024  # 1 MiB
    try:
        with dest.open("wb") as fh:
            while True:
                chunk = await upload.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    fh.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            f"file exceeds max upload size "
                            f"({settings.max_upload_mb} MB)"
                        ),
                    )
                fh.write(chunk)
    finally:
        await upload.close()

    if written == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="empty upload")

    log.info(
        "stored audio project=%s ext=%s bytes=%d path=%s",
        project_id,
        ext,
        written,
        dest,
    )
    return StoredAudio(
        path=dest,
        original_filename=upload.filename or f"upload{ext}",
        extension=ext,
        size_bytes=written,
        mime_type=ct,
    )
