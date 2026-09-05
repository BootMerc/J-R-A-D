"""Streamlit dashboard — landing page.

Run with: streamlit run frontend/dashboard.py
(run.bat does this for you)

Shows quick counts and API connectivity. Actual feature pages (Jobs,
Destinations, Templates, ...) live in frontend/pages/ — see
PROJECT_STATUS.md for what's built and what's still ahead.
"""

import sys
from pathlib import Path

# Let `python -m streamlit run frontend/dashboard.py` (or run.bat) resolve
# `app.*` imports regardless of the working directory Streamlit was launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import streamlit as st

from app.config.settings import get_settings
from app.database.database import get_session_factory, init_db
from app.database.models import Destination, Job
from app.database.seed_data import seed_default_templates

settings = get_settings()

st.set_page_config(page_title=settings.app_name, page_icon="📋", layout="wide")

init_db()  # safe no-op if tables already exist

SessionLocal = get_session_factory()
with SessionLocal() as _seed_db:
    seed_default_templates(_seed_db)  # no-op if any template already exists


def check_api() -> bool:
    try:
        response = httpx.get(
            f"http://{settings.api_host}:{settings.api_port}/health", timeout=2.0
        )
        return response.status_code == 200
    except httpx.HTTPError:
        return False


st.title(f"📋 {settings.app_name}")
st.caption("Phases 1–4 complete")

with SessionLocal() as db:
    job_count = db.query(Job).count()
    destination_count = db.query(Destination).count()

api_ok = check_api()

col1, col2, col3 = st.columns(3)
col1.metric("Jobs in database", job_count)
col2.metric("Destinations in database", destination_count)
col3.metric("API status", "Online" if api_ok else "Offline")

if not api_ok:
    st.warning(
        f"The FastAPI backend isn't reachable at "
        f"http://{settings.api_host}:{settings.api_port}. "
        "Start it with `uvicorn app.main:app --reload` — run.bat does this automatically."
    )

st.divider()
st.subheader("What's next")
st.markdown(
    """
Jobs, Destinations, and Post Templates (with a live `{{variable}}` preview
against any job) are built — use the sidebar. Post Creator, Queue, the
Facebook assistant, Telegram, TikTok, Scheduler, Analytics, and Backup are
still ahead. See `PROJECT_STATUS.md` for the full roadmap and exactly
what's done.
"""
)
