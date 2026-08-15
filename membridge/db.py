import logging
import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast

logger = logging.getLogger(__name__)


class SessionRow(TypedDict, total=False):
    session_id: str
    cwd: str
    project_name: str
    git_branch: str | None
    iterm_tab: str | None
    iterm_session_uuid: str | None
    pid: int | None
    first_seen: str
    last_seen: str
    last_stop_reason: str | None
    description: str | None
    prompt_count: int
    notes: str | None
    archived: int
    tickets: str | None
    starred: int
    awaiting_input: int
    working: int


class LinkedSession(TypedDict):
    session_id: str
    project_name: str
    git_branch: str | None
    description: str | None
    last_seen: str


class SessionTag(TypedDict):
    tag: str
    weight: float

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

_LINKS_SQL = """
CREATE TABLE IF NOT EXISTS session_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_a   TEXT NOT NULL,
    session_b   TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (session_a) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (session_b) REFERENCES sessions(session_id) ON DELETE CASCADE,
    UNIQUE (session_a, session_b)
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

_ACTIVITY_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS activity_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    project_name    TEXT NOT NULL,
    cwd             TEXT NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('prompt', 'stop')),
    stop_reason     TEXT,
    text            TEXT,
    transcript_path TEXT,
    ts              TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
"""

_ACTIVITY_EVENTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_activity_events_ts ON activity_events (ts);
"""

_ACTIVITY_EVENTS_KIND_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_activity_events_kind_ts ON activity_events (kind, ts);
"""

# Domain-neutral: a session carries zero or more free-text `tag`s, each with a
# `weight` used to split that session's active time across its tags. MemBridge
# knows nothing about what a tag means — a downstream consumer (e.g. a timesheet
# tool) owns any mapping from tag -> external code. Never put consumer vocabulary
# (project codes, client names, timesheet fields) in this table.
_TAGS_SQL = """
CREATE TABLE IF NOT EXISTS session_tags (
    session_id  TEXT NOT NULL,
    tag         TEXT NOT NULL,
    weight      REAL NOT NULL DEFAULT 1.0,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (session_id, tag),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
"""

_TAGS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_session_tags_tag ON session_tags (tag);
"""


def _migrate_legacy_event_tables(conn: sqlite3.Connection) -> None:
    """One-time forward migration from the short-lived heartbeat_events/stop_events
    tables into the unified activity_events table. No-ops once both are gone."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "heartbeat_events" in tables:
        conn.execute(
            """INSERT INTO activity_events (session_id, project_name, cwd, kind, stop_reason, ts)
               SELECT session_id, project_name, cwd, 'prompt', NULL, ts FROM heartbeat_events"""
        )
        conn.execute("DROP TABLE heartbeat_events")
    if "stop_events" in tables:
        conn.execute(
            """INSERT INTO activity_events (session_id, project_name, cwd, kind, stop_reason, ts)
               SELECT session_id, project_name, cwd, 'stop', stop_reason, ts FROM stop_events"""
        )
        conn.execute("DROP TABLE stop_events")

_SETTINGS_DEFAULTS = {
    "active_threshold_secs": "300",    # 5 min
    "idle_threshold_secs":   "7200",   # 2 h
    "refresh_interval_secs": "30",
    "notif_popup":           "1",
    "notif_sound":           "0",      # off by default
    "ticket_base_url":       "",       # e.g. https://jira.example.com/browse/
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
    # working = Claude is processing this turn (set on prompt/tool-start, cleared on stop).
    # Lets status show "active" during long single tool calls where last_seen goes stale.
    "ALTER TABLE sessions ADD COLUMN working INTEGER NOT NULL DEFAULT 0;",
    "ALTER TABLE activity_events ADD COLUMN text TEXT;",
    "ALTER TABLE activity_events ADD COLUMN transcript_path TEXT;",
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.execute(_CREATE_SQL)
        conn.execute(_LINKS_SQL)
        conn.execute(_SUMMARIES_SQL)
        conn.execute(_SETTINGS_SQL)
        conn.execute(_ACTIVITY_EVENTS_SQL)
        conn.execute(_ACTIVITY_EVENTS_INDEX_SQL)
        conn.execute(_ACTIVITY_EVENTS_KIND_INDEX_SQL)
        conn.execute(_TAGS_SQL)
        conn.execute(_TAGS_INDEX_SQL)
        _migrate_legacy_event_tables(conn)
        for sql in _MIGRATIONS:
            try:
                conn.execute(sql)
            except Exception as e:
                logger.debug("Migration skipped (already applied?): %s — %s", sql.split("\n")[0][:60], e)
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
    prompt: str | None = None,
    transcript_path: str | None = None,
) -> UpsertResult:
    # Resolve symlinks so paths from machines with symlinked home dirs
    # (e.g. /Users/jane/doe vs /Users/jane.doe) normalise to the same path.
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
                       working = 1,
                       git_branch = COALESCE(?, git_branch),
                       iterm_tab = COALESCE(?, iterm_tab),
                       pid = COALESCE(?, pid),
                       iterm_session_uuid = COALESCE(?, iterm_session_uuid)
                   WHERE session_id = ?""",
                (now, branch or None, iterm_tab or None, pid, iterm_session_uuid or None, session_id),
            )
            result = UpsertResult(is_new=False, uuid_changed=uuid_changed, stored_tab_name=stored_tab)
        else:
            conn.execute(
                """INSERT INTO sessions
                   (session_id, cwd, project_name, git_branch, iterm_tab, pid,
                    iterm_session_uuid, first_seen, last_seen, prompt_count, working)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)""",
                (session_id, cwd, project_name, branch or None, iterm_tab or None, pid,
                 iterm_session_uuid or None, now, now),
            )
            result = UpsertResult(is_new=True, uuid_changed=False, stored_tab_name=None)

        # Append-only event per prompt, recorded after the sessions row is guaranteed
        # to exist (FK) — first_seen/last_seen on `sessions` only ever keep the two
        # endpoints, so this is the only place a mid-session gap survives.
        conn.execute(
            """INSERT INTO activity_events
                   (session_id, project_name, cwd, kind, stop_reason, text, transcript_path, ts)
               VALUES (?, ?, ?, 'prompt', NULL, ?, ?, ?)""",
            (session_id, project_name, cwd, prompt or None, transcript_path or None, now),
        )
        return result


def record_stop(
    session_id: str,
    stop_reason: str,
    last_assistant_message: str | None = None,
    transcript_path: str | None = None,
) -> bool:
    """Set awaiting_input=1. Returns True if session was already awaiting (no transition).

    If stop_reason is empty and awaiting_input is already set (Notification hook fired first),
    preserve the existing last_stop_reason so the UI icon isn't downgraded to the default ✎.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT awaiting_input, cwd, project_name FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        was_awaiting = bool(row and row[0])
        if not stop_reason and was_awaiting:
            # Notification hook already set a meaningful reason — don't overwrite with ""
            conn.execute(
                "UPDATE sessions SET awaiting_input = 1, working = 0 WHERE session_id = ?",
                (session_id,),
            )
        else:
            conn.execute(
                "UPDATE sessions SET last_stop_reason = ?, awaiting_input = 1, working = 0 WHERE session_id = ?",
                (stop_reason, session_id),
            )
        # Append-only event, mirroring heartbeat_events — lets a report correlate
        # "prompt submitted" -> "Claude stopped" (active work) vs "Claude stopped"
        # -> "next prompt" (idle/reading/away, ambiguous but a useful heuristic).
        if row:
            conn.execute(
                """INSERT INTO activity_events
                       (session_id, project_name, cwd, kind, stop_reason, text, transcript_path, ts)
                   VALUES (?, ?, ?, 'stop', ?, ?, ?, ?)""",
                (session_id, row["project_name"], row["cwd"], stop_reason or None,
                 last_assistant_message or None, transcript_path or None, _now()),
            )
    return was_awaiting


def add_summary(
    session_id: str,
    text: str,
    source: str = "auto",
    file_path: str | None = None,
) -> int | None:
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


def touch_session(session_id: str, working: bool = False) -> None:
    """Bump last_seen. When working=True (a tool is starting), also mark the session
    as processing so status stays 'active' through long single tool calls. A falsy
    working leaves the flag untouched — only stop/notification clears it."""
    if working:
        with _conn() as conn:
            conn.execute(
                "UPDATE sessions SET last_seen = ?, awaiting_input = 0, working = 1 WHERE session_id = ?",
                (_now(), session_id),
            )
    else:
        with _conn() as conn:
            conn.execute(
                "UPDATE sessions SET last_seen = ?, awaiting_input = 0 WHERE session_id = ?",
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


def add_link(a: str, b: str) -> bool:
    """Link two sessions. Stored canonically (a < b). Returns True if inserted, False if duplicate."""
    if a == b:
        return False
    pair = (min(a, b), max(a, b))
    with _conn() as conn:
        try:
            conn.execute(
                "INSERT INTO session_links (session_a, session_b, created_at) VALUES (?, ?, ?)",
                (*pair, _now()),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def remove_link(a: str, b: str) -> bool:
    """Remove a link. Returns True if deleted, False if not found."""
    pair = (min(a, b), max(a, b))
    with _conn() as conn:
        cursor = conn.execute(
            "DELETE FROM session_links WHERE session_a = ? AND session_b = ?", pair
        )
        return cursor.rowcount > 0


def get_links(session_id: str) -> list[LinkedSession]:
    """Return all sessions linked to session_id with basic metadata."""
    with _conn() as conn:
        rows = conn.execute(
            """SELECT s.session_id, s.project_name, s.git_branch, s.description, s.last_seen
               FROM session_links l
               JOIN sessions s ON (
                   CASE WHEN l.session_a = ? THEN l.session_b ELSE l.session_a END = s.session_id
               )
               WHERE l.session_a = ? OR l.session_b = ?
               ORDER BY s.last_seen DESC""",
            (session_id, session_id, session_id),
        ).fetchall()
    return [cast(LinkedSession, dict(r)) for r in rows]


def get_session_tags(session_id: str) -> list[SessionTag]:
    """Tags on a session, alphabetical. Each carries a weight for time-splitting."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT tag, weight FROM session_tags WHERE session_id = ? ORDER BY tag",
            (session_id,),
        ).fetchall()
    return [cast(SessionTag, {"tag": r["tag"], "weight": r["weight"]}) for r in rows]


def add_session_tag(session_id: str, tag: str, weight: float = 1.0) -> bool:
    """Add or re-weight one tag on a session. Returns False if the tag is blank."""
    tag = tag.strip()
    if not tag:
        return False
    with _conn() as conn:
        conn.execute(
            """INSERT INTO session_tags (session_id, tag, weight, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (session_id, tag) DO UPDATE SET weight = excluded.weight""",
            (session_id, tag, float(weight), _now()),
        )
    return True


def remove_session_tag(session_id: str, tag: str) -> bool:
    """Remove one tag from a session. Returns True if a row was deleted."""
    with _conn() as conn:
        cursor = conn.execute(
            "DELETE FROM session_tags WHERE session_id = ? AND tag = ?",
            (session_id, tag.strip()),
        )
        return cursor.rowcount > 0


def set_session_tags(session_id: str, tags: list[dict] | dict) -> list[SessionTag]:
    """Replace a session's entire tag set (the retroactive-edit primitive the UI uses).

    `tags` is either a list of ``{"tag", "weight"}`` dicts or a ``{tag: weight}``
    mapping. Blank tags are dropped; a repeated tag keeps its last weight; a
    non-numeric weight falls back to 1.0. Returns the resulting tag set."""
    items = tags.items() if isinstance(tags, dict) else (
        (t.get("tag", ""), t.get("weight", 1.0)) for t in tags
    )
    desired: dict[str, float] = {}
    for tag, weight in items:
        tag = (tag or "").strip()
        if not tag:
            continue
        try:
            desired[tag] = float(weight)
        except (TypeError, ValueError):
            desired[tag] = 1.0
    now = _now()
    with _conn() as conn:
        conn.execute("DELETE FROM session_tags WHERE session_id = ?", (session_id,))
        for tag, weight in desired.items():
            conn.execute(
                """INSERT INTO session_tags (session_id, tag, weight, created_at)
                   VALUES (?, ?, ?, ?)""",
                (session_id, tag, weight, now),
            )
    return [cast(SessionTag, {"tag": t, "weight": w}) for t, w in desired.items()]


def list_all_tags() -> list[str]:
    """Distinct tags across all sessions, most-used first (for autocomplete)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT tag, COUNT(*) AS n FROM session_tags GROUP BY tag ORDER BY n DESC, tag ASC"
        ).fetchall()
    return [r["tag"] for r in rows]


def get_tags_for_sessions(session_ids: list[str]) -> dict[str, list[SessionTag]]:
    """Bulk-fetch tags for many sessions -> {session_id: [SessionTag, ...]}."""
    if not session_ids:
        return {}
    placeholders = ",".join("?" * len(session_ids))
    with _conn() as conn:
        rows = conn.execute(
            f"""SELECT session_id, tag, weight FROM session_tags
                WHERE session_id IN ({placeholders}) ORDER BY tag""",
            session_ids,
        ).fetchall()
    out: dict[str, list[SessionTag]] = {}
    for r in rows:
        out.setdefault(r["session_id"], []).append(
            cast(SessionTag, {"tag": r["tag"], "weight": r["weight"]})
        )
    return out


def get_session(session_id: str) -> SessionRow | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    return SessionRow(**dict(row)) if row else None


def list_sessions(include_stale: bool = True) -> list[SessionRow]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY last_seen DESC"
        ).fetchall()
        link_rows = conn.execute(
            "SELECT session_a, session_b FROM session_links"
        ).fetchall()
        tag_rows = conn.execute(
            "SELECT session_id, tag, weight FROM session_tags ORDER BY tag"
        ).fetchall()
    # Build a map: session_id -> [linked_ids]
    link_map: dict[str, list[str]] = {}
    for lr in link_rows:
        a, b = lr["session_a"], lr["session_b"]
        link_map.setdefault(a, []).append(b)
        link_map.setdefault(b, []).append(a)
    # Build a map: session_id -> [SessionTag]
    tag_map: dict[str, list[SessionTag]] = {}
    for tr in tag_rows:
        tag_map.setdefault(tr["session_id"], []).append(
            cast(SessionTag, {"tag": tr["tag"], "weight": tr["weight"]})
        )
    result = []
    for r in rows:
        row = SessionRow(**dict(r))
        row["linked_session_ids"] = link_map.get(r["session_id"], [])  # type: ignore[typeddict-unknown-key]
        row["tags"] = tag_map.get(r["session_id"], [])  # type: ignore[typeddict-unknown-key]
        result.append(row)
    return result


def get_activity_events(
    project_name: str | None = None,
    since: str | None = None,
    until: str | None = None,
    kind: str | None = None,
) -> list[dict]:
    """Raw activity events (kind='prompt' on UserPromptSubmit, kind='stop' when
    Claude finishes a turn), oldest first, one interleaved timeline per client.
    `since`/`until` are ISO-8601 strings (UTC, matching `_now()`'s format) and are
    inclusive/exclusive-safe via string comparison since ISO-8601 sorts
    lexicographically. Pass `kind` to filter to just 'prompt' or just 'stop'."""
    clauses = []
    params: list[str] = []
    if project_name:
        clauses.append("project_name = ?")
        params.append(project_name)
    if since:
        clauses.append("ts >= ?")
        params.append(since)
    if until:
        clauses.append("ts <= ?")
        params.append(until)
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _conn() as conn:
        rows = conn.execute(
            f"""SELECT session_id, project_name, cwd, kind, stop_reason, text, transcript_path, ts
                FROM activity_events {where} ORDER BY ts ASC""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_settings() -> dict:
    with _conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    result = dict(_SETTINGS_DEFAULTS)
    result.update({r["key"]: r["value"] for r in rows})
    # Cast each value to match the type of its default; string defaults stay as strings
    return {k: (int(v) if isinstance(_SETTINGS_DEFAULTS.get(k), str) and _SETTINGS_DEFAULTS[k].lstrip("-").isdigit() else v) for k, v in result.items()}


def update_settings(updates: dict) -> dict:
    allowed = set(_SETTINGS_DEFAULTS.keys())
    with _conn() as conn:
        for k, v in updates.items():
            if k not in allowed:
                continue
            # Store numeric defaults as ints; string defaults (e.g. ticket_base_url) as-is
            default = _SETTINGS_DEFAULTS[k]
            stored = str(int(v)) if default.lstrip("-").isdigit() else str(v)
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (k, stored),
            )
    return get_settings()
