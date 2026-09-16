# Calendar page — shows a week-at-a-glance view of scheduled_at across
# posts of any status.
#
# This page is read-only. Post actions like Start, Send, Schedule, and
# Mark Posted are handled on the Queue page, so we don't duplicate them here.
#
# The goal is simply to answer "what's happening when?"
#
# As with the other pages, all backend communication goes through
# frontend/components/api_client.py.

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from app.config.settings import get_settings
from frontend.components.api_client import APIError, get

settings = get_settings()
st.set_page_config(page_title=f"Calendar — {settings.app_name}", page_icon="🗓️", layout="wide")

st.title("Calendar")
st.caption(
    "What's scheduled, day by day. Read-only — use the Queue page (or the "
    "Facebook Assistant) to actually act on a post."
)

try:
    jobs_list = get("/jobs", params={"limit": 200, "include_archived": True})["items"]
except APIError:
    jobs_list = []
try:
    destinations_list = get("/destinations", params={"limit": 500})["items"]
except APIError:
    destinations_list = []
try:
    # The API caps limit at 200 (see app/api/posts.py) — plenty for a
    # single-user local tool's few-weeks-out calendar; a post beyond that
    # cap simply won't appear here yet.
    posts_list = get("/posts", params={"limit": 200})["items"]
except APIError:
    posts_list = []

job_titles_by_id = {j["id"]: j["title"] for j in jobs_list}
dest_labels_by_id = {d["id"]: f"{d['name']} ({d['platform']})" for d in destinations_list}

if "calendar_week_offset" not in st.session_state:
    st.session_state.calendar_week_offset = 0

nav_prev, nav_label, nav_next = st.columns([1, 3, 1])
if nav_prev.button("← Previous week"):
    st.session_state.calendar_week_offset -= 1
    st.rerun()
if nav_next.button("Next week →"):
    st.session_state.calendar_week_offset += 1
    st.rerun()

today = datetime.now().date()
week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=st.session_state.calendar_week_offset)
week_days = [week_start + timedelta(days=i) for i in range(7)]
nav_label.markdown(f"**{week_days[0].strftime('%b %d')} – {week_days[-1].strftime('%b %d, %Y')}**")

posts_by_date: dict = {day: [] for day in week_days}
for item in posts_list:
    if not item.get("scheduled_at"):
        continue
    try:
        post_date = datetime.fromisoformat(item["scheduled_at"]).date()
    except ValueError:
        continue
    if post_date in posts_by_date:
        posts_by_date[post_date].append(item)

STATUS_COLORS = {
    "Draft": "gray",
    "Queued": "blue",
    "Scheduled": "violet",
    "Processing": "orange",
    "Posted": "green",
    "Failed": "red",
    "Skipped": "gray",
    "Manual Action Required": "red",
}

columns = st.columns(7)
for day, col in zip(week_days, columns):
    with col:
        # %-d (no leading zero) is a glibc-only strftime extension —
        # doesn't exist on Windows' C runtime (which uses %#d instead).
        # %d works identically and portably everywhere; the leading zero
        # on single-digit days is a trivial cosmetic trade-off for that.
        label = day.strftime("%a %d") if day != today else f"**{day.strftime('%a %d')}** (today)"
        st.markdown(label)
        day_posts = sorted(posts_by_date[day], key=lambda p: p.get("scheduled_at") or "")
        if not day_posts:
            st.caption("—")
        for item in day_posts:
            job_label = job_titles_by_id.get(item["job_id"], f"Job #{item['job_id']}")
            dest_label = dest_labels_by_id.get(item["destination_id"], f"Destination #{item['destination_id']}")
            time_str = datetime.fromisoformat(item["scheduled_at"]).strftime("%H:%M")
            color = STATUS_COLORS.get(item["status"], "gray")
            st.markdown(f"`{time_str}` :{color}[{item['status']}]")
            st.caption(f"{job_label} → {dest_label}")

if not posts_list:
    st.info("No posts yet — create some from the Post Creator or Queue page.")
