"""Request/response schemas for the Jobs API.

JobCreate has no status/archived fields — every new job starts as an
unarchived Draft (see JobService.create). JobUpdate exposes both, since
editing is the general-purpose path for status transitions beyond the
dedicated close/archive quick actions.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.database.enums import JobStatus


class JobBase(BaseModel):
    company: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_text: Optional[str] = None
    employment_type: Optional[str] = None
    experience: Optional[str] = None
    education: Optional[str] = None
    language_requirements: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    benefits: Optional[str] = None
    working_hours: Optional[str] = None
    application_method: Optional[str] = None
    application_url: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_whatsapp: Optional[str] = None
    contact_email: Optional[str] = None
    description: Optional[str] = None


class JobCreate(JobBase):
    title: str


class JobUpdate(JobBase):
    title: Optional[str] = None
    status: Optional[JobStatus] = None
    archived: Optional[bool] = None


class JobRead(JobBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: JobStatus
    archived: bool
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[JobRead]
    total: int
