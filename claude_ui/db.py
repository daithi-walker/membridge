import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

DB_PATH = Path(os.getenv("CLAUDE_UI_DB", Path.home() / ".claude-ui" / "sessions.db"))

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    cwd             TEXT NOT NULL,
    project_name    TEXT NOT NULL,
    git_branch      TEXT,
    iterm_tab       TEXT,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    last_stop_reason TEXT,
    summary         TEXT,
    summary_source  TEXT DEFAULT 'auto',
    prompt_count    INTEGER NOT NULL DEFAULT 0
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.execute(_CREATE_SQL)


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
) -> None:
    project_name = Path(cwd).name
    now = _now()
    with _conn() as conn:
        existing = conn.execute(
            "SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE sessions
                   SET last_seen = ?,
                       prompt_count = prompt_count + 1,
                       git_branch = COALESCE(?, git_branch),
                       iterm_tab = COALESCE(?, iterm_tab)
                   WHERE session_id = ?""",
                (now, branch or None, iterm_tab or None, session_id),
            )
        else:
            conn.execute(
                """INSERT INTO sessions
                   (session_id, cwd, project_name, git_branch, iterm_tab,
                    first_seen, last_seen, prompt_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                (session_id, cwd, project_name, branch or None, iterm_tab or None, now, now),
            )


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
