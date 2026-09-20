"""Phase 2 tests: Job repository, service, and API layers."""

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
    """A TestClient bound to its own isolated SQLite file, so API tests
    never touch the real dev database (data/recruitment.db)."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test_jobs.db")
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


def test_repository_create_and_get(db_session):
    from app.database.repositories.job_repository import JobRepository

    repo = JobRepository(db_session)
    job = repo.create(title="Warehouse Associate", company="Acme")

    assert job.id is not None
    assert repo.get(job.id).title == "Warehouse Associate"


def test_repository_search_and_status_filter(db_session):
    from app.database.enums import JobStatus
    from app.database.repositories.job_repository import JobRepository

    repo = JobRepository(db_session)
    repo.create(title="Cairo Call Center Agent", location="Cairo", status=JobStatus.ACTIVE)
    repo.create(title="Alexandria Sales Rep", location="Alexandria", status=JobStatus.DRAFT)

    assert [j.location for j in repo.list(search="Cairo")] == ["Cairo"]
    assert [j.status for j in repo.list(status=JobStatus.ACTIVE)] == [JobStatus.ACTIVE]


def test_repository_archived_excluded_by_default(db_session):
    from app.database.repositories.job_repository import JobRepository

    repo = JobRepository(db_session)
    job = repo.create(title="Old posting", archived=True)

    assert repo.list() == []
    assert repo.list(include_archived=True)[0].id == job.id


# --- Service -------------------------------------------------------------


def test_service_rejects_bad_salary_range(db_session):
    from app.schemas.job import JobCreate
    from app.services.job_service import JobService

    service = JobService(db_session)
    with pytest.raises(ValueError):
        service.create(JobCreate(title="Bad range job", salary_min=20000, salary_max=10000))


def test_service_duplicate_resets_to_draft(db_session):
    from app.database.enums import JobStatus
    from app.schemas.job import JobCreate
    from app.services.job_service import JobService

    service = JobService(db_session)
    original = service.create(JobCreate(title="Sales Rep", company="Acme"))
    service.set_status(original.id, JobStatus.ACTIVE)  # duplicate a non-Draft job on purpose

    duplicate = service.duplicate(original.id)

    assert duplicate.id != original.id
    assert duplicate.title == "Sales Rep (Copy)"
    assert duplicate.company == "Acme"
    assert duplicate.status == JobStatus.DRAFT
    assert duplicate.archived is False


def test_service_duplicate_missing_job_raises(db_session):
    from app.services.exceptions import NotFoundError
    from app.services.job_service import JobService

    service = JobService(db_session)
    with pytest.raises(NotFoundError):
        service.duplicate(999)


def test_service_archive_and_unarchive(db_session):
    from app.schemas.job import JobCreate
    from app.services.job_service import JobService

    service = JobService(db_session)
    job = service.create(JobCreate(title="Test job"))

    assert service.set_archived(job.id, True).archived is True
    assert service.set_archived(job.id, False).archived is False


# --- API -------------------------------------------------------------------


def test_api_create_and_get_job(api_client):
    response = api_client.post("/jobs", json={"title": "Delivery Driver", "location": "Giza"})
    assert response.status_code == 201
    created = response.json()
    assert created["title"] == "Delivery Driver"
    assert created["status"] == "Draft"
    assert created["archived"] is False

    response = api_client.get(f"/jobs/{created['id']}")
    assert response.status_code == 200
    assert response.json()["location"] == "Giza"


def test_api_get_missing_job_returns_404(api_client):
    assert api_client.get("/jobs/999999").status_code == 404


def test_api_create_rejects_bad_salary_range(api_client):
    response = api_client.post(
        "/jobs", json={"title": "Bad job", "salary_min": 30000, "salary_max": 10000}
    )
    assert response.status_code == 400
    assert "salary_min" in response.json()["detail"]


def test_api_list_search_and_filter(api_client):
    api_client.post("/jobs", json={"title": "Cairo Nurse", "location": "Cairo"})
    api_client.post("/jobs", json={"title": "Giza Teacher", "location": "Giza"})

    response = api_client.get("/jobs", params={"search": "Cairo"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Cairo Nurse"


def test_api_update_job(api_client):
    created = api_client.post("/jobs", json={"title": "Original title"}).json()
    response = api_client.patch(f"/jobs/{created['id']}", json={"title": "Updated title"})
    assert response.status_code == 200
    assert response.json()["title"] == "Updated title"


def test_api_update_missing_job_returns_404(api_client):
    response = api_client.patch("/jobs/999999", json={"title": "Doesn't matter"})
    assert response.status_code == 404


def test_api_duplicate_job(api_client):
    created = api_client.post("/jobs", json={"title": "Cashier", "company": "Store Co"}).json()
    response = api_client.post(f"/jobs/{created['id']}/duplicate")
    assert response.status_code == 201
    duplicate = response.json()
    assert duplicate["title"] == "Cashier (Copy)"
    assert duplicate["id"] != created["id"]


def test_api_close_and_archive_job(api_client):
    created = api_client.post("/jobs", json={"title": "Accountant"}).json()

    response = api_client.post(f"/jobs/{created['id']}/close")
    assert response.json()["status"] == "Closed"

    response = api_client.post(f"/jobs/{created['id']}/archive")
    assert response.json()["archived"] is True

    response = api_client.post(f"/jobs/{created['id']}/unarchive")
    assert response.json()["archived"] is False


def test_api_archived_jobs_excluded_from_list_by_default(api_client):
    created = api_client.post("/jobs", json={"title": "To be archived"}).json()
    api_client.post(f"/jobs/{created['id']}/archive")

    ids = [j["id"] for j in api_client.get("/jobs").json()["items"]]
    assert created["id"] not in ids

    ids = [j["id"] for j in api_client.get("/jobs", params={"include_archived": True}).json()["items"]]
    assert created["id"] in ids
