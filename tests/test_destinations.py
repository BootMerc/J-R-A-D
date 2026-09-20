"""Phase 3 tests: Destination repository, service, and API layers."""

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
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test_destinations.db")
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


# --- Repository ---------------------------------------------------------


def test_repository_create_with_tags(db_session):
    from app.database.enums import Platform, PostingMethod
    from app.database.repositories.destination_repository import DestinationRepository

    repo = DestinationRepository(db_session)
    destination = repo.create(
        platform=Platform.FACEBOOK,
        name="Cairo Jobs",
        posting_method=PostingMethod.BROWSER_ASSISTED,
        tag_names=["Cairo", "Call Center"],
    )

    assert destination.id is not None
    assert {t.name for t in destination.tags} == {"Cairo", "Call Center"}


def test_repository_tag_reuse_is_case_insensitive(db_session):
    from app.database.enums import Platform, PostingMethod
    from app.database.repositories.destination_repository import DestinationRepository

    repo = DestinationRepository(db_session)
    repo.create(
        platform=Platform.FACEBOOK, name="First", posting_method=PostingMethod.BROWSER_ASSISTED,
        tag_names=["Cairo"],
    )
    repo.create(
        platform=Platform.TELEGRAM, name="Second", posting_method=PostingMethod.API,
        tag_names=["cairo", "CAIRO"],  # different casing, same tag, plus an in-list duplicate
    )

    from app.database.models import Tag

    assert db_session.query(Tag).filter(Tag.name.ilike("cairo")).count() == 1


def test_repository_filter_by_platform_and_tag(db_session):
    from app.database.enums import Platform, PostingMethod
    from app.database.repositories.destination_repository import DestinationRepository

    repo = DestinationRepository(db_session)
    repo.create(
        platform=Platform.FACEBOOK, name="Cairo FB", posting_method=PostingMethod.BROWSER_ASSISTED,
        tag_names=["Cairo"],
    )
    repo.create(
        platform=Platform.TELEGRAM, name="Cairo TG", posting_method=PostingMethod.API,
        tag_names=["Cairo"],
    )
    repo.create(
        platform=Platform.FACEBOOK, name="Giza FB", posting_method=PostingMethod.BROWSER_ASSISTED,
        tag_names=["Giza"],
    )

    assert {d.name for d in repo.list(platform=Platform.FACEBOOK)} == {"Cairo FB", "Giza FB"}
    assert {d.name for d in repo.list(tag="Cairo")} == {"Cairo TG", "Cairo FB"}


def test_repository_delete(db_session):
    from app.database.enums import Platform, PostingMethod
    from app.database.repositories.destination_repository import DestinationRepository

    repo = DestinationRepository(db_session)
    destination = repo.create(platform=Platform.FACEBOOK, name="Temp", posting_method=PostingMethod.BROWSER_ASSISTED)

    assert repo.delete(destination.id) is True
    assert repo.get(destination.id) is None
    assert repo.delete(999) is False


def test_repository_distinct_categories(db_session):
    from app.database.enums import Platform, PostingMethod
    from app.database.repositories.destination_repository import DestinationRepository

    repo = DestinationRepository(db_session)
    repo.create(platform=Platform.FACEBOOK, name="A", posting_method=PostingMethod.BROWSER_ASSISTED, category="Call Center")
    repo.create(platform=Platform.FACEBOOK, name="B", posting_method=PostingMethod.BROWSER_ASSISTED, category="IT Jobs")
    repo.create(platform=Platform.FACEBOOK, name="C", posting_method=PostingMethod.BROWSER_ASSISTED, category=None)

    assert repo.distinct_categories() == ["Call Center", "IT Jobs"]


# --- Service (CSV import/export) -----------------------------------------


def test_service_import_csv_valid_rows(db_session):
    from app.services.destination_service import DestinationService

    csv_text = (
        "platform,name,url,category,location,audience,language,posting_method,active,notes,tags\n"
        "Facebook,Cairo Jobs,https://facebook.com/groups/example,Call Center,Cairo,Job seekers,English,,true,,Cairo|Call Center\n"
        "Telegram,Tech Channel,https://t.me/example,IT Jobs,Cairo,Devs,English,,true,,IT Jobs\n"
    )
    service = DestinationService(db_session)
    result = service.import_csv(csv_text)

    assert result.created == 2
    assert result.errors == []

    items, total = service.list()
    assert total == 2
    fb = next(d for d in items if d.name == "Cairo Jobs")
    assert fb.platform.value == "Facebook"
    # posting_method left blank in the CSV -> platform default applied
    assert fb.posting_method.value == "Browser-assisted"
    assert {t.name for t in fb.tags} == {"Cairo", "Call Center"}


def test_service_import_csv_reports_row_errors_without_aborting(db_session):
    from app.services.destination_service import DestinationService

    csv_text = (
        "platform,name\n"
        "Facebook,Good Row\n"
        "Instagram,Bad Platform\n"
        ",Missing Platform\n"
        "Telegram,\n"
    )
    service = DestinationService(db_session)
    result = service.import_csv(csv_text)

    assert result.created == 1  # only "Good Row" succeeds
    assert len(result.errors) == 3
    assert any("Row 3" in e and "Instagram" in e for e in result.errors)
    assert any("Row 4" in e for e in result.errors)
    assert any("Row 5" in e for e in result.errors)


def test_service_import_csv_missing_required_columns(db_session):
    from app.services.destination_service import DestinationService

    service = DestinationService(db_session)
    result = service.import_csv("category,location\nCall Center,Cairo\n")

    assert result.created == 0
    assert "platform" in result.errors[0]


def test_service_export_then_reimport_round_trips(db_session):
    from app.database.enums import Platform, PostingMethod
    from app.services.destination_service import DestinationService

    service = DestinationService(db_session)
    service.repo.create(
        platform=Platform.FACEBOOK, name="Round Trip Group", posting_method=PostingMethod.BROWSER_ASSISTED,
        category="Call Center", location="Cairo", tag_names=["Cairo", "Call Center"],
    )

    csv_text = service.export_csv()
    assert "Round Trip Group" in csv_text
    assert "Cairo|Call Center" in csv_text or "Call Center|Cairo" in csv_text

    # Reimporting the export shouldn't error and should produce a second,
    # independent destination with the same tags reused (not duplicated).
    result = service.import_csv(csv_text)
    assert result.created == 1
    assert result.errors == []

    from app.database.models import Tag

    assert db_session.query(Tag).filter(Tag.name == "Cairo").count() == 1


def test_service_sample_csv_imports_cleanly(db_session):
    """The actual samples/sample_destinations.csv shipped with the project
    must be valid input, not just documentation."""
    from pathlib import Path

    from app.services.destination_service import DestinationService

    sample_path = Path(__file__).resolve().parent.parent / "samples" / "sample_destinations.csv"
    csv_text = sample_path.read_text(encoding="utf-8")

    service = DestinationService(db_session)
    result = service.import_csv(csv_text)

    assert result.errors == []
    assert result.created == 20


# --- API -------------------------------------------------------------------


def test_api_create_with_tags_and_get(api_client):
    response = api_client.post(
        "/destinations",
        json={
            "platform": "Facebook",
            "name": "Cairo Jobs",
            "posting_method": "Browser-assisted",
            "tags": ["Cairo", "Call Center"],
        },
    )
    assert response.status_code == 201
    created = response.json()
    assert set(created["tags"]) == {"Cairo", "Call Center"}
    assert created["active"] is True

    response = api_client.get(f"/destinations/{created['id']}")
    assert response.status_code == 200
    assert set(response.json()["tags"]) == {"Cairo", "Call Center"}


def test_api_get_missing_destination_returns_404(api_client):
    assert api_client.get("/destinations/999999").status_code == 404


def test_api_update_tags_replaces_them(api_client):
    created = api_client.post(
        "/destinations",
        json={"platform": "Telegram", "name": "Tech", "posting_method": "API", "tags": ["Cairo"]},
    ).json()

    response = api_client.patch(f"/destinations/{created['id']}", json={"tags": ["Giza", "IT Jobs"]})
    assert response.status_code == 200
    assert set(response.json()["tags"]) == {"Giza", "IT Jobs"}


def test_api_update_without_tags_field_leaves_tags_untouched(api_client):
    created = api_client.post(
        "/destinations",
        json={"platform": "Telegram", "name": "Tech", "posting_method": "API", "tags": ["Cairo"]},
    ).json()

    response = api_client.patch(f"/destinations/{created['id']}", json={"name": "Tech Renamed"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Tech Renamed"
    assert body["tags"] == ["Cairo"]


def test_api_activate_and_deactivate(api_client):
    created = api_client.post(
        "/destinations",
        json={"platform": "Facebook", "name": "X", "posting_method": "Browser-assisted", "active": True},
    ).json()

    response = api_client.post(f"/destinations/{created['id']}/deactivate")
    assert response.json()["active"] is False

    response = api_client.post(f"/destinations/{created['id']}/activate")
    assert response.json()["active"] is True


def test_api_delete(api_client):
    created = api_client.post(
        "/destinations",
        json={"platform": "Facebook", "name": "Temp", "posting_method": "Browser-assisted"},
    ).json()

    response = api_client.delete(f"/destinations/{created['id']}")
    assert response.status_code == 204
    assert api_client.get(f"/destinations/{created['id']}").status_code == 404
    assert api_client.delete(f"/destinations/{created['id']}").status_code == 404


def test_api_filter_options(api_client):
    api_client.post(
        "/destinations",
        json={"platform": "Facebook", "name": "A", "posting_method": "Browser-assisted", "category": "Call Center"},
    )
    response = api_client.get("/destinations/filter-options")
    assert response.status_code == 200
    assert "Call Center" in response.json()["categories"]


def test_api_import_csv_endpoint(api_client):
    csv_bytes = (
        b"platform,name,category\n"
        b"Facebook,Imported Group,Call Center\n"
    )
    response = api_client.post(
        "/destinations/import-csv",
        files={"file": ("destinations.csv", csv_bytes, "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 1
    assert body["errors"] == []


def test_api_export_csv_endpoint(api_client):
    api_client.post(
        "/destinations",
        json={"platform": "Facebook", "name": "Export Me", "posting_method": "Browser-assisted"},
    )
    response = api_client.get("/destinations/export-csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "Export Me" in response.text


def test_api_platform_filter(api_client):
    api_client.post("/destinations", json={"platform": "Facebook", "name": "FB1", "posting_method": "Browser-assisted"})
    api_client.post("/destinations", json={"platform": "Telegram", "name": "TG1", "posting_method": "API"})

    response = api_client.get("/destinations", params={"platform": "Telegram"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "TG1"
