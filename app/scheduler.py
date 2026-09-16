# Two separate responsibilities live in this file (see PROJECT_STATUS.md
# section 18).
#
# run_due_posts(db) contains the actual scheduler logic. It's a plain
# function that takes a SQLAlchemy Session and has no APScheduler dependency,
# which makes it easy to test directly without timers, threads, or waiting.
#
# start_scheduler() is the only part that uses APScheduler. It runs
# run_due_posts() on a BackgroundScheduler interval and creates a new
# database session for each run since the scheduler uses its own thread.
# It's started once from app/main.py's lifespan.
#
# A post is due when it's Scheduled, not paused, and its scheduled_at time
# has passed. Use app/utils/time_utils.utcnow() for the current time.
#
# Telegram posts are sent automatically through send_telegram_post().
# Facebook and TikTok can't be posted unattended, so those posts are moved
# to Manual Action Required instead of staying overdue with no indication
# that a human needs to step in.

import logging

from sqlalchemy.orm import Session

from app.database.enums import Platform, PostStatus
from app.database.repositories.destination_repository import DestinationRepository
from app.database.repositories.post_repository import PostRepository
from app.services.post_service import PostService
from app.utils.time_utils import utcnow

logger = logging.getLogger(__name__)


def run_due_posts(db: Session) -> dict:
    """Finds due Scheduled posts and resolves each one. Never lets one
    bad post abort the batch (same "never silently fail the whole thing"
    rule as create_queue()/CSV import) — one exception is logged and
    counted, the rest still run. Returns counts, useful for both logging
    and direct test assertions."""
    repo = PostRepository(db)
    destination_repo = DestinationRepository(db)
    service = PostService(db)

    now = utcnow()
    candidates = repo.list(status=PostStatus.SCHEDULED, limit=500)
    due_posts = [p for p in candidates if not p.paused and p.scheduled_at is not None and p.scheduled_at <= now]

    sent = needs_manual = errored = 0
    for due_post in due_posts:
        try:
            destination = destination_repo.get(due_post.destination_id)
            if destination is not None and destination.platform == Platform.TELEGRAM:
                service.send_telegram_post(due_post.id)
                sent += 1
            else:
                repo.update(due_post.id, status=PostStatus.MANUAL_ACTION_REQUIRED)
                needs_manual += 1
        except Exception:
            logger.exception("Scheduler tick failed to process post %s", due_post.id)
            errored += 1

    result = {"due": len(due_posts), "sent": sent, "needs_manual_action": needs_manual, "errored": errored}
    if due_posts:
        logger.info("Scheduler tick: %s", result)
    return result


def start_scheduler():
    """Starts a BackgroundScheduler ticking run_due_posts() on its own
    thread and session. Returns the scheduler instance so the caller can
    shut it down cleanly; returns None if settings.scheduler_enabled is
    False (see the setting's own docstring for why every test disables
    this)."""
    from apscheduler.schedulers.background import BackgroundScheduler

    from app.config.settings import get_settings
    from app.database.database import get_session_factory

    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false) — not starting")
        return None

    session_factory = get_session_factory()

    def _tick() -> None:
        db = session_factory()
        try:
            run_due_posts(db)
        finally:
            db.close()

    scheduler = BackgroundScheduler()
    scheduler.add_job(_tick, "interval", seconds=settings.scheduler_interval_seconds, id="due_posts_tick")
    scheduler.start()
    logger.info("Scheduler started (interval=%ss)", settings.scheduler_interval_seconds)
    return scheduler
