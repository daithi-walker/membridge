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
    summary         TEXT,
    summary_source  TEXT DEFAULT 'auto',
    prompt_count    INTEGER NOT NULL DEFAULT 0,
    notes           TEXT
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
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.execute(_CREATE_SQL)
        conn.execute(_SETTINGS_SQL)
        for sql in _MIGRATIONS:
            try:
                conn.execute(sql)
            except Exception:
                pass
        # Seed defaults (INSERT OR IGNORE — never overwrite user values)
        for k, v in _SETTINGS_DEFAULTS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_heartbeat(
    session_id: str,
    cwd: str,
    branch: str | None,
    iterm_tab: str | None,
    pid: int | None = None,
    iterm_session_uuid: str | None = None,
) -> bool:
    """Returns True if this is a new session, False if existing."""
    project_name = Path(cwd).name
    now = _now()
    with _conn() as conn:
        existing = conn.execute(
            "SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if existing:
            # Only update iterm_tab from heartbeat if the session has no UUID yet
            # (once sync_iterm_tabs.py has run and stored a UUID, the alias is
            # authoritative and heartbeat osascript names should not overwrite it)
            uuid_known = conn.execute(
                "SELECT iterm_session_uuid FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()[0]
            tab_update = iterm_tab if not uuid_known else None
            conn.execute(
                """UPDATE sessions
                   SET last_seen = ?,
                       prompt_count = prompt_count + 1,
                       git_branch = COALESCE(?, git_branch),
                       iterm_tab = COALESCE(?, iterm_tab),
                       pid = COALESCE(?, pid),
                       iterm_session_uuid = COALESCE(?, iterm_session_uuid)
                   WHERE session_id = ?""",
                (now, branch or None, tab_update or None, pid, iterm_session_uuid or None, session_id),
            )
            return False
        else:
            conn.execute(
                """INSERT INTO sessions
                   (session_id, cwd, project_name, git_branch, iterm_tab, pid,
                    iterm_session_uuid, first_seen, last_seen, prompt_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (session_id, cwd, project_name, branch or None, iterm_tab or None, pid,
                 iterm_session_uuid or None, now, now),
            )
            return True


def record_stop(session_id: str, stop_reason: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET last_stop_reason = ? WHERE session_id = ?",
            (stop_reason, session_id),
        )


def update_summary(session_id: str, summary: str, source: str = "auto") -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET summary = ?, summary_source = ? WHERE session_id = ?",
            (summary, source, session_id),
        )


def touch_session(session_id: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET last_seen = ? WHERE session_id = ?",
            (_now(), session_id),
        )


def delete_session(session_id: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


def update_notes(session_id: str, notes: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET notes = ? WHERE session_id = ?",
            (notes, session_id),
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
    result = dict(_SETTINGS_DEFAULTS)  # start with defaults
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
