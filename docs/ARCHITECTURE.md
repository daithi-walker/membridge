# Architecture

## System diagram

```
Claude Code (any session, any project)
│
├── UserPromptSubmit hook ──────────────────────────────────────────────┐
│   hooks/claude_ui_heartbeat.sh                                        │
│   - Captures session_id, cwd, git branch, iTerm tab name, PID,       │
│     ITERM_SESSION_ID UUID                                              │
│   - Background POST → localhost:7842/api/heartbeat                    │
│                                                                       │
├── PreToolUse hook ─────────────────────────────────────────────────────┤
│   hooks/claude_ui_tool_use.sh                                          │
│   - Background POST → localhost:7842/api/touch                         │
│   - Fires before every tool call - keeps last_seen current during      │
│     long Claude responses (prevents idle drift while working)          │
│                                                                       │
├── Stop hook ────────────────────────────────────────────────────────────┤
│   hooks/claude_ui_stop.sh                                              │
│   - Background POST → localhost:7842/api/stop                          │
│   - Sends session_id + transcript_path; triggers auto-summary          │
│                                                                       │
└── Notification hook ──────────────── localhost:7842 (native, launchd) │
    hooks/claude_ui_notification.sh    FastAPI + SQLite                  │
    - Fires on permission_prompt       (com.daihi.membridge)             │
    - POST → localhost:7842/api/notification                            ▼
                                        ├── /api/heartbeat      → db.upsert_heartbeat()
                                        ├── /api/touch          → db.touch_session()
                                        ├── /api/stop           → db.record_stop()
                                        │                          + async summarise()
                                        ├── /api/notification   → macOS alert (osascript)
                                        ├── /api/sessions       → db.list_sessions()
                                        │                          + PID liveness check
                                        ├── /api/sessions/{id}  PATCH → summary/notes/tags
                                        ├── /api/sessions/{id}/summarise  POST
                                        ├── /api/sessions/{id}/push-summary  POST
                                        ├── /api/sessions/{id}/summaries  GET
                                        ├── /api/focus          POST → iTerm2 focus/resume
                                        └── /api/settings       GET/PATCH


~/.membridge/sessions.db   SQLite (survives reinstalls)
```

## Component responsibilities

### Heartbeat hook (`hooks/claude_ui_heartbeat.sh`)
Fires on every `UserPromptSubmit`. Runs in background (`&`) so Claude is never blocked. Sends `session_id`, `cwd`, `git_branch`, `iterm_tab`, `pid`, `iterm_session_uuid` to the API. Max timeout 3 seconds; silently drops on failure.

### PreToolUse hook (`hooks/claude_ui_tool_use.sh`)
Fires before every tool call. Sends a lightweight touch to keep `last_seen` current during long-running responses - prevents active sessions from drifting to idle while Claude is working.

### Stop hook (`hooks/claude_ui_stop.sh`)
Fires when a Claude session ends. Sends `session_id` and `transcript_path`. The server triggers async summary generation (Claude Haiku) from the transcript. Deduplicates against the last stored summary - same text is silently skipped.

### Notification hook (`hooks/claude_ui_notification.sh`)
Fires on `permission_prompt` events. POSTs to `/api/notification`, which calls `osascript` to fire a macOS notification banner so you know a session needs attention.

### FastAPI server (`membridge/server.py`)
Runs natively on the host via launchd (`com.daihi.membridge`), port 7842. Handles all API routes. Imports `focus.py` directly for all macOS operations - no separate process or HTTP hop.

### Focus module (`membridge/focus.py`)
All osascript and iTerm2 logic: focus a tab by UUID or TTY, rename a tab, check PID liveness, list sessions. Called directly from `server.py` as a Python import.

### SQLite (`membridge/db.py`)
Two tables: `sessions` and `session_summaries`. Migrations applied on startup via `_MIGRATIONS` list (idempotent). DB lives at `~/.membridge/sessions.db`.

### Dashboard (`membridge/static/`)
Vanilla JS, no build step. Editable install (`uv pip install -e .`) means static file changes are live on browser refresh. Receives live updates via SSE (`EventSource` → `/api/stream`). Side panel shows full session metadata, editable summary, notes, linked sessions, and summary history.

## Data model

```sql
sessions (
  session_id          TEXT PRIMARY KEY,  -- Claude's session UUID
  cwd                 TEXT,              -- Working directory
  project_name        TEXT,              -- Last segment of cwd
  git_branch          TEXT,              -- Branch at last heartbeat
  iterm_tab           TEXT,              -- iTerm tab name or auto-detected
  iterm_session_uuid  TEXT,              -- UUID from $ITERM_SESSION_ID (stable per tab)
  pid                 INTEGER,           -- Claude process PID
  first_seen          TEXT,              -- ISO8601 UTC
  last_seen           TEXT,              -- ISO8601 UTC (updated on heartbeat/touch)
  last_stop_reason    TEXT,              -- From Stop hook
  summary             TEXT,              -- Current summary (auto or user-edited)
  summary_source      TEXT,              -- 'auto' | 'user' | 'skill' | 'backfill'
  prompt_count        INTEGER,           -- Incremented on each heartbeat
  notes               TEXT,             -- Freeform work log (side panel)
  starred             INTEGER DEFAULT 0, -- Pinned to top of dashboard
  archived            INTEGER DEFAULT 0  -- Hidden from default view
)

session_summaries (
  id          INTEGER PRIMARY KEY,
  session_id  TEXT,       -- FK → sessions.session_id
  source      TEXT,       -- 'auto' | 'skill' | 'user'
  text        TEXT,       -- Summary content
  created_at  TEXT        -- ISO8601 UTC
)
-- Append-only log. Never overwrites. Full history per session.

settings (
  key    TEXT PRIMARY KEY,
  value  TEXT
)
-- Keys: active_threshold_secs (300), idle_threshold_secs (7200),
--       refresh_interval_secs (30), ticket_base_url ('')
```

## Status computation

| Status | Condition |
|--------|-----------|
| active | `last_seen` < `active_threshold_secs` ago |
| idle   | `last_seen` between active and `idle_threshold_secs`, or PID still alive |
| stale  | `last_seen` > `idle_threshold_secs` ago **and** PID is dead |

Thresholds are user-configurable via the Settings modal. Status is computed at query time in `server.py` using a direct `os.kill(pid, 0)` liveness check via `focus.py`.

## Why native, not Docker?

`osascript` and `os.kill` are macOS host operations - they cannot run inside a Linux container. MemBridge's core value (focus the right iTerm2 tab, rename it, fire a notification, check if a PID is alive) requires direct access to the macOS window server and process table. A containerised process has neither. Running natively under launchd also removes Docker as a dependency and gives a simpler one-process, one-plist, one-log-file setup.
