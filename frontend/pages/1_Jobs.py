"""Jobs page — create, edit, search/filter, duplicate, close, archive.

Streamlit auto-discovers this in the sidebar as "Jobs" (the "1_" prefix
just controls ordering). Talks to the backend only through
frontend/components/api_client.py — no direct database access from here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from app.config.settings import get_settings
from app.database.enums import JobStatus
from frontend.components.api_client import APIError, get, patch, post
from frontend.components.pagination import get_page, render_pagination_controls

settings = get_settings()
st.set_page_config(page_title=f"Jobs — {settings.app_name}", page_icon="📋", layout="wide")

PAGE_SIZE = 20
if "editing_job_id" not in st.session_state:
    st.session_state.editing_job_id = None

st.title("Jobs")


def _job_form(defaults: dict, submit_label: str, show_status: bool = False) -> dict | None:
    """Shared field layout for create + edit. Must be called inside a
    `with st.form(...):` block. Returns the collected values on submit,
    or None if not submitted (or submitted invalid)."""

    if show_status:
        status_options = [s.value for s in JobStatus]
        current = defaults.get("status", JobStatus.DRAFT.value)
        status = st.selectbox("Status", status_options, index=status_options.index(current))
    else:
        status = None

    col1, col2, col3 = st.columns(3)
    title = col1.text_input("Job title *", value=defaults.get("title", ""))
    company = col2.text_input("Company", value=defaults.get("company") or "")
    location = col3.text_input("Location", value=defaults.get("location") or "")

    col1, col2, col3 = st.columns(3)
    employment_type = col1.text_input(
        "Employment type", value=defaults.get("employment_type") or "", placeholder="Full-time"
    )
    experience = col2.text_input("Experience", value=defaults.get("experience") or "")
    education = col3.text_input("Education", value=defaults.get("education") or "")

    col1, col2, col3 = st.columns(3)
    salary_min = col1.number_input(
        "Salary min", value=int(defaults.get("salary_min") or 0), min_value=0, step=500
    )
    salary_max = col2.number_input(
        "Salary max", value=int(defaults.get("salary_max") or 0), min_value=0, step=500
    )
    salary_text = col3.text_input(
        "Salary (free text)", value=defaults.get("salary_text") or "", placeholder="Negotiable"
    )

    language_requirements = st.text_input(
        "Language requirements", value=defaults.get("language_requirements") or ""
    )
    requirements = st.text_area("Requirements", value=defaults.get("requirements") or "", height=100)
    responsibilities = st.text_area(
        "Responsibilities", value=defaults.get("responsibilities") or "", height=100
    )
    benefits = st.text_area("Benefits", value=defaults.get("benefits") or "", height=80)
    working_hours = st.text_input("Working hours", value=defaults.get("working_hours") or "")

    col1, col2 = st.columns(2)
    application_method = col1.text_input(
        "Application method", value=defaults.get("application_method") or ""
    )
    application_url = col2.text_input("Application URL", value=defaults.get("application_url") or "")

    col1, col2, col3 = st.columns(3)
    contact_phone = col1.text_input("Contact phone", value=defaults.get("contact_phone") or "")
    contact_whatsapp = col2.text_input("Contact WhatsApp", value=defaults.get("contact_whatsapp") or "")
    contact_email = col3.text_input("Contact email", value=defaults.get("contact_email") or "")

    description = st.text_area("Description", value=defaults.get("description") or "", height=120)

    submitted = st.form_submit_button(submit_label)
    if not submitted:
        return None
    if not title.strip():
        st.error("Job title is required.")
        return None

    result = {
        "title": title.strip(),
        "company": company or None,
        "location": location or None,
        "salary_min": int(salary_min) or None,
        "salary_max": int(salary_max) or None,
        "salary_text": salary_text or None,
        "employment_type": employment_type or None,
        "experience": experience or None,
        "education": education or None,
        "language_requirements": language_requirements or None,
        "requirements": requirements or None,
        "responsibilities": responsibilities or None,
        "benefits": benefits or None,
        "working_hours": working_hours or None,
        "application_method": application_method or None,
        "application_url": application_url or None,
        "contact_phone": contact_phone or None,
        "contact_whatsapp": contact_whatsapp or None,
        "contact_email": contact_email or None,
        "description": description or None,
    }
    if show_status:
        result["status"] = status
    return result


# --- Create or edit form ---
editing_id = st.session_state.editing_job_id

if editing_id is not None:
    try:
        existing = get(f"/jobs/{editing_id}")
    except APIError as exc:
        st.error(f"Couldn't load job {editing_id}: {exc}")
        existing = None

    if existing is not None:
        st.subheader(f"Edit job: {existing['title']}")
        with st.form("edit_job_form"):
            result = _job_form(existing, "Save changes", show_status=True)
        if result is not None:
            try:
                patch(f"/jobs/{editing_id}", json=result)
                st.session_state.editing_job_id = None
                st.success("Job updated.")
                st.rerun()
            except APIError as exc:
                st.error(f"Couldn't save changes: {exc}")
        if st.button("Cancel edit"):
            st.session_state.editing_job_id = None
            st.rerun()
else:
    with st.expander("Create new job"):
        with st.form("create_job_form"):
            result = _job_form({}, "Create job")
        if result is not None:
            try:
                created = post("/jobs", json=result)
                st.success(f"Created job: {created['title']}")
                st.rerun()
            except APIError as exc:
                st.error(f"Couldn't create job: {exc}")

st.divider()

# --- Search / filter ---
col1, col2, col3 = st.columns([2, 1, 1])
search = col1.text_input("Search title, company, or location")
status_filter = col2.selectbox("Status", ["All"] + [s.value for s in JobStatus])
include_archived = col3.checkbox("Include archived")

params: dict = {"skip": (get_page("jobs_page") - 1) * PAGE_SIZE, "limit": PAGE_SIZE}
if search:
    params["search"] = search
if status_filter != "All":
    params["status"] = status_filter
if include_archived:
    params["include_archived"] = True

try:
    result = get("/jobs", params=params)
except APIError as exc:
    st.error(f"Couldn't load jobs: {exc}")
    result = {"items": [], "total": 0}

jobs = result["items"]
total = result["total"]

if total == 0:
    if search or status_filter != "All":
        st.info("No jobs match your search/filters. Try broadening them.")
    else:
        st.info("No jobs yet — use the form above to create your first one.")
else:
    st.caption(f"{total} job{'s' if total != 1 else ''} found")

for job in jobs:
    archived_tag = " (archived)" if job["archived"] else ""
    with st.expander(f"{job['title']} — {job.get('company') or 'No company'} · {job['status']}{archived_tag}"):
        st.write(f"**Location:** {job.get('location') or '—'}")
        salary = job.get("salary_text") or (
            f"{job.get('salary_min') or '?'} – {job.get('salary_max') or '?'}"
            if job.get("salary_min") or job.get("salary_max")
            else "—"
        )
        st.write(f"**Salary:** {salary}")
        st.write(f"**Description:** {job.get('description') or '—'}")

        c1, c2, c3, c4 = st.columns(4)
        if c1.button("Edit", key=f"edit_{job['id']}"):
            st.session_state.editing_job_id = job["id"]
            st.rerun()

        if c2.button("Duplicate", key=f"dup_{job['id']}"):
            try:
                post(f"/jobs/{job['id']}/duplicate")
                st.success("Duplicated as a new Draft.")
                st.rerun()
            except APIError as exc:
                st.error(str(exc))

        if job["status"] != JobStatus.CLOSED.value:
            if c3.button("Close", key=f"close_{job['id']}"):
                try:
                    post(f"/jobs/{job['id']}/close")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))

        if not job["archived"]:
            if c4.button("Archive", key=f"archive_{job['id']}"):
                try:
                    post(f"/jobs/{job['id']}/archive")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))
        else:
            if c4.button("Unarchive", key=f"unarchive_{job['id']}"):
                try:
                    post(f"/jobs/{job['id']}/unarchive")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))

# --- Pagination ---
render_pagination_controls(total, PAGE_SIZE, "jobs_page")
