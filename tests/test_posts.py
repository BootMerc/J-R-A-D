"""Phase 5 tests: PostRepository, PostService (generate_posts,
generate_variations, auto-template-selection, platform-mismatch handling),
and the Posts API.

Phase 6 (Queue) and Phase 7 (Facebook Assistant) additions are appended
below in their own sections rather than a separate file, since both extend
this same PostRepository/PostService/posts.py — see PROJECT_STATUS.md
section 16 for why. Phase 7's pure OS-wrapper tests (webbrowser/pyperclip,
fully mocked) live in tests/test_facebook_assistant.py instead, since they
need no DB fixture at all.
"""

import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import models  # noqa: F401  (registers models on Base)
from app.database.database import Base


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def api_client(monkeypatch, tmp_path):
    """A TestClient bound to its own isolated SQLite file. Startup also
    seeds the 7 default templates via the app's lifespan."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test_posts.db")
    # Phase 10: a real BackgroundScheduler ticking against a test database
    # mid-test-run would be exactly the kind of flaky interference this
    # disables — see settings.py's scheduler_enabled docstring.
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")

    from app.config.settings import get_settings

    get_settings.cache_clear()

    from app.database import database

    database.get_engine.cache_clear()

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client

    get_settings.cache_clear()
    database.get_engine.cache_clear()


def _make_job_and_destination(db_session, platform="Facebook"):
    from app.database.enums import JobStatus, Platform, PostingMethod
    from app.database.models import Destination, Job

    job = Job(title="Cashier", company="Store Co", location="Cairo", status=JobStatus.DRAFT)
    destination = Destination(
        platform=Platform(platform),
        name="Cairo Jobs Group",
        posting_method=PostingMethod.BROWSER_ASSISTED if platform == "Facebook" else PostingMethod.API,
        active=True,
    )
    db_session.add_all([job, destination])
    db_session.commit()
    return job, destination


# --- Repository ---------------------------------------------------------


def test_repository_create_and_filter(db_session):
    from app.database.enums import PostStatus
    from app.database.repositories.post_repository import PostRepository

    job, destination = _make_job_and_destination(db_session)
    repo = PostRepository(db_session)
    post = repo.create(
        job_id=job.id, destination_id=destination.id, content="Hello", status=PostStatus.DRAFT
    )

    assert post.id is not None
    assert [p.id for p in repo.list(job_id=job.id)] == [post.id]
    assert repo.list(destination_id=999999) == []


def test_repository_delete(db_session):
    from app.database.enums import PostStatus
    from app.database.repositories.post_repository import PostRepository

    job, destination = _make_job_and_destination(db_session)
    repo = PostRepository(db_session)
    post = repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.DRAFT)

    assert repo.delete(post.id) is True
    assert repo.get(post.id) is None
    assert repo.delete(999) is False


# --- Service: generate_posts ------------------------------------------------


def test_service_generate_posts_auto_selects_template(db_session):
    from app.database.enums import Platform
    from app.database.models import PostTemplate
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Facebook")
    db_session.add(
        PostTemplate(
            name="FB template", platform=Platform.FACEBOOK, template_text="Hiring {{job_title}} at {{company}}"
        )
    )
    db_session.commit()

    service = PostService(db_session)
    created, errors = service.generate_posts(job.id, [destination.id])

    assert errors == []
    assert len(created) == 1
    assert created[0].content == "Hiring Cashier at Store Co"
    assert created[0].template_id is not None


def test_service_generate_posts_no_matching_template_reports_error(db_session):
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Facebook")
    # deliberately no templates created

    service = PostService(db_session)
    created, errors = service.generate_posts(job.id, [destination.id])

    assert created == []
    assert len(errors) == 1
    assert "Facebook" in errors[0]


def test_service_generate_posts_forced_template_platform_mismatch_is_skipped_not_aborted(db_session):
    from app.database.enums import Platform
    from app.database.models import PostTemplate
    from app.services.post_service import PostService

    job, fb_destination = _make_job_and_destination(db_session, platform="Facebook")
    _, tg_destination = _make_job_and_destination(db_session, platform="Telegram")
    fb_template = PostTemplate(name="FB only", platform=Platform.FACEBOOK, template_text="{{job_title}}")
    db_session.add(fb_template)
    db_session.commit()

    service = PostService(db_session)
    created, errors = service.generate_posts(
        job.id, [fb_destination.id, tg_destination.id], template_id=fb_template.id
    )

    assert len(created) == 1  # Facebook destination succeeds
    assert created[0].destination_id == fb_destination.id
    assert len(errors) == 1  # Telegram destination is reported, not silently dropped
    assert "Telegram" in errors[0]


def test_service_generate_posts_missing_job_raises(db_session):
    from app.services.exceptions import NotFoundError
    from app.services.post_service import PostService

    service = PostService(db_session)
    with pytest.raises(NotFoundError):
        service.generate_posts(999, [1])


def test_service_generate_posts_missing_destination_reports_error(db_session):
    from app.database.enums import JobStatus
    from app.database.models import Job
    from app.services.post_service import PostService

    job = Job(title="Cashier", status=JobStatus.DRAFT)
    db_session.add(job)
    db_session.commit()

    service = PostService(db_session)
    created, errors = service.generate_posts(job.id, [999999])

    assert created == []
    assert "999999" in errors[0]


# --- Service: generate_variations -------------------------------------------


def test_service_generate_variations_creates_one_post_per_template(db_session):
    from app.database.enums import Platform
    from app.database.models import PostTemplate
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Facebook")
    urgent = PostTemplate(name="Urgent", platform=Platform.FACEBOOK, template_text="URGENT: {{job_title}}")
    grad = PostTemplate(name="Fresh Grad", platform=Platform.FACEBOOK, template_text="Grads welcome: {{job_title}}")
    db_session.add_all([urgent, grad])
    db_session.commit()

    service = PostService(db_session)
    created, errors = service.generate_variations(job.id, destination.id, [urgent.id, grad.id])

    assert errors == []
    assert len(created) == 2
    contents = {c.content for c in created}
    assert contents == {"URGENT: Cashier", "Grads welcome: Cashier"}
    # all variations are for the same job + destination
    assert {c.job_id for c in created} == {job.id}
    assert {c.destination_id for c in created} == {destination.id}


def test_service_generate_variations_platform_mismatch_skipped(db_session):
    from app.database.enums import Platform
    from app.database.models import PostTemplate
    from app.services.post_service import PostService

    job, fb_destination = _make_job_and_destination(db_session, platform="Facebook")
    wrong_platform_template = PostTemplate(
        name="Telegram template", platform=Platform.TELEGRAM, template_text="{{job_title}}"
    )
    db_session.add(wrong_platform_template)
    db_session.commit()

    service = PostService(db_session)
    created, errors = service.generate_variations(job.id, fb_destination.id, [wrong_platform_template.id])

    assert created == []
    assert len(errors) == 1


# --- API ---------------------------------------------------------------


def test_api_generate_posts_end_to_end(api_client):
    job = api_client.post(
        "/jobs", json={"title": "Cashier", "company": "Store Co", "location": "Cairo"}
    ).json()
    destination = api_client.post(
        "/destinations",
        json={"platform": "Facebook", "name": "Cairo Jobs", "posting_method": "Browser-assisted"},
    ).json()

    response = api_client.post(
        "/posts/generate", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["created"]) == 1
    assert body["errors"] == []
    assert "Cashier" in body["created"][0]["content"]
    assert body["created"][0]["status"] == "Draft"


def test_api_generate_variations_end_to_end(api_client):
    job = api_client.post("/jobs", json={"title": "Nurse", "company": "Clinic Co"}).json()
    destination = api_client.post(
        "/destinations",
        json={"platform": "Telegram", "name": "Health Jobs", "posting_method": "API"},
    ).json()
    templates = api_client.get("/templates", params={"platform": "Telegram"}).json()["items"]
    template_ids = [t["id"] for t in templates]

    response = api_client.post(
        "/posts/generate-variations",
        json={"job_id": job["id"], "destination_id": destination["id"], "template_ids": template_ids},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["created"]) == len(template_ids)


def test_api_list_filter_by_status(api_client):
    job = api_client.post("/jobs", json={"title": "Driver"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "D", "posting_method": "Browser-assisted"}
    ).json()
    api_client.post("/posts/generate", json={"job_id": job["id"], "destination_ids": [destination["id"]]})

    response = api_client.get("/posts", params={"status": "Draft"})
    assert response.json()["total"] == 1

    response = api_client.get("/posts", params={"status": "Posted"})
    assert response.json()["total"] == 0


def test_api_update_content(api_client):
    job = api_client.post("/jobs", json={"title": "Driver"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "D", "posting_method": "Browser-assisted"}
    ).json()
    created = api_client.post(
        "/posts/generate", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    response = api_client.patch(f"/posts/{created['id']}", json={"content": "Edited by hand"})
    assert response.status_code == 200
    assert response.json()["content"] == "Edited by hand"


def test_api_delete(api_client):
    job = api_client.post("/jobs", json={"title": "Driver"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "D", "posting_method": "Browser-assisted"}
    ).json()
    created = api_client.post(
        "/posts/generate", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    assert api_client.delete(f"/posts/{created['id']}").status_code == 204
    assert api_client.get(f"/posts/{created['id']}").status_code == 404


def test_api_get_missing_post_returns_404(api_client):
    assert api_client.get("/posts/999999").status_code == 404


def test_api_generate_missing_job_returns_404(api_client):
    response = api_client.post("/posts/generate", json={"job_id": 999999, "destination_ids": [1]})
    assert response.status_code == 404


# --- Phase 6: repository -------------------------------------------------


def test_repository_count_for_destination_on_date_checks_scheduled_and_posted(db_session):
    from datetime import date, datetime

    from app.database.enums import PostStatus
    from app.database.repositories.post_repository import PostRepository

    job, destination = _make_job_and_destination(db_session)
    repo = PostRepository(db_session)
    today = date.today()

    repo.create(
        job_id=job.id, destination_id=destination.id, content="a", status=PostStatus.QUEUED,
        scheduled_at=datetime.combine(today, datetime.min.time()),
    )
    repo.create(
        job_id=job.id, destination_id=destination.id, content="b", status=PostStatus.POSTED,
        posted_at=datetime.combine(today, datetime.min.time()),
    )
    repo.create(job_id=job.id, destination_id=destination.id, content="c", status=PostStatus.SKIPPED)  # not counted

    assert repo.count_for_destination_on_date(destination.id, today) == 2


# --- Phase 6: service — create_queue --------------------------------------


def test_service_create_queue_stages_scheduled_times(db_session):
    from datetime import datetime

    from app.database.enums import Platform, PostStatus
    from app.database.models import PostTemplate
    from app.services.post_service import PostService

    job, dest1 = _make_job_and_destination(db_session, platform="Facebook")
    dest2 = dest1.__class__(
        platform=Platform.FACEBOOK, name="Second FB group", posting_method=dest1.posting_method, active=True
    )
    db_session.add(dest2)
    db_session.add(PostTemplate(name="FB", platform=Platform.FACEBOOK, template_text="{{job_title}}"))
    db_session.commit()

    start = datetime(2026, 1, 1, 18, 0)
    service = PostService(db_session)
    created, errors, warnings = service.create_queue(
        job.id, [dest1.id, dest2.id], start_at=start, delay_minutes=7
    )

    assert errors == []
    assert len(created) == 2
    assert all(p.status == PostStatus.QUEUED for p in created)
    times = sorted(p.scheduled_at for p in created)
    assert times[0] == start
    assert times[1] == datetime(2026, 1, 1, 18, 7)


def test_service_create_queue_warns_on_inactive_destination_but_still_queues(db_session):
    from app.database.enums import Platform, PostingMethod
    from app.database.models import Destination, PostTemplate
    from app.services.post_service import PostService

    job, _ = _make_job_and_destination(db_session)
    inactive_dest = Destination(
        platform=Platform.FACEBOOK, name="Inactive group", posting_method=PostingMethod.BROWSER_ASSISTED,
        active=False,
    )
    db_session.add(inactive_dest)
    db_session.add(PostTemplate(name="FB", platform=Platform.FACEBOOK, template_text="{{job_title}}"))
    db_session.commit()

    service = PostService(db_session)
    created, errors, warnings = service.create_queue(job.id, [inactive_dest.id])

    assert len(created) == 1  # still queued despite the warning
    assert errors == []
    assert any("inactive" in w for w in warnings)


def test_service_create_queue_warns_on_cooldown_not_met(db_session):
    from datetime import timedelta

    from app.database.enums import Platform, PostingMethod
    from app.database.models import Destination, PostTemplate
    from app.services.post_service import PostService
    from app.utils.time_utils import utcnow

    job, _ = _make_job_and_destination(db_session)
    destination = Destination(
        platform=Platform.FACEBOOK, name="Cooldown group", posting_method=PostingMethod.BROWSER_ASSISTED,
        active=True, min_posting_interval_minutes=60, last_posted_at=utcnow() - timedelta(minutes=10),
    )
    db_session.add(destination)
    db_session.add(PostTemplate(name="FB", platform=Platform.FACEBOOK, template_text="{{job_title}}"))
    db_session.commit()

    service = PostService(db_session)
    created, errors, warnings = service.create_queue(job.id, [destination.id])

    assert len(created) == 1
    assert any("cooldown" in w for w in warnings)


def test_service_create_queue_deduplicates_repeated_destination_ids(db_session):
    from app.database.enums import Platform
    from app.database.models import PostTemplate
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session)
    db_session.add(PostTemplate(name="FB", platform=Platform.FACEBOOK, template_text="{{job_title}}"))
    db_session.commit()

    service = PostService(db_session)
    created, errors, warnings = service.create_queue(job.id, [destination.id, destination.id, destination.id])

    assert len(created) == 1  # not 3


def test_service_create_queue_missing_job_raises(db_session):
    from app.services.exceptions import NotFoundError
    from app.services.post_service import PostService

    service = PostService(db_session)
    with pytest.raises(NotFoundError):
        service.create_queue(999, [1])


# --- Phase 6: service — queue actions --------------------------------------


def test_service_queue_existing_post_requires_draft(db_session):
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session)
    service = PostService(db_session)
    post_row = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.QUEUED
    )

    with pytest.raises(ValueError):
        service.queue_existing_post(post_row.id)  # already Queued, not Draft


def test_service_start_requires_queued(db_session):
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session)
    service = PostService(db_session)
    draft = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.DRAFT)

    with pytest.raises(ValueError):
        service.start(draft.id)

    queued = service.repo.create(job_id=job.id, destination_id=destination.id, content="y", status=PostStatus.QUEUED)
    started = service.start(queued.id)
    assert started.status == PostStatus.PROCESSING


def test_service_retry_requires_failed_and_clears_error(db_session):
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session)
    service = PostService(db_session)
    failed = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="x",
        status=PostStatus.FAILED, error_message="Bot lacks permission",
    )

    retried = service.retry(failed.id)
    assert retried.status == PostStatus.QUEUED
    assert retried.error_message is None


def test_service_skip_rejects_already_posted(db_session):
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session)
    service = PostService(db_session)
    posted = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.POSTED)

    with pytest.raises(ValueError):
        service.skip(posted.id)


def test_service_pause_and_resume(db_session):
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session)
    service = PostService(db_session)
    queued = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.QUEUED)

    assert service.set_paused(queued.id, True).paused is True
    assert service.set_paused(queued.id, False).paused is False


def test_service_progress_counts_by_status(db_session):
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session)
    service = PostService(db_session)
    service.repo.create(job_id=job.id, destination_id=destination.id, content="a", status=PostStatus.QUEUED)
    service.repo.create(job_id=job.id, destination_id=destination.id, content="b", status=PostStatus.QUEUED)
    service.repo.create(job_id=job.id, destination_id=destination.id, content="c", status=PostStatus.POSTED)

    result = service.progress()
    assert result["counts"]["Queued"] == 2
    assert result["counts"]["Posted"] == 1
    assert result["total"] == 3


# --- Phase 6: API ------------------------------------------------------


def test_api_create_queue_end_to_end(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    d1 = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()
    d2 = api_client.post(
        "/destinations", json={"platform": "Telegram", "name": "TG1", "posting_method": "API"}
    ).json()

    response = api_client.post(
        "/posts/create-queue",
        json={"job_id": job["id"], "destination_ids": [d1["id"], d2["id"]], "delay_minutes": 10},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["created"]) == 2
    assert all(p["status"] == "Queued" for p in body["created"])
    assert all(p["scheduled_at"] is not None for p in body["created"])


def test_api_queue_promotes_draft(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()
    draft = api_client.post(
        "/posts/generate", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    response = api_client.post(f"/posts/{draft['id']}/queue", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "Queued"


def test_api_queue_promotes_draft_with_explicit_scheduled_at(api_client):
    """queue_existing_post() has always accepted an explicit scheduled_at
    (used_at or utcnow()), but nothing exercised that branch through the
    actual API until the Queue page's bulk "queue all drafts" action
    started relying on it for staggered scheduling — closing that gap
    here rather than leaving it implicitly covered only by a frontend
    feature with no backend test of its own."""
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()
    draft = api_client.post(
        "/posts/generate", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    chosen_time = "2030-06-15T09:30:00"
    response = api_client.post(f"/posts/{draft['id']}/queue", json={"scheduled_at": chosen_time})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Queued"
    assert body["scheduled_at"] == chosen_time


def test_api_bulk_queue_drafts_produces_correctly_staggered_times(api_client):
    """Simulates exactly what the Queue page's "Queue all N drafts"
    button does: generate several drafts, then queue each one with an
    incrementing scheduled_at computed client-side. Verifies the backend
    faithfully stores each distinct value rather than, say, silently
    defaulting all of them to "now" regardless of what's sent."""
    from datetime import datetime, timedelta

    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    dest_ids = []
    for i in range(3):
        d = api_client.post(
            "/destinations",
            json={"platform": "Facebook", "name": f"Group {i}", "posting_method": "Browser-assisted"},
        ).json()
        dest_ids.append(d["id"])

    generated = api_client.post(
        "/posts/generate", json={"job_id": job["id"], "destination_ids": dest_ids}
    ).json()
    draft_ids = [p["id"] for p in generated["created"]]
    assert len(draft_ids) == 3

    base_time = datetime(2030, 1, 1, 12, 0, 0)
    delay_minutes = 5
    for index, draft_id in enumerate(draft_ids):
        scheduled_at = base_time + timedelta(minutes=index * delay_minutes)
        response = api_client.post(f"/posts/{draft_id}/queue", json={"scheduled_at": scheduled_at.isoformat()})
        assert response.status_code == 200

    queued = api_client.get("/posts", params={"status": "Queued", "limit": 200}).json()["items"]
    scheduled_times = sorted(p["scheduled_at"] for p in queued)
    expected = [
        (base_time + timedelta(minutes=i * delay_minutes)).isoformat() for i in range(3)
    ]
    assert scheduled_times == expected

    remaining_drafts = api_client.get("/posts", params={"status": "Draft", "limit": 200}).json()["items"]
    assert remaining_drafts == []


def test_api_start_skip_retry_flow(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    response = api_client.post(f"/posts/{queued['id']}/start")
    assert response.json()["status"] == "Processing"

    # Can't start again from Processing
    response = api_client.post(f"/posts/{queued['id']}/start")
    assert response.status_code == 400

    response = api_client.post(f"/posts/{queued['id']}/skip")
    assert response.json()["status"] == "Skipped"


def test_api_pause_resume(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    assert api_client.post(f"/posts/{queued['id']}/pause").json()["paused"] is True
    assert api_client.post(f"/posts/{queued['id']}/resume").json()["paused"] is False


def test_api_progress_endpoint(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()
    api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    )

    response = api_client.get("/posts/progress")
    assert response.status_code == 200
    body = response.json()
    assert body["counts"]["Queued"] == 1
    assert body["total"] == 1


# --- Phase 7: service — Facebook Assistant ---------------------------------


def test_service_facebook_assist_candidates_includes_queued_and_processing_not_paused(db_session):
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Facebook")
    service = PostService(db_session)
    queued = service.repo.create(job_id=job.id, destination_id=destination.id, content="a", status=PostStatus.QUEUED)
    processing = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="b", status=PostStatus.PROCESSING
    )
    paused_processing = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="c", status=PostStatus.PROCESSING, paused=True
    )
    service.repo.create(job_id=job.id, destination_id=destination.id, content="d", status=PostStatus.POSTED)

    candidate_ids = {p.id for p in service.facebook_assist_candidates()}
    assert candidate_ids == {queued.id, processing.id}
    assert paused_processing.id not in candidate_ids


def test_service_facebook_assist_candidates_excludes_other_platforms(db_session):
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, fb_destination = _make_job_and_destination(db_session, platform="Facebook")
    _, tg_destination = _make_job_and_destination(db_session, platform="Telegram")
    service = PostService(db_session)
    fb_post = service.repo.create(
        job_id=job.id, destination_id=fb_destination.id, content="a", status=PostStatus.QUEUED
    )
    service.repo.create(job_id=job.id, destination_id=tg_destination.id, content="b", status=PostStatus.QUEUED)

    candidates = service.facebook_assist_candidates()
    assert [p.id for p in candidates] == [fb_post.id]


def test_service_facebook_assist_candidates_ordered_by_scheduled_at(db_session):
    from datetime import timedelta

    from app.database.enums import PostStatus
    from app.services.post_service import PostService
    from app.utils.time_utils import utcnow

    job, destination = _make_job_and_destination(db_session, platform="Facebook")
    service = PostService(db_session)
    later = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="later", status=PostStatus.QUEUED,
        scheduled_at=utcnow() + timedelta(minutes=10),
    )
    earlier = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="earlier", status=PostStatus.QUEUED,
        scheduled_at=utcnow(),
    )

    candidates = service.facebook_assist_candidates()
    assert [p.id for p in candidates] == [earlier.id, later.id]


def test_service_start_facebook_assist_transitions_queued_and_calls_integrations(db_session):
    from unittest.mock import patch

    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Facebook")
    destination.url = "https://facebook.com/groups/123"
    db_session.commit()
    service = PostService(db_session)
    queued = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="Hiring now", status=PostStatus.QUEUED
    )

    with patch("app.services.post_service.open_destination", return_value=True) as mock_open, patch(
        "app.services.post_service.copy_content", return_value=True
    ) as mock_copy:
        result_post, browser_opened, clipboard_copied = service.start_facebook_assist(queued.id)

    assert result_post.status == PostStatus.PROCESSING
    assert browser_opened is True
    assert clipboard_copied is True
    mock_open.assert_called_once_with("https://facebook.com/groups/123")
    mock_copy.assert_called_once_with("Hiring now")


def test_service_start_facebook_assist_resumes_processing_without_re_transitioning(db_session):
    from unittest.mock import patch

    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Facebook")
    service = PostService(db_session)
    processing = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.PROCESSING
    )

    with patch("app.services.post_service.open_destination", return_value=False), patch(
        "app.services.post_service.copy_content", return_value=True
    ):
        result_post, _, clipboard_copied = service.start_facebook_assist(processing.id)

    assert result_post.status == PostStatus.PROCESSING  # unchanged, not re-started
    assert clipboard_copied is True


def test_service_start_facebook_assist_rejects_non_facebook_destination(db_session):
    from app.services.post_service import PostService
    from app.database.enums import PostStatus

    job, destination = _make_job_and_destination(db_session, platform="Telegram")
    service = PostService(db_session)
    queued = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.QUEUED)

    with pytest.raises(ValueError):
        service.start_facebook_assist(queued.id)


def test_service_start_facebook_assist_rejects_terminal_status(db_session):
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Facebook")
    service = PostService(db_session)
    posted = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.POSTED)

    with pytest.raises(ValueError):
        service.start_facebook_assist(posted.id)


def test_service_start_facebook_assist_missing_post_raises(db_session):
    from app.services.exceptions import NotFoundError
    from app.services.post_service import PostService

    service = PostService(db_session)
    with pytest.raises(NotFoundError):
        service.start_facebook_assist(999999)


def test_service_mark_posted_requires_processing_and_stamps_timestamps(db_session):
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Facebook")
    service = PostService(db_session)
    queued = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.QUEUED)

    with pytest.raises(ValueError):
        service.mark_posted(queued.id)  # not Processing yet

    processing = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="y", status=PostStatus.PROCESSING
    )
    posted = service.mark_posted(processing.id)

    assert posted.status == PostStatus.POSTED
    assert posted.posted_at is not None

    refreshed_destination = service.destination_repo.get(destination.id)
    assert refreshed_destination.last_posted_at is not None


def test_service_mark_failed_requires_processing_and_defaults_message(db_session):
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Facebook")
    service = PostService(db_session)
    queued = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.QUEUED)

    with pytest.raises(ValueError):
        service.mark_failed(queued.id)

    processing = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="y", status=PostStatus.PROCESSING
    )
    failed = service.mark_failed(processing.id)
    assert failed.status == PostStatus.FAILED
    assert failed.error_message  # non-empty default, not blank

    processing2 = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="z", status=PostStatus.PROCESSING
    )
    failed2 = service.mark_failed(processing2.id, "Group requires admin approval")
    assert failed2.error_message == "Group requires admin approval"


# --- Phase 7: API ------------------------------------------------------


def test_api_facebook_queue_filters_by_platform(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    fb = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()
    tg = api_client.post(
        "/destinations", json={"platform": "Telegram", "name": "TG1", "posting_method": "API"}
    ).json()
    api_client.post("/posts/create-queue", json={"job_id": job["id"], "destination_ids": [fb["id"], tg["id"]]})

    response = api_client.get("/posts/facebook-queue")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["destination_id"] == fb["id"]


def test_api_facebook_assist_then_mark_posted_flow(api_client, monkeypatch):
    from app.services import post_service

    monkeypatch.setattr(post_service, "open_destination", lambda url: True)
    monkeypatch.setattr(post_service, "copy_content", lambda text: True)

    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations",
        json={
            "platform": "Facebook",
            "name": "FB1",
            "url": "https://facebook.com/groups/1",
            "posting_method": "Browser-assisted",
        },
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    response = api_client.post(f"/posts/{queued['id']}/facebook-assist")
    assert response.status_code == 200
    body = response.json()
    assert body["post"]["status"] == "Processing"
    assert body["browser_opened"] is True
    assert body["clipboard_copied"] is True

    # No longer in the working set once Processing has an outcome pending
    # resolution is still fine to re-fetch — it's Processing-not-paused.
    still_listed = api_client.get("/posts/facebook-queue").json()
    assert [p["id"] for p in still_listed] == [queued["id"]]

    posted = api_client.post(f"/posts/{queued['id']}/mark-posted")
    assert posted.status_code == 200
    assert posted.json()["status"] == "Posted"
    assert posted.json()["posted_at"] is not None

    # Resolved now — drops out of the working set entirely.
    assert api_client.get("/posts/facebook-queue").json() == []


def test_api_mark_failed_with_custom_message(api_client, monkeypatch):
    from app.services import post_service

    monkeypatch.setattr(post_service, "open_destination", lambda url: True)
    monkeypatch.setattr(post_service, "copy_content", lambda text: True)

    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]
    api_client.post(f"/posts/{queued['id']}/facebook-assist")

    response = api_client.post(
        f"/posts/{queued['id']}/mark-failed", json={"error_message": "Admin approval needed"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Failed"
    assert response.json()["error_message"] == "Admin approval needed"


def test_api_mark_posted_rejects_non_processing(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    response = api_client.post(f"/posts/{queued['id']}/mark-posted")
    assert response.status_code == 400


def test_api_facebook_assist_rejects_telegram_destination(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Telegram", "name": "TG1", "posting_method": "API"}
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    response = api_client.post(f"/posts/{queued['id']}/facebook-assist")
    assert response.status_code == 400


# --- Phase 8: service — Telegram --------------------------------------


def test_service_send_telegram_post_success_marks_posted_with_message_id(db_session):
    from unittest.mock import patch

    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Telegram")
    destination.external_id = "123456789"
    db_session.commit()
    service = PostService(db_session)
    queued = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="Hiring now", status=PostStatus.QUEUED
    )

    with patch(
        "app.services.post_service.send_message", return_value=(True, "42", None)
    ) as mock_send, patch("app.services.post_service.get_settings") as mock_settings:
        mock_settings.return_value.telegram_bot_token = "fake-token"
        result_post = service.send_telegram_post(queued.id)

    assert result_post.status == PostStatus.POSTED
    assert result_post.external_post_id == "42"
    assert result_post.posted_at is not None
    mock_send.assert_called_once_with("fake-token", "123456789", "Hiring now")

    refreshed_destination = service.destination_repo.get(destination.id)
    assert refreshed_destination.last_posted_at is not None


def test_service_send_telegram_post_failure_marks_failed_with_telegram_description(db_session):
    from unittest.mock import patch

    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Telegram")
    destination.external_id = "wrong-chat"
    db_session.commit()
    service = PostService(db_session)
    queued = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="Hiring now", status=PostStatus.QUEUED
    )

    with patch(
        "app.services.post_service.send_message",
        return_value=(False, None, "Bad Request: chat not found"),
    ):
        result_post = service.send_telegram_post(queued.id)

    assert result_post.status == PostStatus.FAILED
    assert result_post.error_message == "Bad Request: chat not found"
    assert result_post.external_post_id is None


def test_service_send_telegram_post_resumes_from_processing(db_session):
    from unittest.mock import patch

    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Telegram")
    service = PostService(db_session)
    processing = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.PROCESSING
    )

    with patch("app.services.post_service.send_message", return_value=(True, None, None)):
        result_post = service.send_telegram_post(processing.id)

    assert result_post.status == PostStatus.POSTED


def test_service_send_telegram_post_rejects_non_telegram_destination(db_session):
    from app.services.post_service import PostService
    from app.database.enums import PostStatus

    job, destination = _make_job_and_destination(db_session, platform="Facebook")
    service = PostService(db_session)
    queued = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.QUEUED)

    with pytest.raises(ValueError):
        service.send_telegram_post(queued.id)


def test_service_send_telegram_post_rejects_terminal_status(db_session):
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Telegram")
    service = PostService(db_session)
    posted = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.POSTED)

    with pytest.raises(ValueError):
        service.send_telegram_post(posted.id)


def test_service_send_telegram_post_without_token_configured_fails_gracefully(db_session):
    """No mocking at all — exercises the real send_message() against a
    genuinely unconfigured bot token, the same as this dev sandbox's own
    environment (see PROJECT_STATUS.md section 15)."""
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Telegram")
    destination.external_id = "123456789"
    db_session.commit()
    service = PostService(db_session)
    queued = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.QUEUED)

    result_post = service.send_telegram_post(queued.id)

    assert result_post.status == PostStatus.FAILED
    assert "bot token" in result_post.error_message.lower()


# --- Phase 8: API --------------------------------------------------------


def test_api_send_telegram_success_round_trip(api_client, monkeypatch):
    from app.services import post_service

    monkeypatch.setattr(post_service, "send_message", lambda token, chat_id, text: (True, "99", None))

    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations",
        json={"platform": "Telegram", "name": "TG1", "external_id": "123", "posting_method": "API"},
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    response = api_client.post(f"/posts/{queued['id']}/send-telegram")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Posted"
    assert body["external_post_id"] == "99"
    assert body["posted_at"] is not None


def test_api_send_telegram_failure_is_200_not_400(api_client, monkeypatch):
    """A Telegram-side rejection is a business outcome, not a request
    error — it must come back 200 with status=Failed, the same way
    POST .../mark-failed does, not a 4xx/5xx."""
    from app.services import post_service

    monkeypatch.setattr(
        post_service, "send_message", lambda token, chat_id, text: (False, None, "Bad Request: chat not found")
    )

    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Telegram", "name": "TG1", "posting_method": "API"}
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    response = api_client.post(f"/posts/{queued['id']}/send-telegram")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Failed"
    assert body["error_message"] == "Bad Request: chat not found"


def test_api_send_telegram_rejects_facebook_destination(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    response = api_client.post(f"/posts/{queued['id']}/send-telegram")
    assert response.status_code == 400


def test_api_send_telegram_without_bot_token_configured(api_client):
    """No monkeypatching — end to end through real HTTP against the real
    (unconfigured, in this test environment) send_message()."""
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations",
        json={"platform": "Telegram", "name": "TG1", "external_id": "123", "posting_method": "API"},
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    response = api_client.post(f"/posts/{queued['id']}/send-telegram")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Failed"
    assert "bot token" in body["error_message"].lower()


# --- Phase 9: service — TikTok visual generator -------------------------


def test_service_generate_tiktok_visual_success(db_session, tmp_path, monkeypatch):
    from app.database.enums import PostStatus
    from app.services import post_service
    from app.services.post_service import PostService

    monkeypatch.setattr(post_service.get_settings(), "media_dir", str(tmp_path))

    job, destination = _make_job_and_destination(db_session, platform="TikTok")
    service = PostService(db_session)
    queued = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.QUEUED)

    result_post = service.generate_tiktok_visual(queued.id)

    assert result_post.media_path is not None
    assert Path(result_post.media_path).exists()
    assert result_post.status == PostStatus.QUEUED  # unchanged — content-prep only


def test_service_generate_tiktok_visual_works_for_processing_too(db_session, tmp_path, monkeypatch):
    from app.database.enums import PostStatus
    from app.services import post_service
    from app.services.post_service import PostService

    monkeypatch.setattr(post_service.get_settings(), "media_dir", str(tmp_path))

    job, destination = _make_job_and_destination(db_session, platform="TikTok")
    service = PostService(db_session)
    processing = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.PROCESSING
    )

    result_post = service.generate_tiktok_visual(processing.id)
    assert result_post.media_path is not None
    assert result_post.status == PostStatus.PROCESSING


def test_service_generate_tiktok_visual_rejects_non_tiktok_destination(db_session, tmp_path, monkeypatch):
    from app.services import post_service
    from app.services.post_service import PostService
    from app.database.enums import PostStatus

    monkeypatch.setattr(post_service.get_settings(), "media_dir", str(tmp_path))

    job, destination = _make_job_and_destination(db_session, platform="Facebook")
    service = PostService(db_session)
    queued = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.QUEUED)

    with pytest.raises(ValueError):
        service.generate_tiktok_visual(queued.id)


def test_service_generate_tiktok_visual_rejects_posted_and_skipped(db_session, tmp_path, monkeypatch):
    from app.database.enums import PostStatus
    from app.services import post_service
    from app.services.post_service import PostService

    monkeypatch.setattr(post_service.get_settings(), "media_dir", str(tmp_path))

    job, destination = _make_job_and_destination(db_session, platform="TikTok")
    service = PostService(db_session)
    posted = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.POSTED)
    skipped = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="y", status=PostStatus.SKIPPED
    )

    with pytest.raises(ValueError):
        service.generate_tiktok_visual(posted.id)
    with pytest.raises(ValueError):
        service.generate_tiktok_visual(skipped.id)


def test_service_generate_tiktok_visual_regenerate_overwrites_same_path(db_session, tmp_path, monkeypatch):
    from app.database.enums import PostStatus
    from app.services import post_service
    from app.services.post_service import PostService

    monkeypatch.setattr(post_service.get_settings(), "media_dir", str(tmp_path))

    job, destination = _make_job_and_destination(db_session, platform="TikTok")
    service = PostService(db_session)
    queued = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.QUEUED)

    first = service.generate_tiktok_visual(queued.id)
    second = service.generate_tiktok_visual(queued.id)
    assert first.media_path == second.media_path


# --- Phase 9: API --------------------------------------------------------


def test_api_generate_tiktok_visual_success(api_client, tmp_path, monkeypatch):
    from app.services import post_service

    monkeypatch.setattr(post_service.get_settings(), "media_dir", str(tmp_path))

    job = api_client.post("/jobs", json={"title": "Delivery Rider", "company": "Acme Co"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "TikTok", "name": "TT1", "posting_method": "Manual"}
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    response = api_client.post(f"/posts/{queued['id']}/generate-tiktok-visual")
    assert response.status_code == 200
    body = response.json()
    assert body["media_path"] is not None
    assert Path(body["media_path"]).exists()


def test_api_generate_tiktok_visual_rejects_facebook_destination(api_client, tmp_path, monkeypatch):
    from app.services import post_service

    monkeypatch.setattr(post_service.get_settings(), "media_dir", str(tmp_path))

    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    response = api_client.post(f"/posts/{queued['id']}/generate-tiktok-visual")
    assert response.status_code == 400


def test_api_tiktok_manual_flow_resolves_via_generic_mark_posted(api_client, tmp_path, monkeypatch):
    """The Phase 9 gap-closing scenario end to end: a TikTok/MANUAL post
    has no dedicated assistant page and no one-click send — Start then
    the already-existing (Phase 7) generic mark-posted is how it actually
    gets resolved. Confirms that path genuinely works for this platform,
    not just Facebook/Telegram."""
    from app.services import post_service

    monkeypatch.setattr(post_service.get_settings(), "media_dir", str(tmp_path))

    job = api_client.post("/jobs", json={"title": "Delivery Rider"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "TikTok", "name": "TT1", "posting_method": "Manual"}
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    api_client.post(f"/posts/{queued['id']}/generate-tiktok-visual")
    started = api_client.post(f"/posts/{queued['id']}/start")
    assert started.json()["status"] == "Processing"

    resolved = api_client.post(f"/posts/{queued['id']}/mark-posted")
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "Posted"
    assert resolved.json()["posted_at"] is not None
    # media_path survives the status transitions — mark_posted only
    # touches status/posted_at/external_post_id.
    assert resolved.json()["media_path"] is not None


# --- Phase 10: service — schedule/unschedule -----------------------------


def test_service_schedule_requires_queued_and_a_scheduled_at(db_session):
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Telegram")
    service = PostService(db_session)

    no_time = service.repo.create(job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.QUEUED)
    with pytest.raises(ValueError):
        service.schedule(no_time.id)  # no scheduled_at set

    from app.utils.time_utils import utcnow

    queued = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="y", status=PostStatus.QUEUED, scheduled_at=utcnow()
    )
    scheduled = service.schedule(queued.id)
    assert scheduled.status == PostStatus.SCHEDULED

    with pytest.raises(ValueError):
        service.schedule(scheduled.id)  # already Scheduled, not Queued


def test_service_unschedule_reverses_schedule(db_session):
    from app.database.enums import PostStatus
    from app.services.post_service import PostService
    from app.utils.time_utils import utcnow

    job, destination = _make_job_and_destination(db_session, platform="Telegram")
    service = PostService(db_session)
    queued = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.QUEUED, scheduled_at=utcnow()
    )
    scheduled = service.schedule(queued.id)

    unscheduled = service.unschedule(scheduled.id)
    assert unscheduled.status == PostStatus.QUEUED

    with pytest.raises(ValueError):
        service.unschedule(unscheduled.id)  # already Queued, not Scheduled


def test_service_start_accepts_scheduled_posts(db_session):
    """Regression coverage for the exact gap the scheduler tests caught:
    start() must accept Scheduled, not just Queued, since Phase 10's
    ticker starts due posts the same way a human clicking Start does."""
    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Telegram")
    service = PostService(db_session)
    scheduled = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.SCHEDULED
    )

    started = service.start(scheduled.id)
    assert started.status == PostStatus.PROCESSING


def test_service_send_telegram_post_accepts_scheduled_posts(db_session):
    from unittest.mock import patch

    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Telegram")
    service = PostService(db_session)
    scheduled = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.SCHEDULED
    )

    with patch("app.services.post_service.send_message", return_value=(True, "1", None)):
        result_post = service.send_telegram_post(scheduled.id)
    assert result_post.status == PostStatus.POSTED


def test_service_start_facebook_assist_accepts_scheduled_posts(db_session):
    from unittest.mock import patch

    from app.database.enums import PostStatus
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session, platform="Facebook")
    service = PostService(db_session)
    scheduled = service.repo.create(
        job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.SCHEDULED
    )

    with patch("app.services.post_service.open_destination", return_value=True), patch(
        "app.services.post_service.copy_content", return_value=True
    ):
        result_post, _, _ = service.start_facebook_assist(scheduled.id)
    assert result_post.status == PostStatus.PROCESSING


# --- Phase 10: API ---------------------------------------------------------


def test_api_schedule_and_unschedule_round_trip(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Telegram", "name": "TG1", "posting_method": "API"}
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]

    scheduled = api_client.post(f"/posts/{queued['id']}/schedule")
    assert scheduled.status_code == 200
    assert scheduled.json()["status"] == "Scheduled"

    unscheduled = api_client.post(f"/posts/{queued['id']}/unschedule")
    assert unscheduled.status_code == 200
    assert unscheduled.json()["status"] == "Queued"


def test_api_schedule_rejects_non_queued(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Telegram", "name": "TG1", "posting_method": "API"}
    ).json()
    queued = api_client.post(
        "/posts/create-queue", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()["created"][0]
    api_client.post(f"/posts/{queued['id']}/schedule")

    response = api_client.post(f"/posts/{queued['id']}/schedule")
    assert response.status_code == 400
