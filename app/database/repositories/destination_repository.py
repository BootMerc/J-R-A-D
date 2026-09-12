"""Destination repository: SQLAlchemy queries only. Validation, CSV import/
export, and other business rules live in app/services/destination_service.py.

Tag handling: `tag_names` is a plain list of strings, not Tag objects — the
repository resolves each name to an existing Tag (case-insensitive match) or
creates a new one. Callers never construct Tag rows themselves.
"""

from __future__ import annotations
# ^ Required: this class defines a method literally named `list`, which
# shadows the builtin for every method defined after it in the class body
# (annotations are evaluated at class-definition time). Deferring
# annotation evaluation avoids it. Same reason this import is in
# job_repository.py, job_service.py, and destination_service.py — keep it
# in any future repository/service class that has a `list()` method too.

from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database.enums import Platform
from app.database.models import Destination, Tag


class DestinationRepository:
    def __init__(self, db: Session):
        self.db = db

    def _resolve_tags(self, tag_names: list[str]) -> list[Tag]:
        tags: list[Tag] = []
        seen_lower: set[str] = set()
        for raw_name in tag_names:
            name = raw_name.strip()
            if not name or name.lower() in seen_lower:
                continue
            seen_lower.add(name.lower())
            tag = self.db.query(Tag).filter(Tag.name.ilike(name)).first()
            if tag is None:
                tag = Tag(name=name)
                self.db.add(tag)
                self.db.flush()  # assign an id without committing yet
            tags.append(tag)
        return tags

    def create(self, tag_names: Optional[list[str]] = None, **fields) -> Destination:
        destination = Destination(**fields)
        if tag_names:
            destination.tags = self._resolve_tags(tag_names)
        self.db.add(destination)
        self.db.commit()
        self.db.refresh(destination)
        return destination

    def get(self, destination_id: int) -> Optional[Destination]:
        return self.db.get(Destination, destination_id)

    def _filtered_query(
        self,
        platform: Optional[Platform] = None,
        category: Optional[str] = None,
        location: Optional[str] = None,
        language: Optional[str] = None,
        tag: Optional[str] = None,
        active: Optional[bool] = None,
        search: Optional[str] = None,
    ):
        query = self.db.query(Destination)
        if platform is not None:
            query = query.filter(Destination.platform == platform)
        if category:
            query = query.filter(Destination.category == category)
        if location:
            query = query.filter(Destination.location == location)
        if language:
            query = query.filter(Destination.language == language)
        if active is not None:
            query = query.filter(Destination.active == active)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Destination.name.ilike(pattern),
                    Destination.url.ilike(pattern),
                    Destination.notes.ilike(pattern),
                )
            )
        if tag:
            query = query.join(Destination.tags).filter(Tag.name.ilike(tag))
        return query

    def list(
        self,
        platform: Optional[Platform] = None,
        category: Optional[str] = None,
        location: Optional[str] = None,
        language: Optional[str] = None,
        tag: Optional[str] = None,
        active: Optional[bool] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: Optional[int] = 50,
    ) -> list[Destination]:
        query = self._filtered_query(platform, category, location, language, tag, active, search)
        query = query.order_by(Destination.created_at.desc()).offset(skip)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def count(
        self,
        platform: Optional[Platform] = None,
        category: Optional[str] = None,
        location: Optional[str] = None,
        language: Optional[str] = None,
        tag: Optional[str] = None,
        active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> int:
        query = self._filtered_query(platform, category, location, language, tag, active, search)
        # distinct() because a tag join can't duplicate a row here (tag
        # names are unique) but is the correct/safe default for any join.
        return query.with_entities(func.count(Destination.id.distinct())).scalar()

    def update(
        self, destination_id: int, tag_names: Optional[list[str]] = None, **fields
    ) -> Optional[Destination]:
        destination = self.get(destination_id)
        if destination is None:
            return None
        for key, value in fields.items():
            setattr(destination, key, value)
        if tag_names is not None:
            destination.tags = self._resolve_tags(tag_names)
        self.db.commit()
        self.db.refresh(destination)
        return destination

    def delete(self, destination_id: int) -> bool:
        destination = self.get(destination_id)
        if destination is None:
            return False
        self.db.delete(destination)
        self.db.commit()
        return True

    def _distinct_values(self, column) -> list[str]:
        rows = self.db.query(column).filter(column.isnot(None), column != "").distinct().all()
        return sorted({row[0] for row in rows if row[0]})

    def distinct_categories(self) -> list[str]:
        return self._distinct_values(Destination.category)

    def distinct_locations(self) -> list[str]:
        return self._distinct_values(Destination.location)

    def distinct_languages(self) -> list[str]:
        return self._distinct_values(Destination.language)
