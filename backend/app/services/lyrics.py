"""Lyrics upload + LLM-driven analysis.

The upload part is trivial storage. The analysis part orchestrates the
LLMEngine: it collects context (lyrics text, optional latest audio
duration and ASR transcript), builds the prompt, gets JSON back, and
validates it against ``LyricsAnalysis`` before persisting.

Because the LLM output is validated by Pydantic before it ever touches
the DB, malformed / hallucinated JSON never corrupts project state.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from agent.prompts import (
    LYRICS_ANALYSIS_JSON_SCHEMA,
    LYRICS_ANALYSIS_SYSTEM,
    build_lyrics_analysis_prompt,
)
from backend.app.core.settings import Settings
from backend.app.db.models import AssetKind, MediaAsset, Project
from backend.app.schemas.lyrics import LyricsAnalysis
from models.llm.base import LLMEngine

log = logging.getLogger(__name__)


class LyricsAnalysisError(RuntimeError):
    pass


def save_lyrics(*, db: Session, project: Project, text: str) -> Project:
    project.lyrics = text.strip()
    db.commit()
    db.refresh(project)
    return project


def _latest_transcript_meta(db: Session, project_id: str) -> tuple[str | None, float | None]:
    asset = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.project_id == project_id,
            MediaAsset.kind == AssetKind.TRANSCRIPT,
        )
        .order_by(MediaAsset.created_at.desc())
        .first()
    )
    if asset is None or not asset.path:
        return None, None
    tp = Path(asset.path)
    if not tp.is_file():
        return None, None
    try:
        data = json.loads(tp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("could not read transcript at %s", tp)
        return None, None
    text = "\n".join(
        (seg.get("text") or "").strip()
        for seg in data.get("segments") or []
        if (seg.get("text") or "").strip()
    ) or None
    dur = data.get("duration")
    duration = float(dur) if isinstance(dur, int | float) else None
    return text, duration


async def analyze_lyrics(
    *,
    db: Session,
    settings: Settings,
    project: Project,
    engine: LLMEngine,
) -> tuple[LyricsAnalysis, MediaAsset]:
    if not project.lyrics or not project.lyrics.strip():
        raise LyricsAnalysisError("project has no lyrics uploaded yet")

    transcript_text, audio_duration = _latest_transcript_meta(db, project.id)
    prompt = build_lyrics_analysis_prompt(
        lyrics=project.lyrics,
        hint_deity=project.deity,
        hint_language=project.language if project.language != "auto" else None,
        audio_duration=audio_duration,
        transcript_hint=transcript_text,
    )

    log.info(
        "running lyrics analysis project=%s engine=%s",
        project.id,
        engine.name,
    )
    raw = await engine.generate_json(
        prompt,
        schema=LYRICS_ANALYSIS_JSON_SCHEMA,
        system=LYRICS_ANALYSIS_SYSTEM,
    )

    try:
        analysis = LyricsAnalysis.model_validate(raw)
    except ValidationError as exc:
        log.warning("LLM produced JSON that failed schema validation: %s", exc)
        raise LyricsAnalysisError(f"LLM returned schema-invalid analysis: {exc}") from exc

    # Persist the analysis alongside other project artefacts.
    dest_dir = (settings.storage_root / "scenes" / project.id).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"lyrics-analysis-{uuid.uuid4().hex}.json"
    dest.write_text(
        analysis.model_dump_json(indent=2), encoding="utf-8"
    )

    asset = MediaAsset(
        project_id=project.id,
        kind=AssetKind.TRANSCRIPT,  # reuse TRANSCRIPT kind; no dedicated bucket yet
        path=str(dest),
        original_filename=None,
        mime_type="application/json",
        size_bytes=dest.stat().st_size,
        meta={
            "kind": "lyrics_analysis",
            "engine": engine.name,
            "language": analysis.language,
            "deity": analysis.deity,
            "section_count": len(analysis.sections),
        },
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return analysis, asset
