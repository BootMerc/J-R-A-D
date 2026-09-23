# Analytics views built from manually entered metrics.
#
# There is no automated metrics collection in the project. Facebook and
# TikTok use manual workflows, while Telegram's Bot API doesn't provide
# the per-message view/click data this project needs without additional
# setup.
#
# Since metrics are entered manually, log_metric() upserts by
# (job_id, destination_id, date). The idea is to update today's numbers
# rather than create another row every time they change.
#
# Aggregation is done in Python after fetching the filtered results instead
# of using SQL GROUP BY. This follows the same approach used by
# facebook_assist_candidates() and keeps things simple for the project's
# expected scale.

from datetime import date as date_type
from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import ApplicationMetric
from app.database.repositories.destination_repository import DestinationRepository
from app.database.repositories.metric_repository import MetricRepository
from app.database.repositories.post_repository import PostRepository
from app.database.repositories.template_repository import TemplateRepository
from app.services.exceptions import NotFoundError

_METRIC_FIELDS = ("views", "clicks", "messages", "applications", "interviews", "hires")


class AnalyticsService:
    def __init__(self, db: Session):
        self.repo = MetricRepository(db)
        self.destination_repo = DestinationRepository(db)
        self.post_repo = PostRepository(db)
        self.template_repo = TemplateRepository(db)

    def log_metric(
        self,
        job_id: int,
        destination_id: int,
        post_id: Optional[int] = None,
        date: Optional[date_type] = None,
        **counts,
    ) -> ApplicationMetric:
        """Creates or updates the (job_id, destination_id, date, post_id)
        row — the date the numbers being logged apply to, not "when this
        API call happened", which is why it defaults to today rather than
        using a server-side timestamp default the way created_at does
        elsewhere. post_id is part of the upsert key, not just an extra
        field: a destination can have more than one post on the same day
        (e.g. two variations posted to the same Facebook group), and each
        one's numbers need their own row rather than the second call
        silently overwriting the first's."""
        resolved_date = date or date_type.today()
        existing = self.repo.find_one(job_id, destination_id, resolved_date, post_id)
        fields = {"post_id": post_id, **{k: counts.get(k, 0) for k in _METRIC_FIELDS}, "notes": counts.get("notes")}
        if existing is not None:
            return self.repo.update(existing.id, **fields)
        return self.repo.create(job_id=job_id, destination_id=destination_id, date=resolved_date, **fields)

    def list_metrics(
        self,
        job_id: Optional[int] = None,
        destination_id: Optional[int] = None,
        date_from: Optional[date_type] = None,
        date_to: Optional[date_type] = None,
        limit: Optional[int] = 200,
    ) -> list[ApplicationMetric]:
        return self.repo.list(job_id, destination_id, date_from, date_to, limit)

    def delete_metric(self, metric_id: int) -> None:
        if self.repo.get(metric_id) is None:
            raise NotFoundError(f"Metric {metric_id} not found")
        self.repo.delete(metric_id)

    def funnel_summary(
        self,
        job_id: Optional[int] = None,
        destination_id: Optional[int] = None,
        date_from: Optional[date_type] = None,
        date_to: Optional[date_type] = None,
    ) -> dict:
        metrics = self.repo.list(job_id, destination_id, date_from, date_to, limit=None)
        return {field: sum(getattr(m, field) for m in metrics) for field in _METRIC_FIELDS}

    def performance_by_destination(
        self,
        job_id: Optional[int] = None,
        date_from: Optional[date_type] = None,
        date_to: Optional[date_type] = None,
    ) -> list[dict]:
        metrics = self.repo.list(job_id=job_id, date_from=date_from, date_to=date_to, limit=None)
        totals: dict[int, dict] = {}
        for metric in metrics:
            bucket = totals.setdefault(metric.destination_id, {field: 0 for field in _METRIC_FIELDS})
            for field in _METRIC_FIELDS:
                bucket[field] += getattr(metric, field)

        results = []
        for destination_id, bucket in totals.items():
            destination = self.destination_repo.get(destination_id)
            if destination is None:
                continue  # destination was deleted since the metric was logged
            results.append(
                {
                    "destination_id": destination_id,
                    "destination_name": destination.name,
                    "platform": destination.platform.value,
                    **bucket,
                }
            )
        results.sort(key=lambda r: r["applications"], reverse=True)
        return results

    def performance_by_template(
        self,
        job_id: Optional[int] = None,
        date_from: Optional[date_type] = None,
        date_to: Optional[date_type] = None,
    ) -> list[dict]:
        """Only metrics logged against a specific post_id can be
        attributed to a template — see TemplatePerformance's own
        docstring for why the rest are silently excluded here rather
        than raising or warning."""
        metrics = self.repo.list(job_id=job_id, date_from=date_from, date_to=date_to, limit=None)
        totals: dict[int, dict] = {}
        post_counts: dict[int, set] = {}

        for metric in metrics:
            if metric.post_id is None:
                continue
            post = self.post_repo.get(metric.post_id)
            if post is None or post.template_id is None:
                continue
            bucket = totals.setdefault(post.template_id, {field: 0 for field in _METRIC_FIELDS})
            for field in _METRIC_FIELDS:
                bucket[field] += getattr(metric, field)
            post_counts.setdefault(post.template_id, set()).add(post.id)

        results = []
        for template_id, bucket in totals.items():
            template = self.template_repo.get(template_id)
            if template is None:
                continue  # template was deleted since the post was created
            results.append(
                {
                    "template_id": template_id,
                    "template_name": template.name,
                    "post_count": len(post_counts[template_id]),
                    **bucket,
                }
            )
        results.sort(key=lambda r: r["applications"], reverse=True)
        return results
