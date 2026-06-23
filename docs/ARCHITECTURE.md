# Architecture

## System diagram

```
Claude Code (any session, any project)
│
├── UserPromptSubmit hook ─────────────────────────────────────────────┐
│   hooks/claude_ui_heartbeat.sh                                       │
│   - Captures session_id, cwd, git branch, iTerm tab name, PID,      │
│     ITERM_SESSION_ID UUID                                             │
│   - Background POST → localhost:7842/api/heartbeat                   │
│                                                                      │
├── PreToolUse hook ────────────────────────────────────────────────────┤
│   hooks/claude_ui_tool_use.sh                                         │
│   - Background POST → localhost:7842/api/touch                        │
│   - Fires before every tool call — keeps last_seen current during     │
│     long Claude responses (prevents idle drift while working)         │
│                                                                      ▼
└── Stop hook ─────────────────────────── localhost:7842 (Docker)
    hooks/claude_ui_stop.sh               FastAPI + SQLite
    - Posts session_id, transcript_path │
                                        ├── /api/heartbeat         → db.upsert_heartbeat()
                                        ├── /api/touch             → db.touch_session()
                                        ├── /api/stop              → db.record_stop()
                                        │                             + async summarise()
                                        ├── /api/sessions          → db.list_sessions()
                                        │                             + PID liveness check
                                        ├── /api/sessions/{id}     PATCH → summary/notes
                                        ├── /api/sessions/{id}/summarise POST → re-summarise
                                        ├── /api/sessions/{id}     DELETE → remove session
                                        └── /api/settings          GET/PATCH


localhost:7843 (host Python — needs osascript + macOS window server)
  scripts/focus_server.py
  ├── POST /focus      → PID→TTY→osascript focus; fallback: new tab with claude --resume
  ├── POST /rename     → osascript: rename iTerm2 session by name match
  ├── GET  /pid/<pid>  → os.kill(pid, 0) liveness check
  └── GET  /sessions   → list all iTerm2 session names (debug)


scripts/sync_iterm_tabs.py   (run manually after renaming tabs)
  Uses iTerm2 Python API (ITERM2_PYTHON) to read titleOverride (user-set aliases)
  Falls back to osascript TTY matching if ITERM2_PYTHON not set
  Updates iterm_tab + iterm_session_uuid in DB


~/.membridge/sessions.db   SQLite, mounted as Docker volume
```

## Component responsibilities

### Heartbeat hook (`hooks/claude_ui_heartbeat.sh`)
Fires on every `UserPromptSubmit`. Runs in background (`&`) so Claude is never blocked. Sends `session_id`, `cwd`, `git_branch`, `iterm_tab`, `pid`, `iterm_session_uuid` to the API. Max timeout 3 seconds; silently drops on failure.

### Stop hook (`hooks/claude_ui_stop.sh`)
Fires when a Claude session ends. Sends `session_id` and `transcript_path`. The server triggers async summary generation (Claude haiku) from the transcript.

### FastAPI server (`membridge/server.py`)
Runs inside Docker. Handles all API routes. On first heartbeat for a session, calls the focus server's `/rename` endpoint via `host.docker.internal:7843` to rename the iTerm tab. Status computation calls `/pid/<pid>` to check liveness — stale sessions with an alive PID are floored to idle.

### SQLite (`membridge/db.py`)
Two tables: `sessions` and `settings`. Migrations applied on startup via try/except (idempotent). Volume-mounted to `~/.membridge/sessions.db` on the host.

### Focus server (`scripts/focus_server.py`)
Pure stdlib Python, no deps. Must run on the Mac host (not Docker) because `osascript` only works on macOS. Registered as a launchd service (`com.daihi.membridge-focus`). CORS: allows `http://localhost:7842`. Also exposes `/pid/<pid>` for host-side process liveness checks (Docker can't see host PIDs directly).

### Tab alias sync (`scripts/sync_iterm_tabs.py`)
Run manually after renaming iTerm2 tabs. Uses the iTerm2 Python API (requires `ITERM2_PYTHON` env var + iTerm2 Python runtime installed) to read `tab.titleOverride` — the user-set alias. Matches sessions by UUID (from `$ITERM_SESSION_ID`) or PID→TTY fallback. Updates `iterm_tab` and `iterm_session_uuid` in the DB.

### Dashboard (`membridge/static/`)
Vanilla JS, no build step. **Static files are baked into the Docker image — rebuild required after any change.** Polls `/api/sessions` on a configurable interval (default 30s). Side panel shows full session metadata, editable summary, auto-saved notes. Project filter and show-stale checkbox state persist to `localStorage`.

## Data model

```sql
sessions (
  session_id          TEXT PRIMARY KEY,  -- Claude's session UUID
  cwd                 TEXT,              -- Working directory
  project_name        TEXT,              -- Last segment of cwd
  git_branch          TEXT,              -- Branch at last heartbeat
  iterm_tab           TEXT,              -- iTerm tab alias (titleOverride) or auto name
  iterm_session_uuid  TEXT,              -- UUID from $ITERM_SESSION_ID (stable per tab)
  pid                 INTEGER,           -- Claude process PID (PPID in hook)
  first_seen          TEXT,              -- ISO8601 UTC
  last_seen           TEXT,              -- ISO8601 UTC (updated on heartbeat)
  last_stop_reason    TEXT,              -- From Stop hook
  summary             TEXT,              -- Auto (Claude haiku) or user-edited
  summary_source      TEXT,              -- 'auto' | 'user' | 'backfill'
  prompt_count        INTEGER,           -- Incremented on each heartbeat
  notes               TEXT               -- Manual work log (side panel)
)

settings (
  key    TEXT PRIMARY KEY,
  value  TEXT
)
-- Keys: active_threshold_secs (300), idle_threshold_secs (7200), refresh_interval_secs (30)
```

## Status computation

| Status | Condition |
|--------|-----------|
| active | last_seen < `active_threshold_secs` ago |
| idle   | last_seen between active and `idle_threshold_secs` |
| stale  | last_seen > `idle_threshold_secs` ago **and** PID is dead |
| idle   | last_seen > `idle_threshold_secs` ago **but** PID is still alive |

Thresholds are user-configurable via the Settings modal (⚙). Status computed at query time in `server.py:_compute_status()`, with a host-side PID liveness check via `focus_server.py:GET /pid/<pid>`.

## Why Docker for the main app but host Python for the focus server?

`osascript` is a macOS-only binary that communicates with the macOS window server. It cannot run inside a Linux Docker container. Similarly, `os.kill(pid, 0)` inside Docker cannot see host PIDs. The main FastAPI app has no such constraint, and Docker keeps its Python dependencies isolated from the host.
