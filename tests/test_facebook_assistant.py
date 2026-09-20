"""Phase 7 tests for app/integrations/facebook/assistant.py — the pure
OS-wrapper functions (webbrowser.open / pyperclip.copy), fully mocked so
these never pop open a real browser or touch the real clipboard during a
test run. Service/API-level Phase 7 tests (PostService.start_facebook_assist,
mark_posted, mark_failed, and the /posts endpoints) live in test_posts.py
instead, alongside the rest of the Posts/Queue suite they extend.
"""

from unittest.mock import patch

import pyperclip

from app.integrations.facebook.assistant import copy_content, open_destination


def test_open_destination_calls_webbrowser_open():
    with patch("app.integrations.facebook.assistant.webbrowser.open", return_value=True) as mock_open:
        assert open_destination("https://facebook.com/groups/123") is True
    mock_open.assert_called_once_with("https://facebook.com/groups/123", new=2)


def test_open_destination_returns_false_for_missing_url():
    with patch("app.integrations.facebook.assistant.webbrowser.open") as mock_open:
        assert open_destination("") is False
        assert open_destination(None) is False
    mock_open.assert_not_called()


def test_open_destination_returns_false_on_exception_instead_of_raising():
    with patch(
        "app.integrations.facebook.assistant.webbrowser.open", side_effect=RuntimeError("no display")
    ):
        assert open_destination("https://facebook.com/groups/123") is False


def test_copy_content_calls_pyperclip_copy():
    with patch("app.integrations.facebook.assistant.pyperclip.copy") as mock_copy:
        assert copy_content("Hiring a cashier") is True
    mock_copy.assert_called_once_with("Hiring a cashier")


def test_copy_content_returns_false_when_no_clipboard_mechanism():
    """The exact failure mode a Linux box without xclip/xsel hits — see
    PROJECT_STATUS.md section 18's testing note. Must not raise."""
    with patch(
        "app.integrations.facebook.assistant.pyperclip.copy",
        side_effect=pyperclip.PyperclipException("no xclip or xsel"),
    ):
        assert copy_content("Hiring a cashier") is False


def test_copy_content_returns_false_on_unexpected_exception_instead_of_raising():
    with patch(
        "app.integrations.facebook.assistant.pyperclip.copy", side_effect=RuntimeError("unexpected")
    ):
        assert copy_content("Hiring a cashier") is False
