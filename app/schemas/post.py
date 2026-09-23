from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.database.enums import PostStatus


class PostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    destination_id: int
    template_id: Optional[int] = None
    content: str
    media_path: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    posted_at: Optional[datetime] = None
    status: PostStatus
    paused: bool
    error_message: Optional[str] = None
    external_post_id: Optional[str] = None
    created_at: datetime


class PostUpdate(BaseModel):
    content: Optional[str] = None
    status: Optional[PostStatus] = None
    scheduled_at: Optional[datetime] = None


class PostListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[PostRead]
    total: int


class GeneratePostsRequest(BaseModel):
    job_id: int
    destination_ids: list[int]
    # If omitted, a suitable active template is auto-selected per
    # destination's platform (preferring a language match). If given, it's
    # used for every destination — and any destination on a different
    # platform than the template is skipped with an error, not silently
    # mis-rendered.
    template_id: Optional[int] = None


class GenerateVariationsRequest(BaseModel):
    job_id: int
    destination_id: int
    template_ids: list[int]


class GenerateResult(BaseModel):
    created: list[PostRead]
    errors: list[str]


class CreateQueueRequest(BaseModel):
    """Section 31's batch queue creation: one job, many destinations, a
    posting window (start time + delay between each)."""

    job_id: int
    destination_ids: list[int]
    template_id: Optional[int] = None
    start_at: Optional[datetime] = None  # defaults to now if omitted
    delay_minutes: int = Field(default=5, ge=0)


class CreateQueueResult(BaseModel):
    created: list[PostRead]
    errors: list[str]  # hard skips — no valid post could be produced
    warnings: list[str]  # Section 19 spam-protection flags — post still created


class QueuePostRequest(BaseModel):
    scheduled_at: Optional[datetime] = None  # defaults to now if omitted


class ProgressResponse(BaseModel):
    counts: dict[str, int]
    total: int


class MarkFailedRequest(BaseModel):
    """Optional — a blank/omitted reason still gets a non-empty default
    message from PostService.mark_failed(), not an empty error_message."""

    error_message: Optional[str] = None


class FacebookAssistResult(BaseModel):
    """Response for POST /posts/{id}/facebook-assist. browser_opened and
    clipboard_copied reflect whether each OS-level action actually
    succeeded (see app/integrations/facebook/assistant.py) — the request
    itself still succeeds either way."""

    post: PostRead
    browser_opened: bool
    clipboard_copied: bool
