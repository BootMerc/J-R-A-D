# Request/response schemas for Phase 11 metrics and analytics.
#
# MetricCreate is used for both creating and updating metrics. The
# AnalyticsService handles the upsert based on (job_id, destination_id, date),
# so callers don't need to know whether they're creating a new metric or
# updating an existing one.

from datetime import date as date_type
from typing import Optional

from pydantic import BaseModel, ConfigDict


class MetricCreate(BaseModel):
    job_id: int
    destination_id: int
    post_id: Optional[int] = None
    date: Optional[date_type] = None  # defaults to today — see the model's own default
    views: int = 0
    clicks: int = 0
    messages: int = 0
    applications: int = 0
    interviews: int = 0
    hires: int = 0
    notes: Optional[str] = None


class MetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    destination_id: int
    post_id: Optional[int] = None
    date: date_type
    views: int
    clicks: int
    messages: int
    applications: int
    interviews: int
    hires: int
    notes: Optional[str] = None


class MetricListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[MetricRead]
    total: int


class FunnelSummary(BaseModel):
    """Raw stage totals only — conversion rates are a display concern
    (percentage of what, relative to what, rounding) better left to
    whatever's rendering this, not baked into the API response."""

    views: int
    clicks: int
    messages: int
    applications: int
    interviews: int
    hires: int


class DestinationPerformance(BaseModel):
    destination_id: int
    destination_name: str
    platform: str
    views: int
    clicks: int
    messages: int
    applications: int
    interviews: int
    hires: int


class TemplatePerformance(BaseModel):
    """Only counts metrics logged against a specific post whose post_id
    resolves to a template — a metric logged at the job+destination level
    with no post_id can't be attributed to one template, so it's excluded
    here (it still counts in FunnelSummary/DestinationPerformance)."""

    template_id: int
    template_name: str
    post_count: int
    views: int
    clicks: int
    messages: int
    applications: int
    interviews: int
    hires: int
