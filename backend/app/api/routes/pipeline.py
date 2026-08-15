"""Pipeline endpoints.

Contracts live here so the frontend can be built in parallel. The actual
audio / lyrics / analyze / plan-scenes / generate implementations are
wired up in later phases; until then the endpoints return HTTP 501.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.db.models import Project
from backend.app.schemas import Message

router = APIRouter(prefix="/projects/{project_id}")


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


@router.post("/audio", response_model=Message)
async def upload_audio(
    project_id: str,
    file: UploadFile,
    db: Session = Depends(get_db),
) -> Message:
    _require_project(db, project_id)
    # File is intentionally not consumed here — real handler lands in Phase 7.
    _ = file
    raise _not_implemented("Audio upload")


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
