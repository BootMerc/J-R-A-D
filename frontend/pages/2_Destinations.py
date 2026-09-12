"""Destinations page — create, edit, search/filter, tags, CSV import/
export, activate/deactivate, delete.

Same pattern as frontend/pages/1_Jobs.py: talks to the backend only through
frontend/components/api_client.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from app.config.settings import get_settings
from app.database.enums import Platform, PostingMethod
from frontend.components.api_client import APIError, delete, get, get_raw, patch, post, post_file
from frontend.components.pagination import get_page, render_pagination_controls

settings = get_settings()
st.set_page_config(page_title=f"Destinations — {settings.app_name}", page_icon="🎯", layout="wide")

PAGE_SIZE = 20
if "editing_destination_id" not in st.session_state:
    st.session_state.editing_destination_id = None
if "confirm_delete_id" not in st.session_state:
    st.session_state.confirm_delete_id = None

st.title("Destinations")


def _destination_form(defaults: dict, submit_label: str) -> dict | None:
    """Must be called inside a `with st.form(...):` block."""

    col1, col2 = st.columns(2)
    platform_options = [p.value for p in Platform]
    default_platform = defaults.get("platform", Platform.FACEBOOK.value)
    platform = col1.selectbox("Platform *", platform_options, index=platform_options.index(default_platform))
    name = col2.text_input("Name *", value=defaults.get("name", ""))

    col1, col2 = st.columns(2)
    url = col1.text_input("URL", value=defaults.get("url") or "")
    posting_method_options = [m.value for m in PostingMethod]
    default_method = defaults.get("posting_method", PostingMethod.BROWSER_ASSISTED.value)
    posting_method = col2.selectbox(
        "Posting method *",
        posting_method_options,
        index=posting_method_options.index(default_method),
        help="Telegram usually supports API (Bot API). Facebook groups don't have a "
        "posting API for third-party apps, so Browser-assisted is standard. TikTok "
        "is Manual unless you've been granted Content Posting API audit access.",
    )

    col1, col2, col3 = st.columns(3)
    category = col1.text_input("Category", value=defaults.get("category") or "", placeholder="Call Center")
    location = col2.text_input("Location", value=defaults.get("location") or "", placeholder="Cairo")
    language = col3.text_input("Language", value=defaults.get("language") or "", placeholder="English")

    audience = st.text_input("Audience", value=defaults.get("audience") or "")
    tags_default = ", ".join(defaults.get("tags", []))
    tags_input = st.text_input(
        "Tags (comma-separated)", value=tags_default, help="e.g. Cairo, Call Center, English Jobs"
    )

    col1, col2 = st.columns(2)
    min_interval = col1.number_input(
        "Minimum minutes between posts to this destination",
        value=int(defaults.get("min_posting_interval_minutes") or 0),
        min_value=0,
        step=5,
        help="Internal workflow safeguard, not a platform restriction bypass. 0 = no limit set.",
    )
    daily_limit = col2.number_input(
        "Daily posting limit",
        value=int(defaults.get("daily_posting_limit") or 0),
        min_value=0,
        step=1,
        help="0 = no limit set.",
    )

    notes = st.text_area("Notes", value=defaults.get("notes") or "", height=80)
    active = st.checkbox("Active", value=defaults.get("active", True))

    submitted = st.form_submit_button(submit_label)
    if not submitted:
        return None
    if not name.strip():
        st.error("Name is required.")
        return None

    return {
        "platform": platform,
        "name": name.strip(),
        "url": url or None,
        "posting_method": posting_method,
        "category": category or None,
        "location": location or None,
        "language": language or None,
        "audience": audience or None,
        "tags": [t.strip() for t in tags_input.split(",") if t.strip()],
        "min_posting_interval_minutes": int(min_interval) or None,
        "daily_posting_limit": int(daily_limit) or None,
        "notes": notes or None,
        "active": active,
    }


# --- Create or edit form ---
editing_id = st.session_state.editing_destination_id

if editing_id is not None:
    try:
        existing = get(f"/destinations/{editing_id}")
    except APIError as exc:
        st.error(f"Couldn't load destination {editing_id}: {exc}")
        existing = None

    if existing is not None:
        st.subheader(f"Edit destination: {existing['name']}")
        with st.form("edit_destination_form"):
            result = _destination_form(existing, "Save changes")
        if result is not None:
            try:
                patch(f"/destinations/{editing_id}", json=result)
                st.session_state.editing_destination_id = None
                st.success("Destination updated.")
                st.rerun()
            except APIError as exc:
                st.error(f"Couldn't save changes: {exc}")
        if st.button("Cancel edit"):
            st.session_state.editing_destination_id = None
            st.rerun()
else:
    with st.expander("Add new destination"):
        with st.form("create_destination_form"):
            result = _destination_form({}, "Add destination")
        if result is not None:
            try:
                created = post("/destinations", json=result)
                st.success(f"Added: {created['name']}")
                st.rerun()
            except APIError as exc:
                st.error(f"Couldn't add destination: {exc}")

st.divider()

# --- CSV import / export ---
with st.expander("Import / export CSV"):
    st.markdown(
        "Columns: `platform, name, url, category, location, audience, language, "
        "posting_method, active, notes, tags`. Separate multiple tags with `|` "
        "(e.g. `Cairo|Call Center|English Jobs`). `posting_method` and `active` "
        "are optional — sensible defaults are applied if left blank."
    )
    uploaded = st.file_uploader("Import destinations from CSV", type="csv")
    if uploaded is not None:
        if st.button("Run import"):
            try:
                result = post_file("/destinations/import-csv", uploaded.name, uploaded.getvalue())
                st.success(f"Imported {result['created']} destination(s).")
                if result["errors"]:
                    st.warning("Some rows had problems:")
                    for err in result["errors"]:
                        st.write(f"- {err}")
                st.rerun()
            except APIError as exc:
                st.error(f"Import failed: {exc}")

    try:
        export_bytes = get_raw("/destinations/export-csv")
        st.download_button(
            "Export all destinations to CSV",
            data=export_bytes,
            file_name="destinations.csv",
            mime="text/csv",
        )
    except APIError as exc:
        st.caption(f"Export unavailable: {exc}")

st.divider()

# --- Search / filter ---
try:
    filter_options = get("/destinations/filter-options")
except APIError:
    filter_options = {"categories": [], "locations": [], "languages": []}

col1, col2, col3 = st.columns(3)
search = col1.text_input("Search name, URL, or notes")
platform_filter = col2.selectbox("Platform", ["All"] + [p.value for p in Platform])
active_filter = col3.selectbox("Status", ["All", "Active only", "Inactive only"])

col1, col2, col3 = st.columns(3)
category_filter = col1.selectbox("Category", ["All"] + filter_options["categories"])
location_filter = col2.selectbox("Location", ["All"] + filter_options["locations"])
language_filter = col3.selectbox("Language", ["All"] + filter_options["languages"])

tag_filter = st.text_input("Filter by tag (exact match)")

params: dict = {"skip": (get_page("destinations_page") - 1) * PAGE_SIZE, "limit": PAGE_SIZE}
if search:
    params["search"] = search
if platform_filter != "All":
    params["platform"] = platform_filter
if category_filter != "All":
    params["category"] = category_filter
if location_filter != "All":
    params["location"] = location_filter
if language_filter != "All":
    params["language"] = language_filter
if tag_filter:
    params["tag"] = tag_filter
if active_filter == "Active only":
    params["active"] = True
elif active_filter == "Inactive only":
    params["active"] = False

try:
    result = get("/destinations", params=params)
except APIError as exc:
    st.error(f"Couldn't load destinations: {exc}")
    result = {"items": [], "total": 0}

destinations = result["items"]
total = result["total"]

if total == 0:
    any_filter_active = (
        search
        or platform_filter != "All"
        or category_filter != "All"
        or location_filter != "All"
        or language_filter != "All"
        or tag_filter
        or active_filter != "All"
    )
    if any_filter_active:
        st.info("No destinations match your search/filters. Try broadening them.")
    else:
        st.info("No destinations yet — use the form above to add your first one, or import a CSV.")
else:
    st.caption(f"{total} destination{'s' if total != 1 else ''} found")

for destination in destinations:
    status_tag = "active" if destination["active"] else "inactive"
    tags_display = ", ".join(destination["tags"]) if destination["tags"] else "no tags"
    with st.expander(f"{destination['name']} — {destination['platform']} · {status_tag}"):
        st.write(f"**URL:** {destination.get('url') or '—'}")
        st.write(f"**Category:** {destination.get('category') or '—'} · **Location:** {destination.get('location') or '—'}")
        st.write(f"**Posting method:** {destination['posting_method']}")
        st.write(f"**Tags:** {tags_display}")
        if destination.get("notes"):
            st.write(f"**Notes:** {destination['notes']}")

        if st.session_state.confirm_delete_id == destination["id"]:
            st.warning(f"Delete '{destination['name']}'? This can't be undone.")
            cc1, cc2 = st.columns(2)
            if cc1.button("Yes, delete", key=f"confirm_del_{destination['id']}"):
                try:
                    delete(f"/destinations/{destination['id']}")
                    st.session_state.confirm_delete_id = None
                    st.success("Deleted.")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))
            if cc2.button("Cancel", key=f"cancel_del_{destination['id']}"):
                st.session_state.confirm_delete_id = None
                st.rerun()
        else:
            c1, c2, c3 = st.columns(3)
            if c1.button("Edit", key=f"edit_{destination['id']}"):
                st.session_state.editing_destination_id = destination["id"]
                st.rerun()

            if destination["active"]:
                if c2.button("Deactivate", key=f"deactivate_{destination['id']}"):
                    try:
                        post(f"/destinations/{destination['id']}/deactivate")
                        st.rerun()
                    except APIError as exc:
                        st.error(str(exc))
            else:
                if c2.button("Activate", key=f"activate_{destination['id']}"):
                    try:
                        post(f"/destinations/{destination['id']}/activate")
                        st.rerun()
                    except APIError as exc:
                        st.error(str(exc))

            if c3.button("Delete", key=f"del_{destination['id']}"):
                st.session_state.confirm_delete_id = destination["id"]
                st.rerun()

# --- Pagination ---
render_pagination_controls(total, PAGE_SIZE, "destinations_page")
