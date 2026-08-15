"""Scene listing endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.db.models import Project, Scene
from backend.app.schemas import SceneRead

router = APIRouter(prefix="/projects/{project_id}")


@router.get("/scenes", response_model=list[SceneRead])
def list_scenes(project_id: str, db: Session = Depends(get_db)) -> list[Scene]:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return db.query(Scene).filter(Scene.project_id == project_id).order_by(Scene.index.asc()).all()
