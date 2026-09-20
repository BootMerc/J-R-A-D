"""Phase 12 tests for scripts/backup.py and scripts/restore.py. Uses a
real temp SQLite file and real file copies throughout — no mocking, since
this is plain file I/O with no network/OS-integration surface worth
mocking (same reasoning as Phase 9's visual generator tests).
"""

import time

import pytest

from scripts.backup import _prune_old_backups, backup
from scripts.restore import restore


@pytest.fixture()
def isolated_db(monkeypatch, tmp_path):
    """A real SQLite file at a temp path, isolated backups/ dir next to
    it — mirrors how the actual project lays out data/ and backups/ as
    siblings, without touching the real project folders.

    backup.py/restore.py derive backups/'s location from their own
    __file__ (Path(__file__).resolve().parent.parent / "backups"), not
    from an env var or the working directory — patching each module's
    __file__ to a path under tmp_path is what redirects that
    computation into the isolated fixture directory instead of the real
    project's backups/.
    """
    db_path = tmp_path / "data" / "recruitment.db"
    db_path.parent.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    from app.config.settings import get_settings

    get_settings.cache_clear()

    from app.database.database import get_engine, init_db

    get_engine.cache_clear()
    init_db()

    import scripts.backup
    import scripts.restore

    (tmp_path / "scripts").mkdir(exist_ok=True)
    monkeypatch.setattr(scripts.backup, "__file__", str(tmp_path / "scripts" / "backup.py"))
    monkeypatch.setattr(scripts.restore, "__file__", str(tmp_path / "scripts" / "restore.py"))

    backups_dir = tmp_path / "backups"
    yield db_path, backups_dir

    get_settings.cache_clear()
    get_engine.cache_clear()


def _add_marker_row(db_path, title):
    from app.database.database import Base
    from app.database.enums import JobStatus
    from app.database.models import Job
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{db_path}")
    session = sessionmaker(bind=engine)()
    session.add(Job(title=title, status=JobStatus.DRAFT))
    session.commit()
    session.close()
    engine.dispose()


def _read_titles(db_path):
    from app.database.models import Job
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{db_path}")
    session = sessionmaker(bind=engine)()
    titles = [j.title for j in session.query(Job).all()]
    session.close()
    engine.dispose()
    return titles


def test_backup_creates_a_timestamped_copy(isolated_db):
    db_path, backups_dir = isolated_db
    _add_marker_row(db_path, "Original Job")

    result = backup()

    assert result.exists()
    assert result.parent == backups_dir
    assert _read_titles(result) == ["Original Job"]


def test_backup_raises_when_no_database_exists(isolated_db, monkeypatch):
    db_path, _ = isolated_db
    db_path.unlink()

    with pytest.raises(FileNotFoundError):
        backup()


def test_prune_old_backups_keeps_only_the_most_recent(isolated_db):
    _, backups_dir = isolated_db
    backups_dir.mkdir(exist_ok=True)
    for i in range(5):
        (backups_dir / f"recruitment_{i:02d}.db").write_text("x")
        time.sleep(0.01)

    _prune_old_backups(backups_dir, retention=2)

    remaining = sorted(backups_dir.glob("recruitment_*.db"))
    assert len(remaining) == 2
    # The two most recently-modified files survive.
    assert {p.name for p in remaining} == {"recruitment_03.db", "recruitment_04.db"}


def test_unique_backup_path_avoids_existing_filename(isolated_db):
    """Regression test for a real bug: two backups within the same
    second (exactly what restore()'s own safety-backup step can trigger
    right after a manual backup) must not collide on the same filename
    and silently overwrite each other — see backup.py's
    _unique_backup_path docstring."""
    from scripts.backup import _unique_backup_path

    _, backups_dir = isolated_db
    backups_dir.mkdir(exist_ok=True)

    first = _unique_backup_path(backups_dir)
    first.write_text("first backup's content")

    # Simulates a second call landing on the exact same second-precision
    # timestamp — must not resolve to the same, already-occupied path.
    second = _unique_backup_path(backups_dir)

    assert second != first
    assert not second.exists()
    assert first.read_text() == "first backup's content"  # untouched


def test_backup_called_twice_quickly_produces_two_distinct_files(isolated_db):
    """The actual end-to-end scenario the bug came from: backup() called
    twice in immediate succession (as restore()'s safety-backup step
    does right after an initial manual backup) must produce two
    independently-readable files, not one overwriting the other."""
    db_path, backups_dir = isolated_db
    _add_marker_row(db_path, "First")
    first = backup()

    _add_marker_row(db_path, "Second")
    second = backup()

    assert first != second
    assert _read_titles(first) == ["First"]
    assert _read_titles(second) == ["First", "Second"]


def test_restore_replaces_the_live_database(isolated_db):
    db_path, backups_dir = isolated_db
    _add_marker_row(db_path, "Before backup")
    backup_path = backup()

    _add_marker_row(db_path, "After backup, before restore")
    assert set(_read_titles(db_path)) == {"Before backup", "After backup, before restore"}

    restore(backup_path.name, skip_confirmation=True)

    assert _read_titles(db_path) == ["Before backup"]


def test_restore_creates_a_safety_backup_of_current_state_first(isolated_db):
    db_path, backups_dir = isolated_db
    _add_marker_row(db_path, "Original")
    first_backup = backup()

    _add_marker_row(db_path, "Changed before restore")
    backups_before = set(backups_dir.glob("recruitment_*.db"))

    restore(first_backup.name, skip_confirmation=True)

    backups_after = set(backups_dir.glob("recruitment_*.db"))
    new_backups = backups_after - backups_before
    assert len(new_backups) == 1  # the safety backup taken just before restoring
    assert _read_titles(list(new_backups)[0]) == ["Original", "Changed before restore"]


def test_restore_rejects_path_traversal(isolated_db):
    with pytest.raises(ValueError, match="not inside backups"):
        restore("../../etc/passwd", skip_confirmation=True)


def test_restore_rejects_missing_backup(isolated_db):
    with pytest.raises(FileNotFoundError):
        restore("recruitment_does_not_exist.db", skip_confirmation=True)
