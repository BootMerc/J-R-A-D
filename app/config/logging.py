"""Application-wide logging configuration.

Writes to logs/app.log (rotating, so it never grows unbounded) and to the
console. Secrets (bot tokens, API keys) must never be passed to log calls —
that rule applies to every module added in later phases, not just this one.
"""

import logging
import logging.handlers
from pathlib import Path

from app.config.settings import get_settings

_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return

    settings = get_settings()
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level.upper())

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Phase 12 security review: httpx (and httpcore underneath it) logs
    # every request's full URL at INFO level by default. Since Telegram's
    # Bot API embeds the bot token directly in the URL path
    # (.../bot{token}/sendMessage), inheriting the root logger's level
    # would write the token straight into logs/app.log on every send —
    # confirmed happening before this fix, with a real token appearing in
    # the log file from a single httpx.post() call. This has nothing to
    # do with what this project's own code logs (which never logs a
    # token directly) — it's httpx's own internal logging, which needs
    # its own level set explicitly rather than silently inheriting
    # root's. WARNING still surfaces genuine httpx-level problems;
    # it just drops the routine per-request INFO line.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _configured = True
