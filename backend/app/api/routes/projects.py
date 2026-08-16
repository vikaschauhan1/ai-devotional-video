"""Project CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from agent.lyrics_presets import SAMPLE_PRESETS, get_preset
from backend.app.api.deps import get_db
from backend.app.db.models import Project
from backend.app.schemas import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects")


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/presets", response_model=list[dict])
def list_presets() -> list[dict]:
    """List bundled sample-bhajan presets."""
    return [
        {k: v for k, v in p.items() if k != "lyrics"}
        for p in SAMPLE_PRESETS.values()
    ]


@router.post(
    "/from-preset/{preset_id}",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
def create_project_from_preset(
    preset_id: str, db: Session = Depends(get_db)
) -> Project:
    try:
        preset = get_preset(preset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    project = Project(
        name=preset["name"],
        deity=preset["deity"],
        style=preset["style"],
        aspect_ratio=preset["aspect_ratio"],
        language=preset["language"],
        lyrics=preset["lyrics"],
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db), limit: int = 50, offset: int = 0) -> list[Project]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    return db.query(Project).order_by(Project.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db)) -> None:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
