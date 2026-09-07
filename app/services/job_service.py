"""Job business logic — validation and workflow actions on top of the
repository. Raises ValueError for bad input (caught globally -> HTTP 400)
and NotFoundError for missing entities (caught globally -> HTTP 404).
"""

from __future__ import annotations
# ^ This class defines a method named `list` — see destination_repository.py
# for why every class with a `list()` method needs this.

from typing import Optional

from sqlalchemy.orm import Session

from app.database.enums import JobStatus
from app.database.models import Job
from app.database.repositories.job_repository import JobRepository
from app.schemas.job import JobCreate, JobUpdate
from app.services.exceptions import NotFoundError

# Fields copied when duplicating a job. Deliberately excludes id, status,
# archived, created_at, updated_at — a duplicate is always a fresh Draft.
_COPYABLE_FIELDS = [
    "title", "company", "location", "salary_min", "salary_max", "salary_text",
    "employment_type", "experience", "education", "language_requirements",
    "requirements", "responsibilities", "benefits", "working_hours",
    "application_method", "application_url", "contact_phone",
    "contact_whatsapp", "contact_email", "description",
]


class JobService:
    def __init__(self, db: Session):
        self.repo = JobRepository(db)

    @staticmethod
    def _validate_salary(salary_min: Optional[int], salary_max: Optional[int]) -> None:
        if salary_min is not None and salary_max is not None and salary_min > salary_max:
            raise ValueError("salary_min cannot be greater than salary_max")

    def create(self, payload: JobCreate) -> Job:
        data = payload.model_dump()
        self._validate_salary(data.get("salary_min"), data.get("salary_max"))
        return self.repo.create(**data)

    def get(self, job_id: int) -> Optional[Job]:
        return self.repo.get(job_id)

    def list(
        self,
        status: Optional[JobStatus] = None,
        search: Optional[str] = None,
        include_archived: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Job], int]:
        items = self.repo.list(status, search, include_archived, skip, limit)
        total = self.repo.count(status, search, include_archived)
        return items, total

    def update(self, job_id: int, payload: JobUpdate) -> Job:
        data = payload.model_dump(exclude_unset=True)

        if "salary_min" in data or "salary_max" in data:
            existing = self.repo.get(job_id)
            if existing is None:
                raise NotFoundError(f"Job {job_id} not found")
            check_min = data.get("salary_min", existing.salary_min)
            check_max = data.get("salary_max", existing.salary_max)
            self._validate_salary(check_min, check_max)

        job = self.repo.update(job_id, **data)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")
        return job

    def duplicate(self, job_id: int) -> Job:
        original = self.repo.get(job_id)
        if original is None:
            raise NotFoundError(f"Job {job_id} not found")

        data = {field: getattr(original, field) for field in _COPYABLE_FIELDS}
        data["title"] = f"{original.title} (Copy)"
        return self.repo.create(**data)  # status/archived fall back to model defaults

    def set_status(self, job_id: int, status: JobStatus) -> Job:
        job = self.repo.update(job_id, status=status)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")
        return job

    def set_archived(self, job_id: int, archived: bool) -> Job:
        job = self.repo.update(job_id, archived=archived)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")
        return job
