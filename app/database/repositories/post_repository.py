# Post repository: only handles SQLAlchemy queries.
# Content generation (rendering a template for a job) is handled in post_service.py.

from __future__ import annotations
# ^ This class has a `list()` method — see destination_repository.py
# (PROJECT_STATUS.md section 13) for why this import is required in every
# repository/service class shaped this way.

from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database.enums import Platform, PostStatus
from app.database.models import Destination, Post


class PostRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **fields) -> Post:
        post = Post(**fields)
        self.db.add(post)
        self.db.commit()
        self.db.refresh(post)
        return post

    def get(self, post_id: int) -> Optional[Post]:
        return self.db.get(Post, post_id)

    def _filtered_query(
        self,
        job_id: Optional[int] = None,
        destination_id: Optional[int] = None,
        status: Optional[PostStatus] = None,
        platform: Optional[Platform] = None,
    ):
        query = self.db.query(Post)
        if job_id is not None:
            query = query.filter(Post.job_id == job_id)
        if destination_id is not None:
            query = query.filter(Post.destination_id == destination_id)
        if status is not None:
            query = query.filter(Post.status == status)
        if platform is not None:
            # Phase 7: joins to Destination only when a caller actually asks
            # to filter by platform (the Facebook Assistant's queue lookup),
            # so every other caller's query plan is unchanged.
            query = query.join(Post.destination).filter(Destination.platform == platform)
        return query

    def list(
        self,
        job_id: Optional[int] = None,
        destination_id: Optional[int] = None,
        status: Optional[PostStatus] = None,
        platform: Optional[Platform] = None,
        skip: int = 0,
        limit: Optional[int] = 50,
    ) -> list[Post]:
        query = self._filtered_query(job_id, destination_id, status, platform)
        query = query.order_by(Post.created_at.desc()).offset(skip)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def count(
        self,
        job_id: Optional[int] = None,
        destination_id: Optional[int] = None,
        status: Optional[PostStatus] = None,
        platform: Optional[Platform] = None,
    ) -> int:
        query = self._filtered_query(job_id, destination_id, status, platform)
        return query.with_entities(func.count(Post.id)).scalar()

    def update(self, post_id: int, **fields) -> Optional[Post]:
        post = self.get(post_id)
        if post is None:
            return None
        for key, value in fields.items():
            setattr(post, key, value)
        self.db.commit()
        self.db.refresh(post)
        return post

    def delete(self, post_id: int) -> bool:
        post = self.get(post_id)
        if post is None:
            return False
        self.db.delete(post)
        self.db.commit()
        return True

    def count_for_destination_on_date(self, destination_id: int, target_date: date) -> int:
        """How many non-failed, non-skipped posts already occupy this
        destination's queue for a given calendar date — checks both
        scheduled_at (pending) and posted_at (completed), since a post's
        scheduled_at doesn't change once it's actually sent."""
        day_start = datetime.combine(target_date, time.min)
        day_end = datetime.combine(target_date, time.max)
        active_statuses = [PostStatus.QUEUED, PostStatus.SCHEDULED, PostStatus.PROCESSING, PostStatus.POSTED]
        return (
            self.db.query(Post)
            .filter(
                Post.destination_id == destination_id,
                Post.status.in_(active_statuses),
                or_(
                    Post.scheduled_at.between(day_start, day_end),
                    Post.posted_at.between(day_start, day_end),
                ),
            )
            .count()
        )
