"""PostTemplate repository: SQLAlchemy queries only. Rendering logic lives
in app/utils/template_rendering.py; validation/preview orchestration lives
in app/services/template_service.py.
"""

from __future__ import annotations
# ^ This class has a `list()` method — see destination_repository.py
# (Phase 3, section 13 of PROJECT_STATUS.md) for why this import is
# required in every repository/service class shaped this way.

from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database.enums import Platform
from app.database.models import PostTemplate


class TemplateRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **fields) -> PostTemplate:
        template = PostTemplate(**fields)
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    def get(self, template_id: int) -> Optional[PostTemplate]:
        return self.db.get(PostTemplate, template_id)

    def _filtered_query(
        self,
        platform: Optional[Platform] = None,
        language: Optional[str] = None,
        active: Optional[bool] = None,
        search: Optional[str] = None,
    ):
        query = self.db.query(PostTemplate)
        if platform is not None:
            query = query.filter(PostTemplate.platform == platform)
        if language:
            query = query.filter(PostTemplate.language == language)
        if active is not None:
            query = query.filter(PostTemplate.active == active)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(PostTemplate.name.ilike(pattern), PostTemplate.template_text.ilike(pattern))
            )
        return query

    def list(
        self,
        platform: Optional[Platform] = None,
        language: Optional[str] = None,
        active: Optional[bool] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: Optional[int] = 50,
    ) -> list[PostTemplate]:
        query = self._filtered_query(platform, language, active, search)
        query = query.order_by(PostTemplate.created_at.desc()).offset(skip)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def count(
        self,
        platform: Optional[Platform] = None,
        language: Optional[str] = None,
        active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> int:
        query = self._filtered_query(platform, language, active, search)
        return query.with_entities(func.count(PostTemplate.id)).scalar()

    def update(self, template_id: int, **fields) -> Optional[PostTemplate]:
        template = self.get(template_id)
        if template is None:
            return None
        for key, value in fields.items():
            setattr(template, key, value)
        self.db.commit()
        self.db.refresh(template)
        return template

    def delete(self, template_id: int) -> bool:
        template = self.get(template_id)
        if template is None:
            return False
        self.db.delete(template)
        self.db.commit()
        return True
