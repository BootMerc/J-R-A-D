"""FastAPI backend entrypoint.

Run with: uvicorn app.main:app --reload --port 8000
(run.bat does this for you)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import destinations, health, jobs, metrics, posts, templates
from app.config.logging import setup_logging
from app.config.settings import get_settings
from app.database.database import get_session_factory, init_db
from app.database.seed_data import seed_default_templates
from app.scheduler import start_scheduler
from app.services.exceptions import NotFoundError

setup_logging()
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (env=%s)", settings.app_name, settings.app_env)
    init_db()
    logger.info("Database ready")

    session_factory = get_session_factory()
    with session_factory() as db:
        seed_default_templates(db)
    logger.info("Default templates seeded (no-op if any templates already exist)")

    scheduler = start_scheduler()

    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(health.router)
app.include_router(jobs.router)
app.include_router(destinations.router)
app.include_router(templates.router)
app.include_router(posts.router)
app.include_router(metrics.router)


# Centralized so individual routers can raise domain exceptions directly
# instead of wrapping every endpoint in try/except.
@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/")
def root() -> dict:
    return {"message": settings.app_name, "status": "running", "docs": "/docs"}
