"""Shared HTTP client for Streamlit pages talking to the FastAPI backend.

Every feature page (Jobs now; Destinations, Templates, etc. from Phase 3
onward) goes through this instead of each page rolling its own httpx calls.
"""

from typing import Any, Optional

import httpx

from app.config.settings import get_settings

_settings = get_settings()
BASE_URL = f"http://{_settings.api_host}:{_settings.api_port}"


class APIError(Exception):
    """Raised for any non-2xx response or connection failure. str(exc) is
    a message safe to show directly in the UI."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _handle_response(response: httpx.Response) -> Any:
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise APIError(str(detail), response.status_code)
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def get(path: str, params: Optional[dict] = None) -> Any:
    try:
        response = httpx.get(f"{BASE_URL}{path}", params=params, timeout=10.0)
    except httpx.HTTPError as exc:
        raise APIError(f"Couldn't reach the backend at {BASE_URL}: {exc}") from exc
    return _handle_response(response)


def post(path: str, json: Optional[dict] = None) -> Any:
    try:
        response = httpx.post(f"{BASE_URL}{path}", json=json, timeout=10.0)
    except httpx.HTTPError as exc:
        raise APIError(f"Couldn't reach the backend at {BASE_URL}: {exc}") from exc
    return _handle_response(response)


def patch(path: str, json: Optional[dict] = None) -> Any:
    try:
        response = httpx.patch(f"{BASE_URL}{path}", json=json, timeout=10.0)
    except httpx.HTTPError as exc:
        raise APIError(f"Couldn't reach the backend at {BASE_URL}: {exc}") from exc
    return _handle_response(response)


def delete(path: str) -> Any:
    try:
        response = httpx.delete(f"{BASE_URL}{path}", timeout=10.0)
    except httpx.HTTPError as exc:
        raise APIError(f"Couldn't reach the backend at {BASE_URL}: {exc}") from exc
    return _handle_response(response)


def post_file(path: str, filename: str, file_bytes: bytes, content_type: str = "text/csv") -> Any:
    try:
        response = httpx.post(
            f"{BASE_URL}{path}",
            files={"file": (filename, file_bytes, content_type)},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise APIError(f"Couldn't reach the backend at {BASE_URL}: {exc}") from exc
    return _handle_response(response)


def get_raw(path: str, params: Optional[dict] = None) -> bytes:
    """Like get(), but returns raw response bytes instead of parsed JSON —
    for file downloads (e.g. CSV export)."""
    try:
        response = httpx.get(f"{BASE_URL}{path}", params=params, timeout=30.0)
    except httpx.HTTPError as exc:
        raise APIError(f"Couldn't reach the backend at {BASE_URL}: {exc}") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise APIError(str(detail), response.status_code)
    return response.content
