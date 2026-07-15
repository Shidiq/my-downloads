import datetime as dt
import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    relpath TEXT UNIQUE NOT NULL,
    kind TEXT NOT NULL DEFAULT 'file',
    category TEXT,
    ext TEXT,
    size INTEGER,
    mtime REAL,
    added_at TEXT,
    sha256 TEXT,
    missing INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_files_category ON files(category);
CREATE INDEX IF NOT EXISTS idx_files_size ON files(size);
CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    config.ensure_dirs()
    with connect() as conn:
        conn.executescript(SCHEMA)


def backup_db() -> None:
    """Copy downloads.db to backups/ via the sqlite online backup API, keep newest N."""
    if not config.DB_PATH.exists():
        return
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_path = config.BACKUP_DIR / f"downloads-{stamp}.db"
    src = sqlite3.connect(config.DB_PATH)
    dest = sqlite3.connect(dest_path)
    try:
        src.backup(dest)
    finally:
        dest.close()
        src.close()
    backups = sorted(config.BACKUP_DIR.glob("downloads-*.db"))
    for old in backups[: -config.BACKUPS_TO_KEEP]:
        old.unlink()


def duplicate_group_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM (SELECT sha256 FROM files "
        "WHERE kind = 'file' AND missing = 0 AND sha256 IS NOT NULL "
        "GROUP BY sha256 HAVING COUNT(*) >= 2)"
    ).fetchone()
    return row["n"]
