"""Template business logic. The one thing beyond plain CRUD: preview(),
which is the first place a service needs both TemplateRepository and
JobRepository — rendering a template genuinely requires both.
"""

from __future__ import annotations
# ^ This class has a `list()` method — see destination_repository.py.

from typing import Optional

from sqlalchemy.orm import Session

from app.database.enums import Platform
from app.database.models import PostTemplate
from app.database.repositories.job_repository import JobRepository
from app.database.repositories.template_repository import TemplateRepository
from app.schemas.template import TemplateCreate, TemplateUpdate
from app.services.exceptions import NotFoundError
from app.utils.template_rendering import job_to_variables, render_template, unknown_variables


class TemplateService:
    def __init__(self, db: Session):
        self.repo = TemplateRepository(db)
        self.job_repo = JobRepository(db)

    def create(self, payload: TemplateCreate) -> PostTemplate:
        return self.repo.create(**payload.model_dump())

    def get(self, template_id: int) -> Optional[PostTemplate]:
        return self.repo.get(template_id)

    def list(
        self,
        platform: Optional[Platform] = None,
        language: Optional[str] = None,
        active: Optional[bool] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[PostTemplate], int]:
        items = self.repo.list(
            platform=platform, language=language, active=active, search=search, skip=skip, limit=limit
        )
        total = self.repo.count(platform=platform, language=language, active=active, search=search)
        return items, total

    def update(self, template_id: int, payload: TemplateUpdate) -> PostTemplate:
        data = payload.model_dump(exclude_unset=True)
        template = self.repo.update(template_id, **data)
        if template is None:
            raise NotFoundError(f"Template {template_id} not found")
        return template

    def delete(self, template_id: int) -> None:
        if not self.repo.delete(template_id):
            raise NotFoundError(f"Template {template_id} not found")

    def set_active(self, template_id: int, active: bool) -> PostTemplate:
        template = self.repo.update(template_id, active=active)
        if template is None:
            raise NotFoundError(f"Template {template_id} not found")
        return template

    def preview(self, template_id: int, job_id: int) -> dict:
        template = self.repo.get(template_id)
        if template is None:
            raise NotFoundError(f"Template {template_id} not found")

        job = self.job_repo.get(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")

        variables = job_to_variables(job)
        return {
            "rendered_text": render_template(template.template_text, variables),
            "unknown_variables": unknown_variables(template.template_text),
        }
