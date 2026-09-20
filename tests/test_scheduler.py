"""Phase 10 tests for app/scheduler.py's run_due_posts() — the actual
logic, with zero APScheduler dependency (see the module's own docstring
for why). Fabricates posts with scheduled_at in the past/future and calls
run_due_posts(db) directly; no timers, no threads, no waiting.

start_scheduler() itself isn't tested here beyond what every existing
TestClient-based test already covers indirectly (the app starts and stops
cleanly with SCHEDULER_ENABLED=false) — see PROJECT_STATUS.md section 18
for why that split is deliberate.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import models  # noqa: F401  (registers models on Base)
from app.database.database import Base
from app.database.enums import PostStatus
from app.scheduler import run_due_posts
from app.services.post_service import PostService
from app.utils.time_utils import utcnow


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def _make_job_and_destination(db_session, platform="Telegram"):
    from app.database.enums import JobStatus, Platform, PostingMethod
    from app.database.models import Destination, Job

    job = Job(title="Cashier", company="Store Co", location="Cairo", status=JobStatus.DRAFT)
    destination = Destination(
        platform=Platform(platform),
        name="Test Destination",
        posting_method=PostingMethod.API if platform == "Telegram" else PostingMethod.BROWSER_ASSISTED,
        active=True,
        external_id="123456" if platform == "Telegram" else None,
    )
    db_session.add_all([job, destination])
    db_session.commit()
    return job, destination


def test_run_due_posts_ignores_non_scheduled_statuses(db_session):
    job, destination = _make_job_and_destination(db_session)
    service = PostService(db_session)
    service.repo.create(
        job_id=job.id, destination_id=destination.id, content="x",
        status=PostStatus.QUEUED, scheduled_at=utcnow() - timedelta(minutes=5),
    )

    result = run_due_posts(db_session)
    assert result == {"due": 0, "sent": 0, "needs_manual_action": 0, "errored": 0}


def test_run_due_posts_ignores_future_scheduled_posts(db_session):
    job, destination = _make_job_and_destination(db_session)
    service = PostService(db_session)
    service.repo.create(
        job_id=job.id, destination_id=destination.id, content="x",
        status=PostStatus.SCHEDULED, scheduled_at=utcnow() + timedelta(hours=1),
    )

    result = run_due_posts(db_session)
    assert result["due"] == 0


def test_run_due_posts_ignores_paused_due_posts(db_session):
    job, destination = _make_job_and_destination(db_session)
    service = PostService(db_session)
    service.repo.create(
        job_id=job.id, destination_id=destination.id, content="x",
        status=PostStatus.SCHEDULED, scheduled_at=utcnow() - timedelta(minutes=5), paused=True,
    )

    result = run_due_posts(db_session)
    assert result == {"due": 0, "sent": 0, "needs_manual_action": 0, "errored": 0}


def test_run_due_posts_sends_due_telegram_posts(db_session):
    job, destination = _make_job_and_destination(db_session, platform="Telegram")
    service = PostService(db_session)
    due_post = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="Hiring now",
        status=PostStatus.SCHEDULED, scheduled_at=utcnow() - timedelta(minutes=5),
    )

    with patch("app.services.post_service.send_message", return_value=(True, "77", None)):
        result = run_due_posts(db_session)

    assert result == {"due": 1, "sent": 1, "needs_manual_action": 0, "errored": 0}
    refreshed = service.repo.get(due_post.id)
    assert refreshed.status == PostStatus.POSTED
    assert refreshed.external_post_id == "77"


def test_run_due_posts_moves_due_facebook_posts_to_manual_action_required(db_session):
    job, destination = _make_job_and_destination(db_session, platform="Facebook")
    service = PostService(db_session)
    due_post = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="Hiring now",
        status=PostStatus.SCHEDULED, scheduled_at=utcnow() - timedelta(minutes=5),
    )

    result = run_due_posts(db_session)

    assert result == {"due": 1, "sent": 0, "needs_manual_action": 1, "errored": 0}
    refreshed = service.repo.get(due_post.id)
    assert refreshed.status == PostStatus.MANUAL_ACTION_REQUIRED


def test_run_due_posts_moves_due_tiktok_posts_to_manual_action_required(db_session):
    job, destination = _make_job_and_destination(db_session, platform="TikTok")
    service = PostService(db_session)
    due_post = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="Hiring now",
        status=PostStatus.SCHEDULED, scheduled_at=utcnow() - timedelta(minutes=5),
    )

    result = run_due_posts(db_session)

    assert result["needs_manual_action"] == 1
    refreshed = service.repo.get(due_post.id)
    assert refreshed.status == PostStatus.MANUAL_ACTION_REQUIRED


def test_run_due_posts_one_bad_post_does_not_abort_the_batch(db_session):
    """Never-silently-fail-the-whole-batch — same rule as
    create_queue()/CSV import (see the module docstring)."""
    job, telegram_dest = _make_job_and_destination(db_session, platform="Telegram")
    _, facebook_dest = _make_job_and_destination(db_session, platform="Facebook")
    service = PostService(db_session)
    broken_post = service.repo.create(
        job_id=job.id, destination_id=telegram_dest.id, content="x",
        status=PostStatus.SCHEDULED, scheduled_at=utcnow() - timedelta(minutes=5),
    )
    healthy_post = service.repo.create(
        job_id=job.id, destination_id=facebook_dest.id, content="y",
        status=PostStatus.SCHEDULED, scheduled_at=utcnow() - timedelta(minutes=5),
    )

    with patch("app.services.post_service.send_message", side_effect=RuntimeError("boom")):
        result = run_due_posts(db_session)

    assert result["errored"] == 1
    assert result["needs_manual_action"] == 1
    # start() already succeeded (Scheduled -> Processing) before the
    # mocked send raised, so the broken post is correctly left Processing
    # — started but unresolved, recoverable via the Queue page's generic
    # Mark Posted/Mark Failed (Phase 9) — not still sitting as Scheduled.
    assert service.repo.get(broken_post.id).status == PostStatus.PROCESSING
    # The healthy Facebook one still got processed despite the other's crash.
    assert service.repo.get(healthy_post.id).status == PostStatus.MANUAL_ACTION_REQUIRED
