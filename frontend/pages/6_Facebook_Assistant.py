# Facebook Assistant page 
# For each Facebook post, the user can open the destination URL in their
# browser, copy the post content to the clipboard, then move to the next one.
#
# No Playwright or DOM automation is used. The backend only opens the URL
# and copies the content through app/integrations/facebook/assistant.py.
#
# The current queue position is kept in the page's session state rather than
# the database. Post.status already stores the actual outcome (Queued ->
# Processing -> Posted/Failed/Skipped), while session state only tracks
# which posts this browser tab has moved past.
#
# As with the other pages, all backend communication goes through
# frontend/components/api_client.py.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import streamlit.components.v1 as components

from app.config.settings import get_settings
from frontend.components.api_client import APIError, get, post

settings = get_settings()
st.set_page_config(page_title=f"Facebook Assistant — {settings.app_name}", page_icon="🖱️", layout="wide")

st.title("Facebook Assistant")
st.caption(
    "Works through your Queued Facebook posts one group at a time: opens the group in "
    "your browser and copies the post to your clipboard. Paste and click Post yourself — "
    "nothing here clicks anything on Facebook's page for you."
)

try:
    candidates = get("/posts/facebook-queue")
except APIError as exc:
    st.error(f"Couldn't load the Facebook queue: {exc}")
    candidates = []

if not candidates:
    st.info(
        "No Facebook posts are queued right now. Create some from the Queue page, "
        "then come back here."
    )
    st.stop()

try:
    jobs_list = get("/jobs", params={"limit": 500, "include_archived": True})["items"]
except APIError:
    jobs_list = []
try:
    # No active=True filter here (unlike the Queue page's picker): a post
    # already queued against a since-deactivated destination should still
    # show its real name and URL, not a bare "Destination #12".
    destinations_list = get("/destinations", params={"limit": 500})["items"]
except APIError:
    destinations_list = []

job_titles_by_id = {j["id"]: j["title"] for j in jobs_list}
destinations_by_id = {d["id"]: d for d in destinations_list}

# --- Session state -----------------------------------------------------
# fb_engaged: post_id -> cached {browser_opened, clipboard_copied} result
#   from the one time per post we actually call /facebook-assist, so a
#   rerun triggered by something else on the page (typing a failure
#   reason, etc.) doesn't reopen the browser or recopy the clipboard.
# fb_skipped_ids: post ids passed over via "Next" this session. Cleared
#   automatically once every candidate has been passed over, so nothing
#   is ever permanently hidden — you just cycle back to the top.
st.session_state.setdefault("fb_engaged", {})
st.session_state.setdefault("fb_skipped_ids", set())

available = [p for p in candidates if p["id"] not in st.session_state.fb_skipped_ids]
if not available:
    st.session_state.fb_skipped_ids = set()
    available = candidates

current = available[0]
total_remaining = len(candidates)

if current["id"] not in st.session_state.fb_engaged:
    try:
        with st.spinner("Opening the group and copying the post..."):
            result = post(f"/posts/{current['id']}/facebook-assist")
        st.session_state.fb_engaged[current["id"]] = {
            "browser_opened": result["browser_opened"],
            "clipboard_copied": result["clipboard_copied"],
        }
        current = result["post"]
    except APIError as exc:
        st.error(f"Couldn't start this post: {exc}")
        st.stop()

engage_info = st.session_state.fb_engaged.get(current["id"], {})
job_label = job_titles_by_id.get(current["job_id"], f"Job #{current['job_id']}")
destination = destinations_by_id.get(current["destination_id"], {})
dest_label = destination.get("name") or f"Destination #{current['destination_id']}"

st.caption(f"{total_remaining} Facebook post{'s' if total_remaining != 1 else ''} left to review")
st.subheader(f"{job_label} → {dest_label}")
if current.get("scheduled_at"):
    st.caption(f"Scheduled: {current['scheduled_at']}")

if engage_info.get("clipboard_copied"):
    st.success("Copied to your clipboard.")
else:
    st.warning("Couldn't copy to the clipboard automatically — copy the text below manually.")

dest_url = destination.get("url")
if dest_url:
    if not engage_info.get("browser_opened"):
        st.warning("Couldn't open the browser automatically — use the button below.")
    st.link_button("Open destination", dest_url)
else:
    st.warning("This destination has no URL on file.")

st.code(current["content"], language=None)

fail_reason = st.text_input(
    "Failure reason (optional — only used if you click Failed)",
    key=f"fb_fail_reason_{current['id']}",
)


def _advance(post_id: int) -> None:
    st.session_state.fb_skipped_ids.discard(post_id)
    st.session_state.fb_engaged.pop(post_id, None)


c1, c2, c3, c4, c5 = st.columns(5)

if c1.button("Posted", key=f"fb_posted_{current['id']}", type="primary", use_container_width=True):
    try:
        post(f"/posts/{current['id']}/mark-posted")
        _advance(current["id"])
        st.rerun()
    except APIError as exc:
        st.error(str(exc))

if c2.button("Skip", key=f"fb_skip_{current['id']}", use_container_width=True):
    try:
        post(f"/posts/{current['id']}/skip")
        _advance(current["id"])
        st.rerun()
    except APIError as exc:
        st.error(str(exc))

if c3.button("Failed", key=f"fb_failed_{current['id']}", use_container_width=True):
    try:
        post(f"/posts/{current['id']}/mark-failed", json={"error_message": fail_reason or None})
        _advance(current["id"])
        st.rerun()
    except APIError as exc:
        st.error(str(exc))

if c4.button("Pause", key=f"fb_pause_{current['id']}", use_container_width=True):
    try:
        post(f"/posts/{current['id']}/pause")
        _advance(current["id"])
        st.rerun()
    except APIError as exc:
        st.error(str(exc))

if c5.button("Next", key=f"fb_next_{current['id']}", use_container_width=True):
    st.session_state.fb_skipped_ids.add(current["id"])
    st.rerun()

st.caption("Keyboard: Enter = Posted · S = Skip · P = Pause · N = Next (not while typing in a text box)")

# Streamlit has no native global key handler (see PROJECT_STATUS.md section
# 18), so this finds the real Streamlit buttons above by their visible text
# and clicks them from a keydown listener on the parent document. Best
# effort — not exercised by a real browser in this project's test suite
# (see tests/test_facebook_assistant.py and test_posts.py for what IS
# covered); flag it if a shortcut doesn't fire and it'll get fixed.
components.html(
    """
    <script>
    (function() {
      const doc = window.parent.document;
      function clickByText(text) {
        const buttons = Array.from(doc.querySelectorAll('button'));
        const btn = buttons.find((b) => b.innerText.trim() === text);
        if (btn) { btn.click(); }
      }
      function handler(e) {
        if (e.repeat) { return; }
        const tag = (e.target && e.target.tagName) || '';
        if (tag === 'INPUT' || tag === 'TEXTAREA') { return; }
        if (e.key === 'Enter') { clickByText('Posted'); }
        else if (e.key === 's' || e.key === 'S') { clickByText('Skip'); }
        else if (e.key === 'p' || e.key === 'P') { clickByText('Pause'); }
        else if (e.key === 'n' || e.key === 'N') { clickByText('Next'); }
      }
      if (doc.__fbAssistantKeyHandler) {
        doc.removeEventListener('keydown', doc.__fbAssistantKeyHandler);
      }
      doc.__fbAssistantKeyHandler = handler;
      doc.addEventListener('keydown', handler);
    })();
    </script>
    """,
    height=0,
)
