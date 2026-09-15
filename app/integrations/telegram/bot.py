"""Phase 8 — Telegram: a plain HTTPS call against the Bot API, not the
`python-telegram-bot` package (see PROJECT_STATUS.md section 14 — that
library is built around *receiving* updates via polling/webhooks; this
project only ever sends, so the full framework is unneeded weight).

send_message() is the only function here and, like
app/integrations/facebook/assistant.py's functions, never raises — every
failure mode (no token configured, no chat_id configured, Telegram's own
{"ok": false, "description": ...} envelope, a network error, a timeout, an
unparseable response) becomes (False, None, "<human-readable reason>")
instead of an exception. PostService.send_telegram_post() stores that
reason directly as the post's error_message, so it needs to already read
naturally — not a repr() of an exception.
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


def send_message(
    bot_token: Optional[str], chat_id: Optional[str], text: str
) -> tuple[bool, Optional[str], Optional[str]]:
    """POSTs to Telegram's Bot API sendMessage endpoint. Returns
    (success, message_id, error_description).

    chat_id is passed through as given — Destination.external_id is a
    plain string column, and Telegram's HTTP API accepts chat_id as
    either a numeric id (as a string or a number) or an "@channelusername"
    string, so no parsing/coercion happens here.
    """
    if not bot_token:
        return False, None, "No Telegram bot token configured (TELEGRAM_BOT_TOKEN)"
    if not chat_id:
        return False, None, "This destination has no chat_id configured (Destination.external_id)"

    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"
    try:
        response = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=15.0)
    except Exception as exc:
        # Covers httpx's own RequestError family (connection refused, DNS
        # failure, timeout, TLS error, a blocked/firewalled host — this
        # project's own dev sandbox blocks api.telegram.org outright, which
        # exercises exactly this path) as well as anything else a network
        # call could throw. A recruiter's machine being offline is a very
        # real scenario for a locally-run tool; it must not crash the
        # request.
        logger.warning("Telegram sendMessage request failed: %s", exc)
        return False, None, f"Couldn't reach Telegram: {exc}"

    try:
        payload = response.json()
    except ValueError:
        return False, None, f"Telegram returned a non-JSON response (HTTP {response.status_code})"

    if payload.get("ok"):
        message_id = payload.get("result", {}).get("message_id")
        return True, (str(message_id) if message_id is not None else None), None

    description = payload.get("description") or f"Telegram request failed (HTTP {response.status_code})"
    return False, None, description
