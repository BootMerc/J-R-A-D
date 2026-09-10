"""Jobs API: create, read, search/filter/paginate, update, duplicate,
close, archive/unarchive. Error handling (404 / 400) is centralized as
global exception handlers in app/main.py, not repeated per endpoint.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.enums import JobStatus
from app.schemas.job import JobCreate, JobListResponse, JobRead, JobUpdate
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_service(db: Session = Depends(get_db)) -> JobService:
    return JobService(db)


@router.post("", response_model=JobRead, status_code=201)
def create_job(payload: JobCreate, service: JobService = Depends(get_job_service)):
    return service.create(payload)


@router.get("", response_model=JobListResponse)
def list_jobs(
    status: Optional[JobStatus] = None,
    search: Optional[str] = None,
    include_archived: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: JobService = Depends(get_job_service),
):
    items, total = service.list(
        status=status, search=search, include_archived=include_archived, skip=skip, limit=limit
    )
    return JobListResponse(items=items, total=total)


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, service: JobService = Depends(get_job_service)):
    job = service.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.patch("/{job_id}", response_model=JobRead)
def update_job(job_id: int, payload: JobUpdate, service: JobService = Depends(get_job_service)):
    return service.update(job_id, payload)


@router.post("/{job_id}/duplicate", response_model=JobRead, status_code=201)
def duplicate_job(job_id: int, service: JobService = Depends(get_job_service)):
    return service.duplicate(job_id)


@router.post("/{job_id}/close", response_model=JobRead)
def close_job(job_id: int, service: JobService = Depends(get_job_service)):
    return service.set_status(job_id, JobStatus.CLOSED)


@router.post("/{job_id}/archive", response_model=JobRead)
def archive_job(job_id: int, service: JobService = Depends(get_job_service)):
    return service.set_archived(job_id, True)


@router.post("/{job_id}/unarchive", response_model=JobRead)
def unarchive_job(job_id: int, service: JobService = Depends(get_job_service)):
    return service.set_archived(job_id, False)
