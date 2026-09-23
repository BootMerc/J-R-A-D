# Posts API.
#
# Keep the specific routes (/generate, /generate-variations, /create-queue,
# /progress, /facebook-queue) before /{post_id} so they don't get matched
# as post IDs.

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.enums import PostStatus
from app.schemas.post import (
    CreateQueueRequest,
    CreateQueueResult,
    FacebookAssistResult,
    GeneratePostsRequest,
    GenerateResult,
    GenerateVariationsRequest,
    MarkFailedRequest,
    PostListResponse,
    PostRead,
    PostUpdate,
    ProgressResponse,
    QueuePostRequest,
)
from app.services.post_service import PostService

router = APIRouter(prefix="/posts", tags=["posts"])


def get_post_service(db: Session = Depends(get_db)) -> PostService:
    return PostService(db)


@router.get("", response_model=PostListResponse)
def list_posts(
    job_id: Optional[int] = None,
    destination_id: Optional[int] = None,
    status: Optional[PostStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: PostService = Depends(get_post_service),
):
    items, total = service.list(
        job_id=job_id, destination_id=destination_id, status=status, skip=skip, limit=limit
    )
    return PostListResponse(items=items, total=total)


@router.post("/generate", response_model=GenerateResult)
def generate_posts(payload: GeneratePostsRequest, service: PostService = Depends(get_post_service)):
    created, errors = service.generate_posts(payload.job_id, payload.destination_ids, payload.template_id)
    return GenerateResult(created=created, errors=errors)


@router.post("/generate-variations", response_model=GenerateResult)
def generate_variations(
    payload: GenerateVariationsRequest, service: PostService = Depends(get_post_service)
):
    created, errors = service.generate_variations(
        payload.job_id, payload.destination_id, payload.template_ids
    )
    return GenerateResult(created=created, errors=errors)


@router.post("/create-queue", response_model=CreateQueueResult)
def create_queue(payload: CreateQueueRequest, service: PostService = Depends(get_post_service)):
    created, errors, warnings = service.create_queue(
        payload.job_id,
        payload.destination_ids,
        payload.template_id,
        payload.start_at,
        payload.delay_minutes,
    )
    return CreateQueueResult(created=created, errors=errors, warnings=warnings)


@router.get("/progress", response_model=ProgressResponse)
def get_progress(job_id: Optional[int] = None, service: PostService = Depends(get_post_service)):
    return service.progress(job_id)


@router.get("/facebook-queue", response_model=list[PostRead])
def facebook_queue(service: PostService = Depends(get_post_service)):
    """Phase 7: the Facebook Assistant's working set — Queued Facebook
    posts plus whichever one is already Processing-and-not-paused (so a
    page reload resumes it), ordered by scheduled_at."""
    return service.facebook_assist_candidates()


@router.get("/{post_id}", response_model=PostRead)
def get_post(post_id: int, service: PostService = Depends(get_post_service)):
    post = service.get(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
    return post


@router.patch("/{post_id}", response_model=PostRead)
def update_post(post_id: int, payload: PostUpdate, service: PostService = Depends(get_post_service)):
    return service.update(post_id, payload)


@router.delete("/{post_id}", status_code=204)
def delete_post(post_id: int, service: PostService = Depends(get_post_service)):
    service.delete(post_id)
    return Response(status_code=204)


@router.post("/{post_id}/queue", response_model=PostRead)
def queue_post(post_id: int, payload: QueuePostRequest, service: PostService = Depends(get_post_service)):
    return service.queue_existing_post(post_id, payload.scheduled_at)


@router.post("/{post_id}/start", response_model=PostRead)
def start_post(post_id: int, service: PostService = Depends(get_post_service)):
    return service.start(post_id)


@router.post("/{post_id}/schedule", response_model=PostRead)
def schedule_post(post_id: int, service: PostService = Depends(get_post_service)):
    return service.schedule(post_id)


@router.post("/{post_id}/unschedule", response_model=PostRead)
def unschedule_post(post_id: int, service: PostService = Depends(get_post_service)):
    return service.unschedule(post_id)


@router.post("/{post_id}/skip", response_model=PostRead)
def skip_post(post_id: int, service: PostService = Depends(get_post_service)):
    return service.skip(post_id)


@router.post("/{post_id}/retry", response_model=PostRead)
def retry_post(post_id: int, service: PostService = Depends(get_post_service)):
    return service.retry(post_id)


@router.post("/{post_id}/pause", response_model=PostRead)
def pause_post(post_id: int, service: PostService = Depends(get_post_service)):
    return service.set_paused(post_id, True)


@router.post("/{post_id}/resume", response_model=PostRead)
def resume_post(post_id: int, service: PostService = Depends(get_post_service)):
    return service.set_paused(post_id, False)


@router.post("/{post_id}/facebook-assist", response_model=FacebookAssistResult)
def facebook_assist_post(post_id: int, service: PostService = Depends(get_post_service)):
    post, browser_opened, clipboard_copied = service.start_facebook_assist(post_id)
    return FacebookAssistResult(post=post, browser_opened=browser_opened, clipboard_copied=clipboard_copied)


@router.post("/{post_id}/mark-posted", response_model=PostRead)
def mark_posted_post(post_id: int, service: PostService = Depends(get_post_service)):
    return service.mark_posted(post_id)


@router.post("/{post_id}/mark-failed", response_model=PostRead)
def mark_failed_post(
    post_id: int, payload: MarkFailedRequest, service: PostService = Depends(get_post_service)
):
    return service.mark_failed(post_id, payload.error_message)


@router.post("/{post_id}/send-telegram", response_model=PostRead)
def send_telegram_post(post_id: int, service: PostService = Depends(get_post_service)):
    """Phase 8: unlike Facebook, this resolves the post to Posted or
    Failed in the same call — a 200 response with status=Failed means the
    send was attempted and Telegram (or the network, or missing config)
    rejected it; a 400 means the request itself was invalid (wrong
    platform, wrong starting status)."""
    return service.send_telegram_post(post_id)


@router.post("/{post_id}/generate-tiktok-visual", response_model=PostRead)
def generate_tiktok_visual_post(post_id: int, service: PostService = Depends(get_post_service)):
    """Phase 9: fills in media_path, doesn't touch status. Safe to call
    again on the same post — each call overwrites the previous image."""
    return service.generate_tiktok_visual(post_id)
