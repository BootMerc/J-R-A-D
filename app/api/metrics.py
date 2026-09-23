# Metrics/Analytics API.
#
# All routes use string paths, so there is no /{id} route that could
# conflict with them. No route-ordering concern here.

from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.metric import (
    DestinationPerformance,
    FunnelSummary,
    MetricCreate,
    MetricListResponse,
    MetricRead,
    TemplatePerformance,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(tags=["analytics"])


def get_analytics_service(db: Session = Depends(get_db)) -> AnalyticsService:
    return AnalyticsService(db)


@router.post("/metrics", response_model=MetricRead)
def log_metric(payload: MetricCreate, service: AnalyticsService = Depends(get_analytics_service)):
    return service.log_metric(**payload.model_dump())


@router.get("/metrics", response_model=MetricListResponse)
def list_metrics(
    job_id: Optional[int] = None,
    destination_id: Optional[int] = None,
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    limit: int = 200,
    service: AnalyticsService = Depends(get_analytics_service),
):
    items = service.list_metrics(job_id, destination_id, date_from, date_to, limit)
    return MetricListResponse(items=items, total=len(items))


@router.delete("/metrics/{metric_id}", status_code=204)
def delete_metric(metric_id: int, service: AnalyticsService = Depends(get_analytics_service)):
    service.delete_metric(metric_id)


@router.get("/analytics/funnel", response_model=FunnelSummary)
def get_funnel(
    job_id: Optional[int] = None,
    destination_id: Optional[int] = None,
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    service: AnalyticsService = Depends(get_analytics_service),
):
    return service.funnel_summary(job_id, destination_id, date_from, date_to)


@router.get("/analytics/by-destination", response_model=list[DestinationPerformance])
def get_performance_by_destination(
    job_id: Optional[int] = None,
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    service: AnalyticsService = Depends(get_analytics_service),
):
    return service.performance_by_destination(job_id, date_from, date_to)


@router.get("/analytics/by-template", response_model=list[TemplatePerformance])
def get_performance_by_template(
    job_id: Optional[int] = None,
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    service: AnalyticsService = Depends(get_analytics_service),
):
    return service.performance_by_template(job_id, date_from, date_to)
