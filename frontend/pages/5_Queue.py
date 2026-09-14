# Queue page — handles batch queue creation, promoting Draft posts,
# progress tracking, and queue management (Start/Pause/Resume/Skip/Retry/Delete).
#
# Like the other pages, all backend communication goes through
# frontend/components/api_client.py.
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from app.config.settings import get_settings
from app.database.enums import PostStatus
from frontend.components.api_client import APIError, get, post
from frontend.components.pagination import get_page, render_pagination_controls

settings = get_settings()
st.set_page_config(page_title=f"Queue — {settings.app_name}", page_icon="📬", layout="wide")

PAGE_SIZE = 20

st.title("Queue")

try:
    jobs_list = get("/jobs", params={"limit": 200, "include_archived": True})["items"]
except APIError:
    jobs_list = []
try:
    destinations_list = get("/destinations", params={"limit": 200, "active": True})["items"]
except APIError:
    destinations_list = []
try:
    # Inclusive of inactive destinations (unlike destinations_list above,
    # which stays active-only since you shouldn't queue new posts against
    # an inactive one) — Phase 8 needs the real platform even for a post
    # queued against a destination that's since been deactivated, so it
    # still shows "Send" instead of silently falling back to "Start".
    all_destinations_list = get("/destinations", params={"limit": 500})["items"]
except APIError:
    all_destinations_list = []

job_options = {f"{j['title']} (#{j['id']})": j["id"] for j in jobs_list}
dest_options = {f"{d['name']} ({d['platform']})": d["id"] for d in destinations_list}
dest_urls_by_id = {d["id"]: d.get("url") for d in destinations_list}
dest_platform_by_id = {d["id"]: d["platform"] for d in all_destinations_list}

if not jobs_list or not destinations_list:
    st.info("Create at least one job and one active destination before creating a queue.")

# --- Batch queue creation ---
st.subheader("Create a queue")
st.caption(
    "Pick a job and destinations across any platforms — each gets its own staggered "
    "send time. Template auto-selects per destination's platform unless you force one "
    "(any destination on a different platform than a forced template is skipped, with "
    "a clear reason, not silently mis-rendered)."
)

if jobs_list and destinations_list:
    q_job_label = st.selectbox("Job", list(job_options.keys()), key="queue_job")
    q_dest_labels = st.multiselect("Destinations", list(dest_options.keys()), key="queue_dests")

    template_mode = st.radio(
        "Template", ["Auto-select per platform", "Use one specific template"], key="queue_template_mode"
    )
    forced_template_id = None
    if template_mode == "Use one specific template":
        try:
            active_templates = get("/templates", params={"limit": 200, "active": True})["items"]
        except APIError:
            active_templates = []
        if active_templates:
            template_labels = {f"{t['name']} ({t['platform']})": t["id"] for t in active_templates}
            selected_label = st.selectbox("Template", list(template_labels.keys()), key="queue_template_pick")
            forced_template_id = template_labels[selected_label]
        else:
            st.caption("No active templates exist yet.")

    col1, col2 = st.columns(2)
    start_now = col1.checkbox("Start now", value=True, key="queue_start_now")
    delay_minutes = col2.number_input(
        "Delay between posts (minutes)", min_value=0, value=5, step=1, key="queue_delay"
    )

    start_at = None
    if not start_now:
        col1, col2 = st.columns(2)
        start_date = col1.date_input("Start date", key="queue_start_date")
        start_time = col2.time_input("Start time", key="queue_start_time")
        start_at = datetime.combine(start_date, start_time)

    if st.button("Create queue", disabled=not q_dest_labels):
        payload = {
            "job_id": job_options[q_job_label],
            "destination_ids": [dest_options[label] for label in q_dest_labels],
            "delay_minutes": int(delay_minutes),
        }
        if forced_template_id is not None:
            payload["template_id"] = forced_template_id
        if start_at is not None:
            payload["start_at"] = start_at.isoformat()

        try:
            result = post("/posts/create-queue", json=payload)
            st.success(f"Queued {len(result['created'])} post(s).")
            if result["warnings"]:
                st.warning("Some destinations have workflow flags (still queued):")
                for w in result["warnings"]:
                    st.write(f"- {w}")
            if result["errors"]:
                st.warning("Some destinations were skipped entirely:")
                for e in result["errors"]:
                    st.write(f"- {e}")
            st.rerun()
        except APIError as exc:
            st.error(str(exc))

st.divider()

# --- Promote existing drafts ---
st.subheader("Queue an existing draft")
try:
    draft_posts = get("/posts", params={"status": "Draft", "limit": 200})["items"]
except APIError:
    draft_posts = []

if not draft_posts:
    st.caption("No Draft posts waiting — generate some on the Post Creator page first.")
else:
    job_titles_by_id = {j["id"]: j["title"] for j in jobs_list}
    dest_labels_by_id = {d["id"]: f"{d['name']} ({d['platform']})" for d in destinations_list}

    # --- Bulk action: queue every draft above in one click, staggered the
    # same way "Create a queue" staggers a fresh batch — so bulk-promoting
    # 50 drafts doesn't schedule all 50 for the exact same instant, which
    # would be poor practice for the same spam-protection reasons
    # create_queue() already cares about (see PROJECT_STATUS.md section 19).
    st.caption(f"{len(draft_posts)} draft{'s' if len(draft_posts) != 1 else ''} waiting")
    bulk_col1, bulk_col2 = st.columns(2)
    bulk_start_now = bulk_col1.checkbox("Start now", value=True, key="bulk_queue_start_now")
    bulk_delay_minutes = bulk_col2.number_input(
        "Delay between each (minutes)", min_value=0, value=5, step=1, key="bulk_queue_delay"
    )
    bulk_start_at = None
    if not bulk_start_now:
        bc1, bc2 = st.columns(2)
        bulk_start_date = bc1.date_input("Start date", key="bulk_queue_start_date")
        bulk_start_time = bc2.time_input("Start time", key="bulk_queue_start_time")
        bulk_start_at = datetime.combine(bulk_start_date, bulk_start_time)

    if st.button(f"Queue all {len(draft_posts)} drafts", type="primary"):
        base_time = bulk_start_at or datetime.now()
        succeeded, failed = 0, []
        for index, draft in enumerate(draft_posts):
            scheduled_at = base_time + timedelta(minutes=index * bulk_delay_minutes)
            try:
                post(f"/posts/{draft['id']}/queue", json={"scheduled_at": scheduled_at.isoformat()})
                succeeded += 1
            except APIError as exc:
                # Never let one bad draft stop the rest — same "never
                # silently fail the whole batch" rule create_queue() and
                # CSV import already follow elsewhere in this project.
                failed.append(f"Draft #{draft['id']}: {exc}")
        if succeeded:
            st.success(f"Queued {succeeded} post(s).")
        if failed:
            st.warning("Some drafts couldn't be queued:")
            for message in failed:
                st.write(f"- {message}")
        st.rerun()

    st.caption("Or queue just one:")
    for draft in draft_posts:
        job_label = job_titles_by_id.get(draft["job_id"], f"Job #{draft['job_id']}")
        dest_label = dest_labels_by_id.get(draft["destination_id"], f"Destination #{draft['destination_id']}")
        col1, col2 = st.columns([4, 1])
        col1.write(f"{job_label} → {dest_label}")
        if col2.button("Queue this", key=f"queue_draft_{draft['id']}"):
            try:
                post(f"/posts/{draft['id']}/queue", json={})
                st.rerun()
            except APIError as exc:
                st.error(str(exc))

st.divider()

# --- Progress ---
st.subheader("Progress")
try:
    progress = get("/posts/progress")
    cols = st.columns(len(progress["counts"]))
    for col, (status_name, count) in zip(cols, progress["counts"].items()):
        col.metric(status_name, count)
    st.caption(f"{progress['total']} post(s) total")
except APIError as exc:
    st.error(f"Couldn't load progress: {exc}")

st.divider()

# --- Queue management ---
st.subheader("Manage queue")

col1, col2, col3 = st.columns(3)
filter_job_label = col1.selectbox("Filter by job", ["All"] + list(job_options.keys()), key="mgmt_job")
filter_dest_label = col2.selectbox("Filter by destination", ["All"] + list(dest_options.keys()), key="mgmt_dest")
filter_status = col3.selectbox("Status", ["All"] + [s.value for s in PostStatus], key="mgmt_status")

params: dict = {"skip": (get_page("queue_page") - 1) * PAGE_SIZE, "limit": PAGE_SIZE}
if filter_job_label != "All":
    params["job_id"] = job_options[filter_job_label]
if filter_dest_label != "All":
    params["destination_id"] = dest_options[filter_dest_label]
if filter_status != "All":
    params["status"] = filter_status

try:
    posts_result = get("/posts", params=params)
except APIError as exc:
    st.error(f"Couldn't load queue: {exc}")
    posts_result = {"items": [], "total": 0}

queue_items = posts_result["items"]
total = posts_result["total"]

if total == 0:
    if filter_job_label != "All" or filter_dest_label != "All" or filter_status != "All":
        st.info("No posts match your filters. Try broadening them.")
    else:
        st.info("Nothing queued yet — create a batch above, or promote a draft from Post Creator.")
else:
    st.caption(f"{total} post{'s' if total != 1 else ''} found")

job_titles_by_id = {j["id"]: j["title"] for j in jobs_list}
dest_labels_by_id = {d["id"]: f"{d['name']} ({d['platform']})" for d in destinations_list}

for item in queue_items:
    job_label = job_titles_by_id.get(item["job_id"], f"Job #{item['job_id']}")
    dest_label = dest_labels_by_id.get(item["destination_id"], f"Destination #{item['destination_id']}")
    paused_tag = " ⏸ paused" if item["paused"] else ""
    scheduled_tag = f" · scheduled {item['scheduled_at']}" if item.get("scheduled_at") else ""

    with st.expander(f"{job_label} → {dest_label} · {item['status']}{paused_tag}{scheduled_tag}"):
        st.code(item["content"], language=None)
        if item.get("error_message"):
            st.error(item["error_message"])

        dest_url = dest_urls_by_id.get(item["destination_id"])
        if dest_url:
            st.link_button("Open destination", dest_url)

        if dest_platform_by_id.get(item["destination_id"]) == "TikTok" and item["status"] not in (
            PostStatus.POSTED.value,
            PostStatus.SKIPPED.value,
        ):
            # Phase 9: TikTok defaults to a manual workflow (no audited API
            # access for most users — see PROJECT_STATUS.md section 14), so
            # the only thing automatable here is preparing the recruitment
            # graphic itself. Posting it and resolving the outcome is the
            # generic Processing-row actions below, same as any other
            # manually-completed post.
            if item.get("media_path"):
                st.image(item["media_path"], caption="Generated visual", width=220)
                visual_button_label = "Regenerate visual"
            else:
                visual_button_label = "Generate visual"
            if st.button(visual_button_label, key=f"gen_visual_{item['id']}"):
                try:
                    with st.spinner("Generating recruitment visual..."):
                        post(f"/posts/{item['id']}/generate-tiktok-visual")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))

        c1, c2, c3, c4, c5 = st.columns(5)

        if item["status"] == PostStatus.QUEUED.value:
            if dest_platform_by_id.get(item["destination_id"]) == "Telegram":
                # Phase 8: Telegram needs no human step, so "Send" does the
                # whole thing (Start + the real Bot API call + resolve to
                # Posted/Failed) in one click, unlike the generic "Start"
                # below which only flips the status and waits for
                # something else to finish the job.
                if c1.button("Send", key=f"send_telegram_{item['id']}"):
                    try:
                        with st.spinner("Sending via Telegram..."):
                            post(f"/posts/{item['id']}/send-telegram")
                        st.rerun()
                    except APIError as exc:
                        st.error(str(exc))
            elif c1.button("Start", key=f"start_{item['id']}"):
                try:
                    post(f"/posts/{item['id']}/start")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))
        elif item["status"] == PostStatus.PROCESSING.value:
            # Phase 9: the generic escape hatch flagged back in Phase 7's
            # design notes — a Processing post with no dedicated assistant
            # page (TikTok's MANUAL workflow, or any post someone Started
            # by hand) needs *some* way to record what actually happened.
            # Reuses the same mark-posted/mark-failed endpoints the
            # Facebook Assistant and Telegram send already call.
            if c1.button("Mark Posted", key=f"mark_posted_{item['id']}"):
                try:
                    post(f"/posts/{item['id']}/mark-posted")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))

        if item["paused"]:
            if c2.button("Resume", key=f"resume_{item['id']}"):
                try:
                    post(f"/posts/{item['id']}/resume")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))
        else:
            if c2.button("Pause", key=f"pause_{item['id']}"):
                try:
                    post(f"/posts/{item['id']}/pause")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))

        if item["status"] not in (PostStatus.POSTED.value, PostStatus.SKIPPED.value):
            if c3.button("Skip", key=f"skip_{item['id']}"):
                try:
                    post(f"/posts/{item['id']}/skip")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))

        if item["status"] == PostStatus.FAILED.value:
            if c4.button("Retry", key=f"retry_{item['id']}"):
                try:
                    post(f"/posts/{item['id']}/retry")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))
        elif item["status"] == PostStatus.PROCESSING.value:
            if c4.button("Mark Failed", key=f"mark_failed_{item['id']}"):
                try:
                    post(f"/posts/{item['id']}/mark-failed", json={"error_message": None})
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))

        if item["status"] == PostStatus.QUEUED.value:
            # Phase 10: opting a post into unattended sending is a
            # separate, explicit choice from Queued itself — see
            # PROJECT_STATUS.md section 14. Only offered when there's a
            # scheduled_at time for the ticker to compare against.
            if item.get("scheduled_at") and c5.button("Schedule", key=f"schedule_{item['id']}"):
                try:
                    post(f"/posts/{item['id']}/schedule")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))
        elif item["status"] == PostStatus.SCHEDULED.value:
            if c5.button("Unschedule", key=f"unschedule_{item['id']}"):
                try:
                    post(f"/posts/{item['id']}/unschedule")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))

render_pagination_controls(total, PAGE_SIZE, "queue_page")
