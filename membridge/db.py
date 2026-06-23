import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

DB_PATH = Path(os.getenv("MEMBRIDGE_DB", Path.home() / ".membridge" / "sessions.db"))

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    cwd             TEXT NOT NULL,
    project_name    TEXT NOT NULL,
    git_branch      TEXT,
    iterm_tab       TEXT,
    pid             INTEGER,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    last_stop_reason TEXT,
    description     TEXT,
    prompt_count    INTEGER NOT NULL DEFAULT 0,
    notes           TEXT
);
"""

_SUMMARIES_SQL = """
CREATE TABLE IF NOT EXISTS session_summaries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    source      TEXT NOT NULL,
    text        TEXT NOT NULL,
    file_path   TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
"""

_SETTINGS_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_SETTINGS_DEFAULTS = {
    "active_threshold_secs": "300",    # 5 min
    "idle_threshold_secs":   "7200",   # 2 h
    "refresh_interval_secs": "30",
}

_MIGRATIONS = [
    "ALTER TABLE sessions ADD COLUMN pid INTEGER;",
    "ALTER TABLE sessions ADD COLUMN notes TEXT;",
    "ALTER TABLE sessions ADD COLUMN iterm_session_uuid TEXT;",
    # Rename summary → description (SQLite lacks RENAME COLUMN before 3.25; use ADD + copy)
    "ALTER TABLE sessions ADD COLUMN description TEXT;",
    "UPDATE sessions SET description = summary WHERE description IS NULL AND summary IS NOT NULL;",
    # summary_source column is obsolete — SQLite can't DROP columns cleanly, just leave it
    "ALTER TABLE sessions ADD COLUMN archived INTEGER NOT NULL DEFAULT 0;",
    "ALTER TABLE sessions ADD COLUMN tickets TEXT;",
    "ALTER TABLE sessions ADD COLUMN starred INTEGER NOT NULL DEFAULT 0;",
    "ALTER TABLE sessions ADD COLUMN awaiting_input INTEGER NOT NULL DEFAULT 0;",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.execute(_CREATE_SQL)
        conn.execute(_SUMMARIES_SQL)
        conn.execute(_SETTINGS_SQL)
        for sql in _MIGRATIONS:
            try:
                conn.execute(sql)
            except Exception:
                pass
        for k, v in _SETTINGS_DEFAULTS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


class UpsertResult:
    def __init__(self, is_new: bool, uuid_changed: bool, stored_tab_name: str | None):
        self.is_new = is_new
        self.uuid_changed = uuid_changed
        self.stored_tab_name = stored_tab_name  # canonical name to restore on resume


def upsert_heartbeat(
    session_id: str,
    cwd: str,
    branch: str | None,
    iterm_tab: str | None,
    pid: int | None = None,
    iterm_session_uuid: str | None = None,
) -> UpsertResult:
    # Resolve symlinks so paths from machines with symlinked home dirs
    # (e.g. /Users/david/walker vs /Users/david.walker) normalise to the same path.
    try:
        cwd = str(Path(cwd).resolve())
    except Exception:
        pass
    project_name = Path(cwd).name
    now = _now()
    with _conn() as conn:
        existing = conn.execute(
            "SELECT iterm_session_uuid, iterm_tab FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        if existing:
            stored_uuid, stored_tab = existing[0], existing[1]
            # UUID changed = resumed into a new iTerm tab
            uuid_changed = bool(
                iterm_session_uuid and stored_uuid and iterm_session_uuid != stored_uuid
            )
            conn.execute(
                """UPDATE sessions
                   SET last_seen = ?,
                       prompt_count = prompt_count + 1,
                       awaiting_input = 0,
                       git_branch = COALESCE(?, git_branch),
                       iterm_tab = COALESCE(?, iterm_tab),
                       pid = COALESCE(?, pid),
                       iterm_session_uuid = COALESCE(?, iterm_session_uuid)
                   WHERE session_id = ?""",
                (now, branch or None, iterm_tab or None, pid, iterm_session_uuid or None, session_id),
            )
            return UpsertResult(is_new=False, uuid_changed=uuid_changed, stored_tab_name=stored_tab)
        else:
            conn.execute(
                """INSERT INTO sessions
                   (session_id, cwd, project_name, git_branch, iterm_tab, pid,
                    iterm_session_uuid, first_seen, last_seen, prompt_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (session_id, cwd, project_name, branch or None, iterm_tab or None, pid,
                 iterm_session_uuid or None, now, now),
            )
            return UpsertResult(is_new=True, uuid_changed=False, stored_tab_name=None)


def record_stop(session_id: str, stop_reason: str) -> bool:
    """Set awaiting_input=1. Returns True if session was already awaiting (no transition)."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT awaiting_input FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        was_awaiting = bool(row and row[0])
        conn.execute(
            "UPDATE sessions SET last_stop_reason = ?, awaiting_input = 1 WHERE session_id = ?",
            (stop_reason, session_id),
        )
    return was_awaiting


def add_summary(
    session_id: str,
    text: str,
    source: str = "auto",
    file_path: str | None = None,
) -> int:
    """Append a new entry to session_summaries. Only auto-source updates sessions.description."""
    now = _now()
    with _conn() as conn:
        cursor = conn.execute(
            """INSERT INTO session_summaries (session_id, created_at, source, text, file_path)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, now, source, text, file_path),
        )
        row_id = cursor.lastrowid
        if source == "auto":
            conn.execute(
                "UPDATE sessions SET description = ? WHERE session_id = ?",
                (text, session_id),
            )
    return row_id


def get_summaries(session_id: str) -> list[dict]:
    """Return all summary entries for a session, newest first."""
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, session_id, created_at, source, text, file_path
               FROM session_summaries
               WHERE session_id = ?
               ORDER BY created_at DESC""",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def summary_file_already_ingested(file_path: str) -> bool:
    """True if this file_path has already been stored in session_summaries."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM session_summaries WHERE file_path = ?", (file_path,)
        ).fetchone()
    return row is not None


def last_auto_summary_text(session_id: str) -> str | None:
    """Return the text of the most recent auto-source summary for this session, or None."""
    with _conn() as conn:
        row = conn.execute(
            """SELECT text FROM session_summaries
               WHERE session_id = ? AND source = 'auto'
               ORDER BY created_at DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
    return row[0] if row else None


def update_description(session_id: str, description: str) -> None:
    """Legacy: update sessions.description only (no history row). Kept for backfill compat."""
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET description = ? WHERE session_id = ?",
            (description, session_id),
        )


def touch_session(session_id: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET last_seen = ? WHERE session_id = ?",
            (_now(), session_id),
        )


def delete_session(session_id: str) -> None:
    with _conn() as conn:
        # CASCADE deletes session_summaries rows too
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


def update_notes(session_id: str, notes: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET notes = ? WHERE session_id = ?",
            (notes, session_id),
        )


def set_archived(session_id: str, archived: bool) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET archived = ? WHERE session_id = ?",
            (1 if archived else 0, session_id),
        )


def set_starred(session_id: str, starred: bool) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET starred = ? WHERE session_id = ?",
            (1 if starred else 0, session_id),
        )


def update_tickets(session_id: str, tickets: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET tickets = ? WHERE session_id = ?",
            (tickets, session_id),
        )


def get_session(session_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def list_sessions(include_stale: bool = True) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY last_seen DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_settings() -> dict:
    with _conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    result = dict(_SETTINGS_DEFAULTS)
    result.update({r["key"]: r["value"] for r in rows})
    return {k: int(v) for k, v in result.items()}


def update_settings(updates: dict) -> dict:
    allowed = set(_SETTINGS_DEFAULTS.keys())
    with _conn() as conn:
        for k, v in updates.items():
            if k in allowed:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (k, str(int(v))),
                )
    return get_settings()
