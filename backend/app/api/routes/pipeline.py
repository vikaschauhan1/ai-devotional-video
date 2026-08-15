"""Pipeline endpoints.

Contracts live here so the frontend can be built in parallel. Phase 7
implements audio upload + FFmpeg metadata extraction; the remaining
lyrics / analyze / plan-scenes / generate endpoints stay as 501 stubs
until the phases that implement them.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import AssetKind, MediaAsset, Project
from backend.app.schemas import (
    AudioMetadataOut,
    AudioUploadResponse,
    Message,
)
from backend.app.services.audio import save_upload
from pipeline.audio_analysis import AudioAnalysisError, probe

router = APIRouter(prefix="/projects/{project_id}")
log = logging.getLogger(__name__)


def _require_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _not_implemented(feature: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"{feature} is not implemented yet (see project phase plan).",
    )


@router.post(
    "/audio",
    response_model=AudioUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_audio(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AudioUploadResponse:
    project = _require_project(db, project_id)

    stored = await save_upload(
        settings=settings, project_id=project.id, upload=file
    )

    try:
        meta = probe(stored.path)
    except AudioAnalysisError as exc:
        # File was invalid audio - clean up and 400 back.
        stored.path.unlink(missing_ok=True)
        log.warning("rejecting upload for project=%s: %s", project.id, exc)
        raise HTTPException(status_code=400, detail=f"audio invalid: {exc}") from exc

    asset = MediaAsset(
        project_id=project.id,
        kind=AssetKind.AUDIO,
        path=str(stored.path),
        original_filename=stored.original_filename,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        meta=meta.to_dict(),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    return AudioUploadResponse(
        asset_id=asset.id,
        project_id=project.id,
        path=str(stored.path),
        original_filename=stored.original_filename,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        metadata=AudioMetadataOut(**meta.to_dict()),
    )


@router.post("/lyrics", response_model=Message)
def upload_lyrics(project_id: str, db: Session = Depends(get_db)) -> Message:
    _require_project(db, project_id)
    raise _not_implemented("Lyrics upload")


@router.post("/analyze", response_model=Message)
def analyze(project_id: str, db: Session = Depends(get_db)) -> Message:
    _require_project(db, project_id)
    raise _not_implemented("Audio + lyrics analysis")


@router.post("/plan-scenes", response_model=Message)
def plan_scenes(project_id: str, db: Session = Depends(get_db)) -> Message:
    _require_project(db, project_id)
    raise _not_implemented("Scene planning")


@router.post("/generate", response_model=Message)
def generate(project_id: str, db: Session = Depends(get_db)) -> Message:
    _require_project(db, project_id)
    raise _not_implemented("End-to-end generation")


@router.get("/render", response_model=Message)
def render_status(project_id: str, db: Session = Depends(get_db)) -> Message:
    _require_project(db, project_id)
    raise _not_implemented("Render status")
