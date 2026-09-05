"""Central application configuration.

All configuration is read from environment variables (optionally via a local
.env file). Nothing here is ever hard-coded to a secret value — see
.env.example for the full list of supported variables.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = three levels up from this file (app/config/settings.py -> app -> root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    app_name: str = "Recruitment Automation Dashboard"
    app_env: str = "development"
    debug: bool = True

    # Database — as_posix() keeps the URL correct on both Windows and Linux
    # (see PROJECT_STATUS.md "Important implementation details" for why).
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'recruitment.db').as_posix()}"

    # Logging
    log_level: str = "INFO"
    log_file: str = str(BASE_DIR / "logs" / "app.log")

    # Local API server (FastAPI)
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Local UI server (Streamlit)
    streamlit_port: int = 8501

    # --- Added in later phases; optional, app runs fine without them ---

    # Phase 8 — Telegram Bot API
    telegram_bot_token: str | None = None

    # Phase 4 / 9 — optional AI-assisted features
    ai_api_key: str | None = None
    ai_provider: str | None = None

    # Phase 9 — TikTok Content Posting API
    tiktok_client_key: str | None = None
    tiktok_client_secret: str | None = None

    # Phase 9 — generated recruitment visuals (TikTok) live here
    media_dir: str = str(BASE_DIR / "media")

    # Phase 10 — Scheduler. Disabled by every test fixture that spins up a
    # TestClient (see tests/*.py's api_client fixtures) — a real
    # BackgroundScheduler firing mid-test-run against a test database
    # would be exactly the kind of flaky, hard-to-debug interference this
    # setting exists to prevent. Defaults to on for real usage, since the
    # whole point of this phase is that it works unattended out of the box.
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance. Tests can call get_settings.cache_clear()
    after monkeypatching environment variables to pick up new values."""
    return Settings()
