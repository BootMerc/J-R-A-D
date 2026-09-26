"""Post Creator page — generate post content from a job + destination(s) +
template(s), compare variations, browse/edit/delete the results.

Content renders in st.code() blocks, which give a built-in copy-to-clipboard
button — that's what satisfies Section 40's "Copy to clipboard" for this
phase. (Not to be confused with Phase 7's pyperclip, which copies to the OS
clipboard as part of the Facebook assistant's browser-automation-free
workflow — different mechanism for a different job.)

Same pattern as the other pages: talks to the backend only through
frontend/components/api_client.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from app.config.settings import get_settings
from app.database.enums import PostStatus
from frontend.components.api_client import APIError, delete, get, patch, post
from frontend.components.pagination import get_page, render_pagination_controls

settings = get_settings()
st.set_page_config(page_title=f"Post Creator — {settings.app_name}", page_icon="✍️", layout="wide")

PAGE_SIZE = 20

st.title("Post Creator")

try:
    jobs_list = get("/jobs", params={"limit": 200, "include_archived": True})["items"]
except APIError:
    jobs_list = []
try:
    destinations_list = get("/destinations", params={"limit": 200, "active": True})["items"]
except APIError:
    destinations_list = []

job_options = {f"{j['title']} (#{j['id']})": j["id"] for j in jobs_list}
dest_options = {f"{d['name']} ({d['platform']})": d["id"] for d in destinations_list}
dest_platform_by_id = {d["id"]: d["platform"] for d in destinations_list}

if not jobs_list or not destinations_list:
    st.info("Create at least one job and one active destination before generating posts.")

# --- Generate posts across destinations ---
st.subheader("Generate posts")
st.caption(
    "Pick a job and one or more destinations. Leave the template on auto-select "
    "and a suitable active template is chosen per destination's platform "
    "(preferring a language match) — or force one specific template, in which "
    "case any destination on a different platform is skipped, not mis-rendered."
)

if jobs_list and destinations_list:
    gen_job_label = st.selectbox("Job", list(job_options.keys()), key="gen_job")
    gen_dest_labels = st.multiselect("Destinations", list(dest_options.keys()), key="gen_dests")

    template_mode = st.radio(
        "Template", ["Auto-select per platform", "Use one specific template"], key="gen_template_mode"
    )
    forced_template_id = None
    if template_mode == "Use one specific template":
        try:
            active_templates = get("/templates", params={"limit": 200, "active": True})["items"]
        except APIError:
            active_templates = []
        if active_templates:
            template_labels = {f"{t['name']} ({t['platform']})": t["id"] for t in active_templates}
            selected_label = st.selectbox("Template", list(template_labels.keys()), key="gen_template_pick")
            forced_template_id = template_labels[selected_label]
        else:
            st.caption("No active templates exist yet.")

    if st.button("Generate posts", disabled=not gen_dest_labels):
        payload = {
            "job_id": job_options[gen_job_label],
            "destination_ids": [dest_options[label] for label in gen_dest_labels],
        }
        if forced_template_id is not None:
            payload["template_id"] = forced_template_id
        try:
            result = post("/posts/generate", json=payload)
            st.success(f"Generated {len(result['created'])} post(s).")
            if result["errors"]:
                st.warning("Some destinations were skipped:")
                for err in result["errors"]:
                    st.write(f"- {err}")
            st.rerun()
        except APIError as exc:
            st.error(str(exc))

st.divider()

# --- Generate variations for one destination ---
st.subheader("Generate variations")
st.caption(
    "Compare different tones (Professional, Urgent, Fresh Graduates, Arabic, "
    "Bilingual...) for the same job and destination, side by side."
)

if jobs_list and destinations_list:
    var_job_label = st.selectbox("Job", list(job_options.keys()), key="var_job")
    var_dest_label = st.selectbox("Destination", list(dest_options.keys()), key="var_dest")
    var_dest_id = dest_options[var_dest_label]
    var_platform = dest_platform_by_id[var_dest_id]

    try:
        matching_templates = get("/templates", params={"platform": var_platform, "limit": 200})["items"]
    except APIError:
        matching_templates = []

    if not matching_templates:
        st.caption(f"No templates exist yet for {var_platform}.")
    else:
        variation_options = {
            f"{t['name']} ({t.get('language') or 'any language'})": t["id"] for t in matching_templates
        }
        selected_variations = st.multiselect(
            f"Templates to compare (must all be {var_platform})",
            list(variation_options.keys()),
            key="var_templates",
        )
        if st.button("Generate variations", disabled=not selected_variations):
            payload = {
                "job_id": job_options[var_job_label],
                "destination_id": var_dest_id,
                "template_ids": [variation_options[label] for label in selected_variations],
            }
            try:
                result = post("/posts/generate-variations", json=payload)
                st.success(f"Generated {len(result['created'])} variation(s).")
                for err in result["errors"]:
                    st.warning(err)
                st.rerun()
            except APIError as exc:
                st.error(str(exc))

st.divider()

# --- Browse / edit / delete generated posts ---
st.subheader("Generated posts")

col1, col2, col3 = st.columns(3)
filter_job_label = col1.selectbox("Filter by job", ["All"] + list(job_options.keys()), key="filter_job")
filter_dest_label = col2.selectbox("Filter by destination", ["All"] + list(dest_options.keys()), key="filter_dest")
filter_status = col3.selectbox("Status", ["All"] + [s.value for s in PostStatus], key="filter_status")

params: dict = {"skip": (get_page("posts_page") - 1) * PAGE_SIZE, "limit": PAGE_SIZE}
if filter_job_label != "All":
    params["job_id"] = job_options[filter_job_label]
if filter_dest_label != "All":
    params["destination_id"] = dest_options[filter_dest_label]
if filter_status != "All":
    params["status"] = filter_status

try:
    posts_result = get("/posts", params=params)
except APIError as exc:
    st.error(f"Couldn't load posts: {exc}")
    posts_result = {"items": [], "total": 0}

posts_page_items = posts_result["items"]
total = posts_result["total"]

if total == 0:
    if filter_job_label != "All" or filter_dest_label != "All" or filter_status != "All":
        st.info("No posts match your filters. Try broadening them.")
    else:
        st.info("No posts yet — generate some above.")
else:
    st.caption(f"{total} post{'s' if total != 1 else ''} found")

job_titles_by_id = {j["id"]: j["title"] for j in jobs_list}
dest_labels_by_id = {d["id"]: f"{d['name']} ({d['platform']})" for d in destinations_list}

for item in posts_page_items:
    job_label = job_titles_by_id.get(item["job_id"], f"Job #{item['job_id']}")
    dest_label = dest_labels_by_id.get(item["destination_id"], f"Destination #{item['destination_id']}")

    with st.expander(f"{job_label} → {dest_label} · {item['status']}"):
        editing_key = f"editing_post_{item['id']}"
        confirm_key = f"confirm_del_post_{item['id']}"

        if st.session_state.get(editing_key):
            new_content = st.text_area(
                "Content", value=item["content"], height=200, key=f"content_input_{item['id']}"
            )
            c1, c2 = st.columns(2)
            if c1.button("Save", key=f"save_post_{item['id']}"):
                try:
                    patch(f"/posts/{item['id']}", json={"content": new_content})
                    st.session_state[editing_key] = False
                    st.success("Saved.")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))
            if c2.button("Cancel", key=f"cancel_edit_post_{item['id']}"):
                st.session_state[editing_key] = False
                st.rerun()
        elif st.session_state.get(confirm_key):
            st.warning("Delete this post? This can't be undone.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, delete", key=f"confirm_yes_post_{item['id']}"):
                try:
                    delete(f"/posts/{item['id']}")
                    st.session_state[confirm_key] = False
                    st.success("Deleted.")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))
            if c2.button("Cancel", key=f"confirm_no_post_{item['id']}"):
                st.session_state[confirm_key] = False
                st.rerun()
        else:
            st.code(item["content"], language=None)
            c1, c2 = st.columns(2)
            if c1.button("Edit content", key=f"edit_post_{item['id']}"):
                st.session_state[editing_key] = True
                st.rerun()
            if c2.button("Delete", key=f"del_post_{item['id']}"):
                st.session_state[confirm_key] = True
                st.rerun()

render_pagination_controls(total, PAGE_SIZE, "posts_page")
