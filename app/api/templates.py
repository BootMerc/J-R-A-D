from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.enums import Platform
from app.schemas.template import (
    TemplateCreate,
    TemplateListResponse,
    TemplatePreviewResponse,
    TemplateRead,
    TemplateUpdate,
)
from app.services.template_service import TemplateService

router = APIRouter(prefix="/templates", tags=["templates"])


def get_template_service(db: Session = Depends(get_db)) -> TemplateService:
    return TemplateService(db)


@router.post("", response_model=TemplateRead, status_code=201)
def create_template(payload: TemplateCreate, service: TemplateService = Depends(get_template_service)):
    return service.create(payload)


@router.get("", response_model=TemplateListResponse)
def list_templates(
    platform: Optional[Platform] = None,
    language: Optional[str] = None,
    active: Optional[bool] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: TemplateService = Depends(get_template_service),
):
    items, total = service.list(
        platform=platform, language=language, active=active, search=search, skip=skip, limit=limit
    )
    return TemplateListResponse(items=items, total=total)


@router.get("/{template_id}", response_model=TemplateRead)
def get_template(template_id: int, service: TemplateService = Depends(get_template_service)):
    template = service.get(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    return template


@router.patch("/{template_id}", response_model=TemplateRead)
def update_template(
    template_id: int, payload: TemplateUpdate, service: TemplateService = Depends(get_template_service)
):
    return service.update(template_id, payload)


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: int, service: TemplateService = Depends(get_template_service)):
    service.delete(template_id)
    return Response(status_code=204)


@router.post("/{template_id}/activate", response_model=TemplateRead)
def activate_template(template_id: int, service: TemplateService = Depends(get_template_service)):
    return service.set_active(template_id, True)


@router.post("/{template_id}/deactivate", response_model=TemplateRead)
def deactivate_template(template_id: int, service: TemplateService = Depends(get_template_service)):
    return service.set_active(template_id, False)


@router.get("/{template_id}/preview", response_model=TemplatePreviewResponse)
def preview_template(
    template_id: int, job_id: int, service: TemplateService = Depends(get_template_service)
):
    return service.preview(template_id, job_id)
