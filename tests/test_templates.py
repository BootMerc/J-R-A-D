"""Phase 4 tests: template_rendering utility, TemplateRepository,
TemplateService (incl. preview against a real Job), and the Templates API.
"""

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
    """A TestClient bound to its own isolated SQLite file. Note this DOES
    trigger seed_default_templates via the app's lifespan (same as any
    real startup), so tests that check `total` counts create their own
    templates and assert on top of, not instead of, the 4 seeded ones."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test_templates.db")
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


# --- Rendering utility (pure functions, no DB) ----------------------------


def test_render_template_basic_substitution():
    from app.utils.template_rendering import render_template

    result = render_template("Hiring {{job_title}} at {{company}}!", {"job_title": "Nurse", "company": "Acme"})
    assert result == "Hiring Nurse at Acme!"


def test_render_template_tolerates_whitespace_inside_braces():
    from app.utils.template_rendering import render_template

    result = render_template("{{ job_title }}", {"job_title": "Nurse"})
    assert result == "Nurse"


def test_render_template_leaves_unknown_placeholder_visible():
    from app.utils.template_rendering import render_template

    result = render_template("{{job_title}} needs {{sallary}}", {"job_title": "Nurse"})
    assert result == "Nurse needs {{sallary}}"  # typo left visible, not blanked


def test_extract_and_unknown_variables():
    from app.utils.template_rendering import extract_variables, unknown_variables

    text = "{{job_title}} {{job_title}} {{sallary}} {{location}}"
    assert extract_variables(text) == ["job_title", "location", "sallary"]
    assert unknown_variables(text) == ["sallary"]


def test_format_salary_priority_order():
    from app.utils.template_rendering import format_salary

    assert format_salary(10000, 15000, "Negotiable") == "Negotiable"  # text wins
    assert format_salary(10000, 15000, None) == "10,000 - 15,000"
    assert format_salary(10000, None, None) == "10,000+"
    assert format_salary(None, 15000, None) == "Up to 15,000"
    assert format_salary(None, None, None) == ""


def test_job_to_variables_maps_all_fields(db_session):
    from app.database.enums import JobStatus
    from app.database.models import Job
    from app.utils.template_rendering import job_to_variables

    job = Job(title="Nurse", company="Acme", location="Cairo", salary_text="Negotiable", status=JobStatus.DRAFT)
    db_session.add(job)
    db_session.commit()

    variables = job_to_variables(job)
    assert variables["job_title"] == "Nurse"
    assert variables["company"] == "Acme"
    assert variables["salary"] == "Negotiable"
    assert variables["benefits"] == ""  # unset field -> empty string, not "None"


# --- Repository ------------------------------------------------------------


def test_repository_create_and_filter_by_platform(db_session):
    from app.database.enums import Platform
    from app.database.repositories.template_repository import TemplateRepository

    repo = TemplateRepository(db_session)
    repo.create(name="FB template", platform=Platform.FACEBOOK, template_text="{{job_title}}")
    repo.create(name="TG template", platform=Platform.TELEGRAM, template_text="{{job_title}}")

    assert [t.name for t in repo.list(platform=Platform.TELEGRAM)] == ["TG template"]


def test_repository_delete(db_session):
    from app.database.enums import Platform
    from app.database.repositories.template_repository import TemplateRepository

    repo = TemplateRepository(db_session)
    template = repo.create(name="Temp", platform=Platform.FACEBOOK, template_text="x")

    assert repo.delete(template.id) is True
    assert repo.get(template.id) is None
    assert repo.delete(999) is False


# --- Service (incl. preview) ------------------------------------------------


def test_service_preview_renders_against_real_job(db_session):
    from app.database.enums import JobStatus, Platform
    from app.database.models import Job
    from app.services.template_service import TemplateService

    job = Job(title="Nurse", company="Acme", location="Cairo", status=JobStatus.DRAFT)
    db_session.add(job)
    db_session.commit()

    service = TemplateService(db_session)
    template = service.repo.create(
        name="FB", platform=Platform.FACEBOOK, template_text="Hiring {{job_title}} at {{company}} in {{location}}!"
    )

    result = service.preview(template.id, job.id)
    assert result["rendered_text"] == "Hiring Nurse at Acme in Cairo!"
    assert result["unknown_variables"] == []


def test_service_preview_missing_template_raises(db_session):
    from app.database.enums import JobStatus
    from app.database.models import Job
    from app.services.exceptions import NotFoundError
    from app.services.template_service import TemplateService

    job = Job(title="Nurse", status=JobStatus.DRAFT)
    db_session.add(job)
    db_session.commit()

    service = TemplateService(db_session)
    with pytest.raises(NotFoundError):
        service.preview(999, job.id)


def test_service_preview_missing_job_raises(db_session):
    from app.database.enums import Platform
    from app.services.exceptions import NotFoundError
    from app.services.template_service import TemplateService

    service = TemplateService(db_session)
    template = service.repo.create(name="FB", platform=Platform.FACEBOOK, template_text="{{job_title}}")

    with pytest.raises(NotFoundError):
        service.preview(template.id, 999)


def test_service_activate_and_deactivate(db_session):
    from app.database.enums import Platform
    from app.services.template_service import TemplateService

    service = TemplateService(db_session)
    template = service.repo.create(name="FB", platform=Platform.FACEBOOK, template_text="x")

    assert service.set_active(template.id, False).active is False
    assert service.set_active(template.id, True).active is True


# --- Seed data ---------------------------------------------------------


def test_seed_default_templates_is_idempotent(db_session):
    from app.database.models import PostTemplate
    from app.database.seed_data import seed_default_templates

    seed_default_templates(db_session)
    first_count = db_session.query(PostTemplate).count()
    assert first_count == 7  # FB Professional, FB Arabic, FB Urgent, FB Fresh Grads,
    # FB Bilingual, Telegram English, TikTok English — see seed_data.py

    seed_default_templates(db_session)  # calling again must not duplicate
    assert db_session.query(PostTemplate).count() == first_count


def test_seed_default_templates_skips_if_any_template_exists(db_session):
    from app.database.enums import Platform
    from app.database.models import PostTemplate
    from app.database.seed_data import seed_default_templates

    db_session.add(PostTemplate(name="Custom", platform=Platform.FACEBOOK, template_text="x"))
    db_session.commit()

    seed_default_templates(db_session)
    assert db_session.query(PostTemplate).count() == 1  # not topped up to 7+1


# --- API ---------------------------------------------------------------


def test_api_seeds_default_templates_on_startup(api_client):
    response = api_client.get("/templates", params={"limit": 200})
    body = response.json()
    assert body["total"] == 7
    platforms = {item["platform"] for item in body["items"]}
    assert platforms == {"Facebook", "Telegram", "TikTok"}


def test_api_create_flags_unknown_variables(api_client):
    response = api_client.post(
        "/templates",
        json={"name": "Typo template", "platform": "Facebook", "template_text": "{{job_title}} — {{sallary}}"},
    )
    assert response.status_code == 201
    assert response.json()["unknown_variables"] == ["sallary"]


def test_api_get_missing_template_returns_404(api_client):
    assert api_client.get("/templates/999999").status_code == 404


def test_api_update_template_text(api_client):
    created = api_client.post(
        "/templates", json={"name": "T", "platform": "Facebook", "template_text": "old"}
    ).json()
    response = api_client.patch(f"/templates/{created['id']}", json={"template_text": "new"})
    assert response.status_code == 200
    assert response.json()["template_text"] == "new"


def test_api_delete(api_client):
    created = api_client.post(
        "/templates", json={"name": "Temp", "platform": "Facebook", "template_text": "x"}
    ).json()

    assert api_client.delete(f"/templates/{created['id']}").status_code == 204
    assert api_client.get(f"/templates/{created['id']}").status_code == 404


def test_api_activate_deactivate(api_client):
    created = api_client.post(
        "/templates", json={"name": "T", "platform": "Facebook", "template_text": "x", "active": True}
    ).json()

    assert api_client.post(f"/templates/{created['id']}/deactivate").json()["active"] is False
    assert api_client.post(f"/templates/{created['id']}/activate").json()["active"] is True


def test_api_preview_end_to_end(api_client):
    job = api_client.post(
        "/jobs", json={"title": "Cashier", "company": "Store Co", "location": "Giza"}
    ).json()
    template = api_client.post(
        "/templates",
        json={
            "name": "FB test",
            "platform": "Facebook",
            "template_text": "Hiring {{job_title}} at {{company}} — {{location}}",
        },
    ).json()

    response = api_client.get(f"/templates/{template['id']}/preview", params={"job_id": job["id"]})
    assert response.status_code == 200
    body = response.json()
    assert body["rendered_text"] == "Hiring Cashier at Store Co — Giza"
    assert body["unknown_variables"] == []


def test_api_preview_missing_job_returns_404(api_client):
    template = api_client.post(
        "/templates", json={"name": "T", "platform": "Facebook", "template_text": "{{job_title}}"}
    ).json()

    response = api_client.get(f"/templates/{template['id']}/preview", params={"job_id": 999999})
    assert response.status_code == 404


def test_api_platform_filter(api_client):
    response = api_client.get("/templates", params={"platform": "TikTok"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["platform"] == "TikTok"
