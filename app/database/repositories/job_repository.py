"""Job repository: SQLAlchemy queries only. Validation and business rules
live in app/services/job_service.py, not here.
"""

from __future__ import annotations
# ^ This class defines a method named `list`, which shadows the builtin for
# any later method's annotations in the same class body (not currently
# triggered here, but see destination_repository.py for what happens when
# it is — keeping this everywhere a `list()` method exists, preventively).

from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database.enums import JobStatus
from app.database.models import Job


class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **fields) -> Job:
        job = Job(**fields)
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get(self, job_id: int) -> Optional[Job]:
        return self.db.get(Job, job_id)

    def _filtered_query(
        self,
        status: Optional[JobStatus] = None,
        search: Optional[str] = None,
        include_archived: bool = False,
    ):
        query = self.db.query(Job)
        if not include_archived:
            query = query.filter(Job.archived.is_(False))
        if status is not None:
            query = query.filter(Job.status == status)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Job.title.ilike(pattern),
                    Job.company.ilike(pattern),
                    Job.location.ilike(pattern),
                )
            )
        return query

    def list(
        self,
        status: Optional[JobStatus] = None,
        search: Optional[str] = None,
        include_archived: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Job]:
        query = self._filtered_query(status, search, include_archived)
        return query.order_by(Job.created_at.desc()).offset(skip).limit(limit).all()

    def count(
        self,
        status: Optional[JobStatus] = None,
        search: Optional[str] = None,
        include_archived: bool = False,
    ) -> int:
        query = self._filtered_query(status, search, include_archived)
        return query.with_entities(func.count(Job.id)).scalar()

    def update(self, job_id: int, **fields) -> Optional[Job]:
        job = self.get(job_id)
        if job is None:
            return None
        for key, value in fields.items():
            setattr(job, key, value)
        self.db.commit()
        self.db.refresh(job)
        return job
