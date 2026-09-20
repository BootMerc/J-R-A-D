"""Phase 12 — Backup: copies the live SQLite database into backups/ with
a timestamped filename, then prunes old backups beyond a retention count.

Run directly (`python scripts/backup.py`) or via backup.bat on Windows.
Safe to run while the app is up — SQLite's own file-level locking during
a plain file copy is the same situation a Windows Explorer copy of the
same file would be in; the actual risk this project cares about is
RESTORE overwriting a live file, not backup reading one (see restore.py).
"""

import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import get_settings

DEFAULT_RETENTION = 10


def backup(retention: int = DEFAULT_RETENTION) -> Path:
    settings = get_settings()
    if not settings.database_url.startswith("sqlite:///"):
        raise ValueError(
            f"backup.py only supports a sqlite:/// DATABASE_URL (this project's only "
            f"supported database); got: {settings.database_url}"
        )
    db_path = Path(settings.database_url[len("sqlite:///") :])
    if not db_path.exists():
        raise FileNotFoundError(f"No database found at {db_path} — nothing to back up.")

    backups_dir = Path(__file__).resolve().parent.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    destination = _unique_backup_path(backups_dir)
    shutil.copy2(db_path, destination)

    _prune_old_backups(backups_dir, retention)
    return destination


def _unique_backup_path(backups_dir: Path) -> Path:
    """A timestamped filename, guaranteed not to already exist — never
    silently overwrites an existing backup. Second-granularity timestamps
    alone aren't enough: two backups within the same second (e.g.
    restore()'s own safety-backup step running right after a manual
    backup) would otherwise collide and the second call would overwrite
    the first, which is exactly backwards for a backup tool. Confirmed
    happening before this fix — see PROJECT_STATUS.md section 13."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = backups_dir / f"recruitment_{timestamp}.db"
    suffix = 1
    while candidate.exists():
        candidate = backups_dir / f"recruitment_{timestamp}_{suffix}.db"
        suffix += 1
    return candidate


def _prune_old_backups(backups_dir: Path, retention: int) -> None:
    """Keeps the most recent `retention` backups, deletes the rest —
    backups/ would otherwise grow unbounded on a tool meant to run
    continuously in the background (Phase 10's scheduler)."""
    existing = sorted(backups_dir.glob("recruitment_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old_backup in existing[retention:]:
        old_backup.unlink()


if __name__ == "__main__":
    try:
        result_path = backup()
    except (ValueError, FileNotFoundError) as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    print(f"Backed up to {result_path}")
