# ApplicationMetric repository: only handles SQLAlchemy queries.
#
# The upsert logic for (job_id, destination_id, date) lives in
# app/services/analytics_service.py. This repository only provides
# find_one() to look up an existing metric.

from __future__ import annotations
# ^ This class defines a method literally named `list` — see
# destination_repository.py's comment for why this import matters.

from datetime import date as date_type
from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import ApplicationMetric


class MetricRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **fields) -> ApplicationMetric:
        metric = ApplicationMetric(**fields)
        self.db.add(metric)
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def get(self, metric_id: int) -> Optional[ApplicationMetric]:
        return self.db.get(ApplicationMetric, metric_id)

    def find_one(
        self, job_id: int, destination_id: int, date: date_type, post_id: Optional[int] = None
    ) -> Optional[ApplicationMetric]:
        """The natural key a "log today's numbers" form re-submits
        against — used by log_metric() to decide update vs create.
        post_id is part of the key (not just job/destination/date): a
        metric tied to one specific post and a metric logged with no
        post_id are two different things for the same day, not the same
        entry with an optional extra field — see AnalyticsService's own
        note on why this matters when a destination has more than one
        post on the same day."""
        query = self.db.query(ApplicationMetric).filter(
            ApplicationMetric.job_id == job_id,
            ApplicationMetric.destination_id == destination_id,
            ApplicationMetric.date == date,
        )
        if post_id is None:
            query = query.filter(ApplicationMetric.post_id.is_(None))
        else:
            query = query.filter(ApplicationMetric.post_id == post_id)
        return query.first()

    def update(self, metric_id: int, **fields) -> ApplicationMetric:
        metric = self.get(metric_id)
        for key, value in fields.items():
            setattr(metric, key, value)
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def delete(self, metric_id: int) -> None:
        metric = self.get(metric_id)
        if metric is not None:
            self.db.delete(metric)
            self.db.commit()

    def list(
        self,
        job_id: Optional[int] = None,
        destination_id: Optional[int] = None,
        date_from: Optional[date_type] = None,
        date_to: Optional[date_type] = None,
        limit: Optional[int] = 200,
    ) -> list[ApplicationMetric]:
        query = self.db.query(ApplicationMetric)
        if job_id is not None:
            query = query.filter(ApplicationMetric.job_id == job_id)
        if destination_id is not None:
            query = query.filter(ApplicationMetric.destination_id == destination_id)
        if date_from is not None:
            query = query.filter(ApplicationMetric.date >= date_from)
        if date_to is not None:
            query = query.filter(ApplicationMetric.date <= date_to)
        query = query.order_by(ApplicationMetric.date.desc())
        if limit is not None:
            query = query.limit(limit)
        return query.all()
