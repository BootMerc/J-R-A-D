# Request/response schemas for the Templates API.
#
# TemplateRead.unknown_variables is a computed field, not a database column.
# It checks the template for unknown {{variables}} on every response, so
# mistakes are shown immediately when a template is created, edited, or listed
# instead of only appearing during preview.
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from app.database.enums import Platform
from app.utils.template_rendering import unknown_variables as _unknown_variables


class TemplateBase(BaseModel):
    language: Optional[str] = None


class TemplateCreate(TemplateBase):
    name: str
    platform: Platform
    template_text: str
    active: bool = True


class TemplateUpdate(TemplateBase):
    name: Optional[str] = None
    platform: Optional[Platform] = None
    template_text: Optional[str] = None
    active: Optional[bool] = None


class TemplateRead(TemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    platform: Platform
    template_text: str
    active: bool
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def unknown_variables(self) -> list[str]:
        return _unknown_variables(self.template_text)


class TemplateListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[TemplateRead]
    total: int


class TemplatePreviewResponse(BaseModel):
    rendered_text: str
    unknown_variables: list[str]
