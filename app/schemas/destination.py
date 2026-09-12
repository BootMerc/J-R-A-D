"""Request/response schemas for the Destinations API.

`tags` is a plain list[str] on the wire in both directions — the ORM's
list[Tag] gets converted to names by the field_validator below on the way
out, and the service/repository resolve names back to Tag rows on the way
in. Callers never see a Tag object.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.database.enums import Platform, PostingMethod


class DestinationBase(BaseModel):
    url: Optional[str] = None
    external_id: Optional[str] = None
    category: Optional[str] = None
    location: Optional[str] = None
    audience: Optional[str] = None
    language: Optional[str] = None
    notes: Optional[str] = None
    min_posting_interval_minutes: Optional[int] = Field(default=None, ge=0)
    daily_posting_limit: Optional[int] = Field(default=None, ge=0)


class DestinationCreate(DestinationBase):
    platform: Platform
    name: str
    posting_method: PostingMethod
    active: bool = True
    tags: list[str] = Field(default_factory=list)


class DestinationUpdate(DestinationBase):
    platform: Optional[Platform] = None
    name: Optional[str] = None
    posting_method: Optional[PostingMethod] = None
    active: Optional[bool] = None
    tags: Optional[list[str]] = None


class DestinationRead(DestinationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: Platform
    name: str
    posting_method: PostingMethod
    active: bool
    last_posted_at: Optional[datetime] = None
    created_at: datetime
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def _tag_names(cls, value):
        """Accepts either list[Tag] (from the ORM) or list[str] (already
        plain names, e.g. in tests) and always returns list[str]."""
        if value and hasattr(value[0], "name"):
            return [tag.name for tag in value]
        return value


class DestinationListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[DestinationRead]
    total: int
