# Database engine, session factory, and declarative Base.
#
# The engine is created lazily with a cached get_engine() instead of at
# import time. This makes it easy to swap the database in tests by changing
# DATABASE_URL, clearing the settings/engine caches, and creating a fresh
# engine for the isolated test database.
#
# See tests/test_foundation.py for the testing pattern.

from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    url = settings.database_url

    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        db_path = url.split("sqlite:///")[-1]
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    return create_engine(url, connect_args=connect_args)


def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def get_db():
    """FastAPI dependency: yields a session, always closes it afterwards."""
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Safe to call every startup — no-op if they exist."""
    from app.database import models  # noqa: F401  (registers models on Base)

    Base.metadata.create_all(bind=get_engine())
