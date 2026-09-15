# Uses a simple HTTPS request to the Telegram Bot API instead of the
# python-telegram-bot package. The project only sends messages, so the
# full framework isn't needed.
#
# send_message() handles all failures itself and never raises. Missing
# configuration, Telegram API errors, network/timeout issues, or invalid
# responses are returned as a simple (False, None, reason) result.
#
# The error message is stored directly by PostService, so the reason should
# be clear and human-readable rather than a raw exception or repr().

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
