"""Transcription orchestration: pick latest audio, run whisper, persist."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import AssetKind, MediaAsset, Project
from pipeline.transcription import (
    TranscriptionError,
    TranscriptionResult,
    transcribe,
)

log = logging.getLogger(__name__)


def _latest_audio_asset(db: Session, project_id: str) -> MediaAsset | None:
    return (
        db.query(MediaAsset)
        .filter(
            MediaAsset.project_id == project_id,
            MediaAsset.kind == AssetKind.AUDIO,
        )
        .order_by(MediaAsset.created_at.desc())
        .first()
    )


def transcribe_project(
    *,
    db: Session,
    settings: Settings,
    project: Project,
    language: str | None,
    beam_size: int,
    vad_filter: bool,
) -> tuple[MediaAsset, MediaAsset, TranscriptionResult]:
    """Transcribe the most recent audio asset for the project.

    Returns ``(audio_asset, transcript_asset, result)``. Raises
    ``TranscriptionError`` if audio is missing or Whisper fails.
    """
    audio = _latest_audio_asset(db, project.id)
    if audio is None:
        raise TranscriptionError("no audio uploaded for this project yet")

    audio_path = Path(audio.path)
    if not audio_path.is_file():
        raise TranscriptionError(f"audio file missing on disk: {audio_path}")

    log.info(
        "transcribing project=%s audio_asset=%s model=%s",
        project.id,
        audio.id,
        settings.whisper_model,
    )
    result = transcribe(
        audio_path,
        model_name=settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        language=language,
        beam_size=beam_size,
        vad_filter=vad_filter,
    )

    # Persist transcript JSON alongside the other project files.
    transcripts_dir = (settings.storage_root / "transcripts" / project.id).resolve()
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    dest = transcripts_dir / f"{uuid.uuid4().hex}.json"
    payload = {
        "audio_asset_id": audio.id,
        "project_id": project.id,
        **result.to_dict(),
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    transcript_asset = MediaAsset(
        project_id=project.id,
        kind=AssetKind.TRANSCRIPT,
        path=str(dest),
        original_filename=None,
        mime_type="application/json",
        size_bytes=dest.stat().st_size,
        meta={
            "audio_asset_id": audio.id,
            "language": result.language,
            "language_probability": result.language_probability,
            "duration": result.duration,
            "model": result.model,
            "segment_count": len(result.segments),
        },
    )
    db.add(transcript_asset)
    db.commit()
    db.refresh(transcript_asset)

    return audio, transcript_asset, result
