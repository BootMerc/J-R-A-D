# These are the only two OS-level actions the project performs for Facebook:
# opening a destination URL and copying post content to the clipboard.
#
# No Playwright or DOM automation is used. open_destination() only opens the
# URL in the default browser, while copy_content() only writes to the OS
# clipboard. Neither function reads or interacts with Facebook itself.
#
# Both functions handle their own errors and return a bool instead of raising.
# This lets PostService report failures to the user without breaking the
# Facebook Assistant page.
#
# pyperclip may need xclip or xsel on Linux. Windows and macOS use their
# built-in clipboard support. webbrowser.open() can also fail on headless
# machines where no browser/display is available.

import logging
import webbrowser

import pyperclip

logger = logging.getLogger(__name__)


def open_destination(url: str) -> bool:
    """Opens `url` in the user's default browser (new tab if the browser
    supports it). Returns whether that reported success — False, not an
    exception, if `url` is falsy or the OS couldn't find/launch a browser."""
    if not url:
        return False
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:
        logger.exception("Couldn't open destination URL in browser")
        return False


def copy_content(text: str) -> bool:
    """Copies `text` to the OS clipboard. Returns False (never raises) if
    the platform has no clipboard mechanism available — e.g. Linux without
    xclip/xsel installed. The Facebook Assistant page falls back to its own
    st.code() copy button when this returns False."""
    try:
        pyperclip.copy(text)
        return True
    except pyperclip.PyperclipException:
        logger.warning("Clipboard copy failed — no clipboard mechanism available on this system")
        return False
    except Exception:
        logger.exception("Unexpected error copying to clipboard")
        return False
