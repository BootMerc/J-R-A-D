"""Shared pagination for Streamlit list pages.

Usage:
    page = get_page("jobs_page")               # early, to compute skip/limit
    ... fetch and render results using `page` ...
    render_pagination_controls(total, PAGE_SIZE, "jobs_page")   # at the bottom
"""

import streamlit as st


def get_page(state_key: str) -> int:
    if state_key not in st.session_state:
        st.session_state[state_key] = 1
    return st.session_state[state_key]


def render_pagination_controls(total: int, page_size: int, state_key: str) -> None:
    current = get_page(state_key)
    total_pages = max(1, (total + page_size - 1) // page_size)

    col1, col2, col3 = st.columns([1, 2, 1])
    if col1.button("Previous", disabled=current <= 1, key=f"{state_key}_prev"):
        st.session_state[state_key] = current - 1
        st.rerun()
    col2.write(f"Page {current} of {total_pages}")
    if col3.button("Next", disabled=current >= total_pages, key=f"{state_key}_next"):
        st.session_state[state_key] = current + 1
        st.rerun()
