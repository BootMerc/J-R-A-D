"""Templates page — create, edit, search/filter, activate/deactivate,
delete, and a live preview of {{variable}} rendering against a real job.

Same pattern as the Jobs/Destinations pages: talks to the backend only
through frontend/components/api_client.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from app.config.settings import get_settings
from app.database.enums import Platform
from app.utils.template_rendering import KNOWN_VARIABLES
from frontend.components.api_client import APIError, delete, get, patch, post
from frontend.components.pagination import get_page, render_pagination_controls

settings = get_settings()
st.set_page_config(page_title=f"Templates — {settings.app_name}", page_icon="📝", layout="wide")

PAGE_SIZE = 20
if "editing_template_id" not in st.session_state:
    st.session_state.editing_template_id = None
if "confirm_delete_template_id" not in st.session_state:
    st.session_state.confirm_delete_template_id = None

st.title("Post Templates")


def _template_form(defaults: dict, submit_label: str) -> dict | None:
    """Must be called inside a `with st.form(...):` block."""

    col1, col2, col3 = st.columns(3)
    name = col1.text_input("Name *", value=defaults.get("name", ""))
    platform_options = [p.value for p in Platform]
    default_platform = defaults.get("platform", Platform.FACEBOOK.value)
    platform = col2.selectbox("Platform *", platform_options, index=platform_options.index(default_platform))
    language = col3.text_input(
        "Language", value=defaults.get("language") or "", placeholder="English / Arabic / Bilingual"
    )

    template_text = st.text_area(
        "Template text *",
        value=defaults.get("template_text", ""),
        height=220,
        help="Use {{variable}} placeholders — see the reference above.",
    )
    active = st.checkbox("Active", value=defaults.get("active", True))

    submitted = st.form_submit_button(submit_label)
    if not submitted:
        return None
    if not name.strip():
        st.error("Name is required.")
        return None
    if not template_text.strip():
        st.error("Template text is required.")
        return None

    return {
        "name": name.strip(),
        "platform": platform,
        "language": language or None,
        "template_text": template_text,
        "active": active,
    }


with st.expander("Available variables"):
    st.code(", ".join(f"{{{{{v}}}}}" for v in KNOWN_VARIABLES))
    st.caption(
        "These map to Job fields — e.g. {{job_title}} becomes the job's title, "
        "{{salary}} uses the job's salary text if set, otherwise a formatted "
        "min–max range. Anything else you type in {{double braces}} is left "
        "as-is in the output and flagged as an unrecognized variable — almost "
        "always a typo."
    )

# --- Create or edit form ---
editing_id = st.session_state.editing_template_id

if editing_id is not None:
    try:
        existing = get(f"/templates/{editing_id}")
    except APIError as exc:
        st.error(f"Couldn't load template {editing_id}: {exc}")
        existing = None

    if existing is not None:
        st.subheader(f"Edit template: {existing['name']}")
        with st.form("edit_template_form"):
            result = _template_form(existing, "Save changes")
        if result is not None:
            try:
                patch(f"/templates/{editing_id}", json=result)
                st.session_state.editing_template_id = None
                st.success("Template updated.")
                st.rerun()
            except APIError as exc:
                st.error(f"Couldn't save changes: {exc}")
        if st.button("Cancel edit"):
            st.session_state.editing_template_id = None
            st.rerun()
else:
    with st.expander("Create new template"):
        with st.form("create_template_form"):
            result = _template_form({}, "Create template")
        if result is not None:
            try:
                created = post("/templates", json=result)
                st.success(f"Created: {created['name']}")
                if created["unknown_variables"]:
                    st.warning(
                        "Unrecognized variables (left as-is when rendered): "
                        + ", ".join("{{" + v + "}}" for v in created["unknown_variables"])
                    )
                st.rerun()
            except APIError as exc:
                st.error(f"Couldn't create template: {exc}")

st.divider()

# --- Preview ---
with st.expander("Preview a template against a job"):
    try:
        preview_templates = get("/templates", params={"limit": 200})["items"]
    except APIError:
        preview_templates = []
    try:
        preview_jobs = get("/jobs", params={"limit": 200, "include_archived": True})["items"]
    except APIError:
        preview_jobs = []

    if not preview_templates or not preview_jobs:
        st.caption("Create at least one template and one job to preview.")
    else:
        template_options = {f"{t['name']} ({t['platform']})": t["id"] for t in preview_templates}
        job_options = {f"{j['title']} (#{j['id']})": j["id"] for j in preview_jobs}

        col1, col2 = st.columns(2)
        selected_template_label = col1.selectbox("Template", list(template_options.keys()))
        selected_job_label = col2.selectbox("Job", list(job_options.keys()))

        if st.button("Render preview"):
            try:
                preview = get(
                    f"/templates/{template_options[selected_template_label]}/preview",
                    params={"job_id": job_options[selected_job_label]},
                )
                st.text_area("Rendered output", value=preview["rendered_text"], height=250, disabled=True)
                if preview["unknown_variables"]:
                    st.warning(
                        "Unrecognized variables (left as-is above): "
                        + ", ".join("{{" + v + "}}" for v in preview["unknown_variables"])
                    )
            except APIError as exc:
                st.error(str(exc))

st.divider()

# --- Search / filter ---
col1, col2, col3 = st.columns(3)
search = col1.text_input("Search name or content")
platform_filter = col2.selectbox("Platform", ["All"] + [p.value for p in Platform])
active_filter = col3.selectbox("Status", ["All", "Active only", "Inactive only"])

params: dict = {"skip": (get_page("templates_page") - 1) * PAGE_SIZE, "limit": PAGE_SIZE}
if search:
    params["search"] = search
if platform_filter != "All":
    params["platform"] = platform_filter
if active_filter == "Active only":
    params["active"] = True
elif active_filter == "Inactive only":
    params["active"] = False

try:
    result = get("/templates", params=params)
except APIError as exc:
    st.error(f"Couldn't load templates: {exc}")
    result = {"items": [], "total": 0}

templates = result["items"]
total = result["total"]

if total == 0:
    if search or platform_filter != "All" or active_filter != "All":
        st.info("No templates match your search/filters. Try broadening them.")
    else:
        st.info(
            "No templates found. The 7 default templates are normally seeded "
            "automatically on first run — if this is a fresh install, check "
            "logs/app.log for a seeding error; otherwise, use the form above to add one."
        )
else:
    st.caption(f"{total} template{'s' if total != 1 else ''} found")

for template in templates:
    status_tag = "active" if template["active"] else "inactive"
    language_tag = f" · {template['language']}" if template.get("language") else ""
    with st.expander(f"{template['name']} — {template['platform']}{language_tag} · {status_tag}"):
        st.text(template["template_text"])

        if template["unknown_variables"]:
            st.warning(
                "Unrecognized variables: "
                + ", ".join("{{" + v + "}}" for v in template["unknown_variables"])
            )

        if st.session_state.confirm_delete_template_id == template["id"]:
            st.warning(f"Delete '{template['name']}'? This can't be undone.")
            cc1, cc2 = st.columns(2)
            if cc1.button("Yes, delete", key=f"confirm_del_tpl_{template['id']}"):
                try:
                    delete(f"/templates/{template['id']}")
                    st.session_state.confirm_delete_template_id = None
                    st.success("Deleted.")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))
            if cc2.button("Cancel", key=f"cancel_del_tpl_{template['id']}"):
                st.session_state.confirm_delete_template_id = None
                st.rerun()
        else:
            c1, c2, c3 = st.columns(3)
            if c1.button("Edit", key=f"edit_tpl_{template['id']}"):
                st.session_state.editing_template_id = template["id"]
                st.rerun()

            if template["active"]:
                if c2.button("Deactivate", key=f"deactivate_tpl_{template['id']}"):
                    try:
                        post(f"/templates/{template['id']}/deactivate")
                        st.rerun()
                    except APIError as exc:
                        st.error(str(exc))
            else:
                if c2.button("Activate", key=f"activate_tpl_{template['id']}"):
                    try:
                        post(f"/templates/{template['id']}/activate")
                        st.rerun()
                    except APIError as exc:
                        st.error(str(exc))

            if c3.button("Delete", key=f"del_tpl_{template['id']}"):
                st.session_state.confirm_delete_template_id = template["id"]
                st.rerun()

# --- Pagination ---
render_pagination_controls(total, PAGE_SIZE, "templates_page")
