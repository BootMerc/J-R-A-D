"""Phase 11 tests: MetricRepository, AnalyticsService (log_metric's
upsert behavior, funnel_summary, performance_by_destination,
performance_by_template), and the metrics/analytics API.
"""

from datetime import date, timedelta

import pytest
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
    """A TestClient bound to its own isolated SQLite file."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test_analytics.db")
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


# --- Repository ------------------------------------------------------------


def test_repository_create_and_get(db_session):
    from app.database.repositories.metric_repository import MetricRepository

    job, destination = _make_job_and_destination(db_session)
    repo = MetricRepository(db_session)
    metric = repo.create(job_id=job.id, destination_id=destination.id, date=date.today(), views=10)

    fetched = repo.get(metric.id)
    assert fetched.views == 10


def test_repository_find_one_distinguishes_by_post_id(db_session):
    """The exact bug caught during live verification: a metric tied to
    one post and a metric with no post_id must be treated as different
    entries for the same day, not the same one."""
    from app.database.enums import PostStatus
    from app.database.repositories.metric_repository import MetricRepository

    job, destination = _make_job_and_destination(db_session)
    repo = MetricRepository(db_session)
    from app.services.post_service import PostService

    post_service = PostService(db_session)
    post_a = post_service.repo.create(
        job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.POSTED
    )
    today = date.today()

    repo.create(job_id=job.id, destination_id=destination.id, date=today, post_id=post_a.id, views=500)
    repo.create(job_id=job.id, destination_id=destination.id, date=today, post_id=None, views=20)

    with_post = repo.find_one(job.id, destination.id, today, post_id=post_a.id)
    without_post = repo.find_one(job.id, destination.id, today, post_id=None)

    assert with_post is not None and with_post.views == 500
    assert without_post is not None and without_post.views == 20
    assert with_post.id != without_post.id


def test_repository_find_one_matches_natural_key(db_session):
    from app.database.repositories.metric_repository import MetricRepository

    job, destination = _make_job_and_destination(db_session)
    repo = MetricRepository(db_session)
    today = date.today()
    repo.create(job_id=job.id, destination_id=destination.id, date=today, views=5)

    found = repo.find_one(job.id, destination.id, today)
    assert found is not None
    assert found.views == 5

    assert repo.find_one(job.id, destination.id, today - timedelta(days=1)) is None


def test_repository_list_filters_by_date_range(db_session):
    from app.database.repositories.metric_repository import MetricRepository

    job, destination = _make_job_and_destination(db_session)
    repo = MetricRepository(db_session)
    today = date.today()
    repo.create(job_id=job.id, destination_id=destination.id, date=today - timedelta(days=10), views=1)
    repo.create(job_id=job.id, destination_id=destination.id, date=today, views=2)

    recent = repo.list(job_id=job.id, date_from=today - timedelta(days=1))
    assert [m.views for m in recent] == [2]


def test_repository_delete(db_session):
    from app.database.repositories.metric_repository import MetricRepository

    job, destination = _make_job_and_destination(db_session)
    repo = MetricRepository(db_session)
    metric = repo.create(job_id=job.id, destination_id=destination.id, date=date.today())

    repo.delete(metric.id)
    assert repo.get(metric.id) is None


# --- Service: log_metric's upsert behavior ----------------------------------


def test_service_log_metric_creates_when_none_exists(db_session):
    from app.services.analytics_service import AnalyticsService

    job, destination = _make_job_and_destination(db_session)
    service = AnalyticsService(db_session)

    metric = service.log_metric(job_id=job.id, destination_id=destination.id, views=10, clicks=3)
    assert metric.views == 10
    assert metric.clicks == 3
    assert metric.date == date.today()


def test_service_log_metric_updates_existing_same_day_entry(db_session):
    """The core upsert behavior — re-submitting today's numbers updates
    the same row rather than creating a second one."""
    from app.services.analytics_service import AnalyticsService

    job, destination = _make_job_and_destination(db_session)
    service = AnalyticsService(db_session)

    first = service.log_metric(job_id=job.id, destination_id=destination.id, views=10)
    second = service.log_metric(job_id=job.id, destination_id=destination.id, views=25, applications=2)

    assert first.id == second.id
    assert second.views == 25
    assert second.applications == 2
    assert len(service.list_metrics(job_id=job.id)) == 1


def test_service_log_metric_different_dates_create_separate_rows(db_session):
    from app.services.analytics_service import AnalyticsService

    job, destination = _make_job_and_destination(db_session)
    service = AnalyticsService(db_session)

    service.log_metric(job_id=job.id, destination_id=destination.id, date=date.today(), views=10)
    service.log_metric(
        job_id=job.id, destination_id=destination.id, date=date.today() - timedelta(days=1), views=20
    )

    assert len(service.list_metrics(job_id=job.id)) == 2


def test_service_log_metric_different_posts_same_day_create_separate_rows(db_session):
    """Regression test for a real bug caught during live verification:
    logging metrics for two different posts (or one post plus a
    no-post-id entry) against the same destination on the same day must
    NOT collide — see MetricRepository.find_one's docstring."""
    from app.database.enums import PostStatus
    from app.services.analytics_service import AnalyticsService
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session)
    post_service = PostService(db_session)
    post_a = post_service.repo.create(
        job_id=job.id, destination_id=destination.id, content="x", status=PostStatus.POSTED
    )
    post_b = post_service.repo.create(
        job_id=job.id, destination_id=destination.id, content="y", status=PostStatus.POSTED
    )

    service = AnalyticsService(db_session)
    service.log_metric(job_id=job.id, destination_id=destination.id, post_id=post_a.id, views=500)
    service.log_metric(job_id=job.id, destination_id=destination.id, post_id=post_b.id, views=300)
    service.log_metric(job_id=job.id, destination_id=destination.id, views=20)  # no post_id

    all_metrics = service.list_metrics(job_id=job.id)
    assert len(all_metrics) == 3
    assert {m.views for m in all_metrics} == {500, 300, 20}
    assert service.funnel_summary(job_id=job.id)["views"] == 820


def test_service_delete_metric_missing_raises(db_session):
    from app.services.analytics_service import AnalyticsService
    from app.services.exceptions import NotFoundError

    service = AnalyticsService(db_session)
    with pytest.raises(NotFoundError):
        service.delete_metric(999999)


# --- Service: aggregations --------------------------------------------------


def test_service_funnel_summary_sums_across_matching_rows(db_session):
    from app.services.analytics_service import AnalyticsService

    job, destination = _make_job_and_destination(db_session)
    service = AnalyticsService(db_session)
    service.log_metric(
        job_id=job.id, destination_id=destination.id, date=date.today(),
        views=100, clicks=20, messages=5, applications=3, interviews=2, hires=1,
    )
    service.log_metric(
        job_id=job.id, destination_id=destination.id, date=date.today() - timedelta(days=1),
        views=50, clicks=10, applications=1,
    )

    summary = service.funnel_summary(job_id=job.id)
    assert summary == {"views": 150, "clicks": 30, "messages": 5, "applications": 4, "interviews": 2, "hires": 1}


def test_service_funnel_summary_respects_date_range(db_session):
    from app.services.analytics_service import AnalyticsService

    job, destination = _make_job_and_destination(db_session)
    service = AnalyticsService(db_session)
    service.log_metric(job_id=job.id, destination_id=destination.id, date=date.today(), views=100)
    service.log_metric(
        job_id=job.id, destination_id=destination.id, date=date.today() - timedelta(days=30), views=999
    )

    summary = service.funnel_summary(job_id=job.id, date_from=date.today() - timedelta(days=1))
    assert summary["views"] == 100


def test_service_performance_by_destination_groups_and_sorts(db_session):
    from app.services.analytics_service import AnalyticsService

    job, dest_a = _make_job_and_destination(db_session, platform="Facebook")
    _, dest_b = _make_job_and_destination(db_session, platform="Telegram")
    service = AnalyticsService(db_session)
    service.log_metric(job_id=job.id, destination_id=dest_a.id, views=10, applications=1)
    service.log_metric(job_id=job.id, destination_id=dest_b.id, views=50, applications=5)

    results = service.performance_by_destination(job_id=job.id)
    assert len(results) == 2
    # Sorted by applications descending — dest_b (5) before dest_a (1).
    assert results[0]["destination_id"] == dest_b.id
    assert results[0]["platform"] == "Telegram"
    assert results[0]["applications"] == 5


def test_service_performance_by_destination_skips_deleted_destination(db_session):
    from app.services.analytics_service import AnalyticsService

    job, destination = _make_job_and_destination(db_session)
    service = AnalyticsService(db_session)
    service.log_metric(job_id=job.id, destination_id=destination.id, views=10)

    db_session.delete(destination)
    db_session.commit()

    results = service.performance_by_destination(job_id=job.id)
    assert results == []


def test_service_performance_by_template_correlates_via_post(db_session):
    from app.database.enums import PostStatus
    from app.database.models import PostTemplate
    from app.services.analytics_service import AnalyticsService
    from app.services.post_service import PostService

    job, destination = _make_job_and_destination(db_session)
    template = PostTemplate(name="Friendly tone", platform=destination.platform, template_text="Hiring: {{title}}")
    db_session.add(template)
    db_session.commit()

    post_service = PostService(db_session)
    post = post_service.repo.create(
        job_id=job.id, destination_id=destination.id, template_id=template.id,
        content="Hiring: Cashier", status=PostStatus.POSTED,
    )

    service = AnalyticsService(db_session)
    service.log_metric(job_id=job.id, destination_id=destination.id, post_id=post.id, views=40, applications=4)

    results = service.performance_by_template(job_id=job.id)
    assert len(results) == 1
    assert results[0]["template_id"] == template.id
    assert results[0]["template_name"] == "Friendly tone"
    assert results[0]["post_count"] == 1
    assert results[0]["applications"] == 4


def test_service_performance_by_template_excludes_metrics_without_post_id(db_session):
    from app.services.analytics_service import AnalyticsService

    job, destination = _make_job_and_destination(db_session)
    service = AnalyticsService(db_session)
    service.log_metric(job_id=job.id, destination_id=destination.id, views=40)  # no post_id

    results = service.performance_by_template(job_id=job.id)
    assert results == []


# --- API ---------------------------------------------------------------


def test_api_log_metric_upserts_on_repeat_call(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()

    first = api_client.post(
        "/metrics", json={"job_id": job["id"], "destination_id": destination["id"], "views": 10}
    ).json()
    second = api_client.post(
        "/metrics", json={"job_id": job["id"], "destination_id": destination["id"], "views": 30, "applications": 2}
    ).json()

    assert first["id"] == second["id"]
    assert second["views"] == 30
    assert second["applications"] == 2

    listed = api_client.get("/metrics", params={"job_id": job["id"]}).json()
    assert listed["total"] == 1


def test_api_delete_metric(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()
    metric = api_client.post(
        "/metrics", json={"job_id": job["id"], "destination_id": destination["id"], "views": 10}
    ).json()

    response = api_client.delete(f"/metrics/{metric['id']}")
    assert response.status_code == 204

    missing = api_client.delete(f"/metrics/{metric['id']}")
    assert missing.status_code == 404


def test_api_funnel_endpoint(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()
    api_client.post(
        "/metrics",
        json={
            "job_id": job["id"], "destination_id": destination["id"],
            "views": 100, "clicks": 20, "applications": 5, "hires": 1,
        },
    )

    response = api_client.get("/analytics/funnel", params={"job_id": job["id"]})
    assert response.status_code == 200
    body = response.json()
    assert body["views"] == 100
    assert body["hires"] == 1


def test_api_by_destination_endpoint(api_client):
    job = api_client.post("/jobs", json={"title": "Cashier"}).json()
    fb = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()
    tg = api_client.post(
        "/destinations", json={"platform": "Telegram", "name": "TG1", "posting_method": "API"}
    ).json()
    api_client.post("/metrics", json={"job_id": job["id"], "destination_id": fb["id"], "views": 10})
    api_client.post("/metrics", json={"job_id": job["id"], "destination_id": tg["id"], "views": 90})

    response = api_client.get("/analytics/by-destination", params={"job_id": job["id"]})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {row["destination_id"] for row in body} == {fb["id"], tg["id"]}


def test_api_by_template_endpoint_end_to_end(api_client):
    """Uses the real /posts/generate flow (not a direct DB insert) so the
    post genuinely has a template_id the way production usage would."""
    job = api_client.post(
        "/jobs", json={"title": "Cashier", "company": "Store Co", "location": "Cairo"}
    ).json()
    destination = api_client.post(
        "/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"}
    ).json()

    generated = api_client.post(
        "/posts/generate", json={"job_id": job["id"], "destination_ids": [destination["id"]]}
    ).json()
    post = generated["created"][0]
    assert post["template_id"] is not None

    api_client.post(
        "/metrics",
        json={"job_id": job["id"], "destination_id": destination["id"], "post_id": post["id"], "applications": 3},
    )

    response = api_client.get("/analytics/by-template", params={"job_id": job["id"]})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["template_id"] == post["template_id"]
    assert body[0]["applications"] == 3
    assert body[0]["post_count"] == 1
