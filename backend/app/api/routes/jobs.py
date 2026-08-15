"""Job status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.db.models import Job, JobStatus
from backend.app.schemas import JobRead, Message

router = APIRouter(prefix="/jobs")


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/cancel", response_model=Message)
def cancel_job(job_id: str, db: Session = Depends(get_db)) -> Message:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
        raise HTTPException(status_code=409, detail=f"Job already {job.status.value}")
    # Real cancellation signals the running worker; for the skeleton we just
    # flip the DB state so the frontend behaves.
    job.status = JobStatus.CANCELLED
    db.commit()
    return Message(message=f"Job {job_id} cancelled")
