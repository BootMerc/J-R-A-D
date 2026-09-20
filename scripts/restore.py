"""Phase 12 — Restore: copies a chosen backup file over the live
database. Run with the app fully stopped — this replaces the database
file on disk, and doing that while something else has it open can leave
things inconsistent (SQLite's own WAL/journal files aside, this is the
same risk any file-replace-while-open operation has).

Usage:
    python scripts/restore.py                  # lists available backups
    python scripts/restore.py <filename>        # restores that one
    python scripts/restore.py <filename> --yes  # skips the confirmation prompt

Before overwriting anything, the CURRENT database is itself backed up
first (via backup.py, same retention-pruned backups/ folder) — a restore
is always itself reversible, the same way retry()/resume()/unschedule()
reverse their own forward actions elsewhere in this project.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import get_settings
from scripts.backup import backup


def list_backups(backups_dir: Path) -> list[Path]:
    return sorted(backups_dir.glob("recruitment_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)


def restore(filename: str, skip_confirmation: bool = False) -> Path:
    settings = get_settings()
    if not settings.database_url.startswith("sqlite:///"):
        raise ValueError("restore.py only supports a sqlite:/// DATABASE_URL")
    db_path = Path(settings.database_url[len("sqlite:///") :])

    backups_dir = Path(__file__).resolve().parent.parent / "backups"
    backup_path = (backups_dir / filename).resolve()
    # Defensive path-traversal check — filename is meant to be one of
    # backups/'s own files, not an arbitrary path (this is a locally-run
    # script a trusted user runs directly, but resolving and checking
    # containment costs nothing and rules out a mistyped ../ argument
    # doing something surprising).
    if backups_dir.resolve() not in backup_path.parents:
        raise ValueError(f"{filename} is not inside backups/")
    if not backup_path.exists():
        raise FileNotFoundError(f"No backup found at {backup_path}")

    if not skip_confirmation:
        answer = input(
            f"This will REPLACE the live database at {db_path} with {backup_path.name}. "
            f"Make sure the app is stopped first. Continue? [y/N] "
        )
        if answer.strip().lower() != "y":
            print("Cancelled.")
            sys.exit(1)

    if db_path.exists():
        safety_backup = backup()
        print(f"Backed up the current database to {safety_backup} before restoring.")

    import shutil

    shutil.copy2(backup_path, db_path)
    return db_path


if __name__ == "__main__":
    backups_directory = Path(__file__).resolve().parent.parent / "backups"
    args = sys.argv[1:]
    skip = "--yes" in args
    positional = [a for a in args if a != "--yes"]

    if not positional:
        available = list_backups(backups_directory)
        if not available:
            print(f"No backups found in {backups_directory}. Run backup.py first.")
        else:
            print("Available backups (most recent first):")
            for entry in available:
                print(f"  {entry.name}")
            print("\nUsage: python scripts/restore.py <filename> [--yes]")
        sys.exit(0)

    try:
        restored_path = restore(positional[0], skip_confirmation=skip)
    except (ValueError, FileNotFoundError) as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    print(f"Restored {restored_path} from {positional[0]}")
