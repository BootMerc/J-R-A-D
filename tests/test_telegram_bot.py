"""Phase 8 tests for app/integrations/telegram/bot.py — send_message(),
fully mocked so these never make a real network call to Telegram during a
test run. Service/API-level Phase 8 tests (PostService.send_telegram_post
and POST /posts/{id}/send-telegram) live in test_posts.py instead,
alongside the rest of the Posts/Queue suite they extend.

Phase 13 additions cover more of Telegram's actual documented error
shapes (401 invalid token, 403 blocked-by-user, 429 rate limited) beyond
the original single generic-400 case, plus a couple of edge cases
(missing message_id on an ok:true response, a timeout distinct from a
connection error) — hardening the mock coverage without changing any
production code.
"""

from unittest.mock import MagicMock, patch

import httpx

from app.integrations.telegram.bot import send_message


def _mock_response(json_data, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    return response


def test_send_message_returns_false_without_bot_token():
    with patch("app.integrations.telegram.bot.httpx.post") as mock_post:
        success, message_id, error = send_message(None, "12345", "Hiring now")
    assert success is False
    assert message_id is None
    assert "bot token" in error.lower()
    mock_post.assert_not_called()


def test_send_message_returns_false_without_chat_id():
    with patch("app.integrations.telegram.bot.httpx.post") as mock_post:
        success, message_id, error = send_message("real-token", "", "Hiring now")
    assert success is False
    assert message_id is None
    assert "chat_id" in error.lower() or "chat id" in error.lower()
    mock_post.assert_not_called()


def test_send_message_success_extracts_message_id():
    ok_response = _mock_response({"ok": True, "result": {"message_id": 42}})
    with patch("app.integrations.telegram.bot.httpx.post", return_value=ok_response) as mock_post:
        success, message_id, error = send_message("real-token", "12345", "Hiring now")

    assert success is True
    assert message_id == "42"
    assert error is None
    mock_post.assert_called_once_with(
        "https://api.telegram.org/botreal-token/sendMessage",
        json={"chat_id": "12345", "text": "Hiring now"},
        timeout=15.0,
    )


def test_send_message_telegram_rejection_returns_description():
    rejected = _mock_response({"ok": False, "error_code": 400, "description": "Bad Request: chat not found"})
    with patch("app.integrations.telegram.bot.httpx.post", return_value=rejected):
        success, message_id, error = send_message("real-token", "wrong-chat", "Hiring now")

    assert success is False
    assert message_id is None
    assert error == "Bad Request: chat not found"


def test_send_message_invalid_token_returns_description():
    """Telegram's real shape for a revoked/typo'd bot token — a
    token-level problem, distinct from a chat-level one like the generic
    400 case above."""
    unauthorized = _mock_response({"ok": False, "error_code": 401, "description": "Unauthorized"}, status_code=401)
    with patch("app.integrations.telegram.bot.httpx.post", return_value=unauthorized):
        success, message_id, error = send_message("revoked-token", "12345", "Hiring now")

    assert success is False
    assert message_id is None
    assert error == "Unauthorized"


def test_send_message_bot_blocked_by_user_returns_description():
    """Telegram's real shape when the bot can't message a chat it's
    been blocked in/removed from — a common real-world failure that has
    nothing to do with the message content or the token."""
    forbidden = _mock_response(
        {"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"},
        status_code=403,
    )
    with patch("app.integrations.telegram.bot.httpx.post", return_value=forbidden):
        success, message_id, error = send_message("real-token", "12345", "Hiring now")

    assert success is False
    assert error == "Forbidden: bot was blocked by the user"


def test_send_message_rate_limited_returns_description():
    """Telegram's real shape for rate limiting — includes an extra
    parameters.retry_after field beyond the generic {ok, description}
    shape; send_message() only needs the description, but this confirms
    the extra field doesn't break parsing."""
    rate_limited = _mock_response(
        {
            "ok": False,
            "error_code": 429,
            "description": "Too Many Requests: retry after 30",
            "parameters": {"retry_after": 30},
        },
        status_code=429,
    )
    with patch("app.integrations.telegram.bot.httpx.post", return_value=rate_limited):
        success, message_id, error = send_message("real-token", "12345", "Hiring now")

    assert success is False
    assert error == "Too Many Requests: retry after 30"


def test_send_message_ok_true_without_message_id_does_not_crash():
    """A degenerate but real-shaped success response — ok: true with no
    message_id in result. Must not raise; message_id should just come
    back None rather than the call failing."""
    odd_response = _mock_response({"ok": True, "result": {}})
    with patch("app.integrations.telegram.bot.httpx.post", return_value=odd_response):
        success, message_id, error = send_message("real-token", "12345", "Hiring now")

    assert success is True
    assert message_id is None
    assert error is None


def test_send_message_timeout_returns_graceful_failure():
    """A timeout is a distinct httpx exception from ConnectError — both
    should be caught by the same broad except Exception, but this
    confirms that explicitly rather than assuming one exception type
    stands in for all of them."""
    with patch(
        "app.integrations.telegram.bot.httpx.post", side_effect=httpx.TimeoutException("timed out")
    ):
        success, message_id, error = send_message("real-token", "12345", "Hiring now")

    assert success is False
    assert message_id is None
    assert "Couldn't reach Telegram" in error


def test_send_message_network_error_returns_graceful_failure():
    """The exact failure mode this project's own dev sandbox hits — see
    PROJECT_STATUS.md section 15 — api.telegram.org blocked/unreachable."""
    with patch(
        "app.integrations.telegram.bot.httpx.post", side_effect=httpx.ConnectError("blocked")
    ):
        success, message_id, error = send_message("real-token", "12345", "Hiring now")

    assert success is False
    assert message_id is None
    assert "Couldn't reach Telegram" in error


def test_send_message_non_json_response_returns_graceful_failure():
    bad_response = MagicMock()
    bad_response.status_code = 502
    bad_response.json.side_effect = ValueError("not json")
    with patch("app.integrations.telegram.bot.httpx.post", return_value=bad_response):
        success, message_id, error = send_message("real-token", "12345", "Hiring now")

    assert success is False
    assert message_id is None
    assert "502" in error
