"""Phase 1 foundation tests.

Phase 13: test_health_endpoint now uses the same tmp_path +
DATABASE_URL-override isolation every other test file's api_client
fixture already uses, rather than running against whatever the real
DATABASE_URL happens to resolve to. Kept as the plain env-var pattern
(not FastAPI's dependency_overrides) specifically for consistency with
every other test file — introducing a second isolation mechanism for
one test would leave two different patterns solving the same problem
across the suite, which is worse than either alone.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.database import models  # noqa: F401  (registers models on Base)
from app.database.database import Base


@pytest.fixture()
def db_session():
    """An isolated in-memory SQLite database, fresh for each test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def test_settings_load():
    settings = get_settings()
    assert settings.app_name
    assert settings.database_url.startswith("sqlite:///")


def test_tables_created(db_session):
    rows = db_session.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    table_names = {row[0] for row in rows}
    expected = {
        "jobs",
        "destinations",
        "post_templates",
        "posts",
        "application_metrics",
        "tags",
        "destination_tags",
    }
    assert expected.issubset(table_names)


def test_create_job(db_session):
    from app.database.enums import JobStatus
    from app.database.models import Job

    job = Job(
        title="Customer Service Representative",
        company="Test Co",
        location="Cairo",
        status=JobStatus.DRAFT,
    )
    db_session.add(job)
    db_session.commit()

    fetched = db_session.query(Job).first()
    assert fetched.title == "Customer Service Representative"
    assert fetched.status == JobStatus.DRAFT
    assert fetched.created_at is not None


def test_destination_tags_many_to_many(db_session):
    from app.database.enums import Platform, PostingMethod
    from app.database.models import Destination, Tag

    destination = Destination(
        platform=Platform.FACEBOOK,
        name="Cairo English Call Center Jobs",
        posting_method=PostingMethod.BROWSER_ASSISTED,
    )
    destination.tags = [Tag(name="Cairo"), Tag(name="English"), Tag(name="Call Center")]
    db_session.add(destination)
    db_session.commit()

    fetched = db_session.query(Destination).first()
    assert {tag.name for tag in fetched.tags} == {"Cairo", "English", "Call Center"}


def test_health_endpoint(monkeypatch, tmp_path):
    # Phase 13: isolated DATABASE_URL, same pattern as every other test
    # file's api_client fixture — this was the one test in the suite
    # that didn't have it (flagged since Phase 1, fixed here).
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test_foundation.db")
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")

    from app.config.settings import get_settings

    get_settings.cache_clear()

    from app.database import database

    database.get_engine.cache_clear()

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"

    get_settings.cache_clear()
    database.get_engine.cache_clear()


def test_setup_logging_silences_httpx_request_logging():
    """Phase 13: regression coverage for a real Phase 12 security fix
    that had zero automated test protecting it until now. httpx (and
    httpcore underneath it) logs every request's full URL at INFO level
    by default — since Telegram's Bot API embeds the bot token directly
    in the URL, this was writing the token straight into logs/app.log
    before app/config/logging.py explicitly raised these two loggers to
    WARNING (confirmed with a real fake-token repro at the time — see
    PROJECT_STATUS.md section 13/16). Without this test, a future change
    to logging.py could silently reintroduce the leak and nothing would
    catch it."""
    import logging

    import app.config.logging as logging_module

    # setup_logging() is idempotent (a module-level _configured flag
    # short-circuits every call after the first) — by the time this test
    # runs, some earlier test in the session has almost certainly already
    # triggered it once via importing app.main, so calling it again here
    # would silently no-op and this test would pass or fail depending on
    # test execution order rather than on what setup_logging() actually
    # does. Resetting both the flag and the loggers' levels first makes
    # this test deterministic regardless of what ran before it.
    logging_module._configured = False
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    logging.getLogger("httpcore").setLevel(logging.NOTSET)

    logging_module.setup_logging()

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
