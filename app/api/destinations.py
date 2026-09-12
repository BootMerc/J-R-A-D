"""Destinations API. Specific string routes (filter-options, import-csv,
export-csv) are declared before the /{destination_id} route so an int-typed
path param can never shadow them.
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.enums import Platform
from app.schemas.destination import (
    DestinationCreate,
    DestinationListResponse,
    DestinationRead,
    DestinationUpdate,
)
from app.services.destination_service import DestinationService

router = APIRouter(prefix="/destinations", tags=["destinations"])


def get_destination_service(db: Session = Depends(get_db)) -> DestinationService:
    return DestinationService(db)


@router.post("", response_model=DestinationRead, status_code=201)
def create_destination(
    payload: DestinationCreate, service: DestinationService = Depends(get_destination_service)
):
    return service.create(payload)


@router.get("", response_model=DestinationListResponse)
def list_destinations(
    platform: Optional[Platform] = None,
    category: Optional[str] = None,
    location: Optional[str] = None,
    language: Optional[str] = None,
    tag: Optional[str] = None,
    active: Optional[bool] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: DestinationService = Depends(get_destination_service),
):
    items, total = service.list(
        platform=platform, category=category, location=location, language=language,
        tag=tag, active=active, search=search, skip=skip, limit=limit,
    )
    return DestinationListResponse(items=items, total=total)


@router.get("/filter-options")
def get_filter_options(service: DestinationService = Depends(get_destination_service)) -> dict:
    return service.filter_options()


@router.post("/import-csv")
async def import_destinations_csv(
    file: UploadFile = File(...), service: DestinationService = Depends(get_destination_service)
) -> dict:
    raw = await file.read()
    content = raw.decode("utf-8-sig")  # utf-8-sig also handles plain utf-8 without a BOM
    result = service.import_csv(content)
    return {"created": result.created, "errors": result.errors}


@router.get("/export-csv")
def export_destinations_csv(service: DestinationService = Depends(get_destination_service)) -> Response:
    csv_content = service.export_csv()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=destinations.csv"},
    )


@router.get("/{destination_id}", response_model=DestinationRead)
def get_destination(destination_id: int, service: DestinationService = Depends(get_destination_service)):
    destination = service.get(destination_id)
    if destination is None:
        raise HTTPException(status_code=404, detail=f"Destination {destination_id} not found")
    return destination


@router.patch("/{destination_id}", response_model=DestinationRead)
def update_destination(
    destination_id: int,
    payload: DestinationUpdate,
    service: DestinationService = Depends(get_destination_service),
):
    return service.update(destination_id, payload)


@router.delete("/{destination_id}", status_code=204)
def delete_destination(destination_id: int, service: DestinationService = Depends(get_destination_service)):
    service.delete(destination_id)
    return Response(status_code=204)


@router.post("/{destination_id}/activate", response_model=DestinationRead)
def activate_destination(destination_id: int, service: DestinationService = Depends(get_destination_service)):
    return service.set_active(destination_id, True)


@router.post("/{destination_id}/deactivate", response_model=DestinationRead)
def deactivate_destination(destination_id: int, service: DestinationService = Depends(get_destination_service)):
    return service.set_active(destination_id, False)
