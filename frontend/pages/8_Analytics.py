# Analytics page — handles manual metrics logging and reporting.
#
# There is no automated metrics collection in the project. Every metric
# shown here is entered manually by the user.
#
# As with the other pages, all backend communication goes through
# frontend/components/api_client.py.

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from app.config.settings import get_settings
from frontend.components.api_client import APIError, get, post

settings = get_settings()
st.set_page_config(page_title=f"Analytics — {settings.app_name}", page_icon="📊", layout="wide")

st.title("Analytics")
st.caption(
    "Every number here is logged by hand — none of Facebook, Telegram, or TikTok's real "
    "view/click data is fetched automatically. Log today's numbers below, then see them "
    "rolled up by destination and by template underneath."
)

try:
    jobs_list = get("/jobs", params={"limit": 200, "include_archived": True})["items"]
except APIError:
    jobs_list = []
try:
    destinations_list = get("/destinations", params={"limit": 500})["items"]
except APIError:
    destinations_list = []

job_options = {f"{j['title']} (#{j['id']})": j["id"] for j in jobs_list}
dest_options = {f"{d['name']} ({d['platform']})": d["id"] for d in destinations_list}

st.subheader("Log metrics")
if not job_options or not dest_options:
    st.info("Create a job and a destination first (Jobs / Destinations pages).")
else:
    with st.form("log_metric_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        job_label = col1.selectbox("Job", list(job_options.keys()))
        dest_label = col2.selectbox("Destination", list(dest_options.keys()))
        metric_date = col3.date_input("Date", value=date.today())

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        views = c1.number_input("Views", min_value=0, value=0, step=1)
        clicks = c2.number_input("Clicks", min_value=0, value=0, step=1)
        messages = c3.number_input("Messages", min_value=0, value=0, step=1)
        applications = c4.number_input("Applications", min_value=0, value=0, step=1)
        interviews = c5.number_input("Interviews", min_value=0, value=0, step=1)
        hires = c6.number_input("Hires", min_value=0, value=0, step=1)

        notes = st.text_input("Notes (optional)")
        submitted = st.form_submit_button("Save")

        if submitted:
            try:
                post(
                    "/metrics",
                    json={
                        "job_id": job_options[job_label],
                        "destination_id": dest_options[dest_label],
                        "date": metric_date.isoformat(),
                        "views": views,
                        "clicks": clicks,
                        "messages": messages,
                        "applications": applications,
                        "interviews": interviews,
                        "hires": hires,
                        "notes": notes or None,
                    },
                )
                st.success(f"Saved {metric_date.isoformat()}'s numbers for that job + destination.")
            except APIError as exc:
                st.error(str(exc))

st.divider()

filter_col1, filter_col2 = st.columns(2)
filter_job_label = filter_col1.selectbox("Filter by job", ["All jobs"] + list(job_options.keys()))
filter_days = filter_col2.selectbox(
    "Date range", ["Last 7 days", "Last 30 days", "Last 90 days", "All time"], index=1
)
filter_job_id = job_options.get(filter_job_label)
date_from = None
if filter_days != "All time":
    days = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}[filter_days]
    date_from = (date.today() - timedelta(days=days)).isoformat()

params = {k: v for k, v in {"job_id": filter_job_id, "date_from": date_from}.items() if v is not None}

st.subheader("Funnel")
try:
    funnel = get("/analytics/funnel", params=params)
    stages = [
        ("Views", funnel["views"]),
        ("Clicks", funnel["clicks"]),
        ("Messages", funnel["messages"]),
        ("Applications", funnel["applications"]),
        ("Interviews", funnel["interviews"]),
        ("Hires", funnel["hires"]),
    ]
    cols = st.columns(6)
    previous_label, previous_count = None, None
    for col, (label, count) in zip(cols, stages):
        conversion = f"{count / previous_count:.0%} of {previous_label.lower()}" if previous_count else None
        col.metric(label, count, delta=conversion, delta_color="off")
        if count:
            previous_label, previous_count = label, count
except APIError as exc:
    st.error(f"Couldn't load the funnel: {exc}")

st.subheader("Performance by destination")
try:
    by_destination = get("/analytics/by-destination", params=params)
    if by_destination:
        st.dataframe(by_destination, hide_index=True, use_container_width=True)
    else:
        st.caption("No metrics logged yet for this filter.")
except APIError as exc:
    st.error(f"Couldn't load destination performance: {exc}")

st.subheader("Performance by template")
st.caption("Only counts metrics logged against a specific post — see the note on the form above.")
try:
    by_template = get("/analytics/by-template", params=params)
    if by_template:
        st.dataframe(by_template, hide_index=True, use_container_width=True)
    else:
        st.caption("No metrics logged against a specific post yet for this filter.")
except APIError as exc:
    st.error(f"Couldn't load template performance: {exc}")
