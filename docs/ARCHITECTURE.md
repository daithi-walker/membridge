# Architecture

## System diagram

```
Claude Code (any session, any project)
│
├── UserPromptSubmit hook ─────────────────────────────────────────┐
│   hooks/claude_ui_heartbeat.sh                                   │
│   - Captures session_id, cwd, git branch, iTerm tab name, PID   │
│   - Background POST → localhost:7842/api/heartbeat               │
│                                                                  ▼
└── Stop hook ───────────────────────────── localhost:7842 (Docker / OrbStack)
    hooks/claude_ui_stop.sh                 FastAPI + SQLite
    - Posts session_id, transcript_path  │
                                         ├── /api/heartbeat  → db.upsert_heartbeat()
                                         ├── /api/stop       → db.record_stop()
                                         │                      + async summarise()
                                         ├── /api/sessions   → db.list_sessions()
                                         └── /api/sessions/{id} PATCH → update summary/notes


localhost:7843 (host Python — needs osascript)
  scripts/focus_server.py
  ├── POST /focus   → osascript: find iTerm2 tab by name, select it
  └── POST /rename  → osascript: rename iTerm2 tab session

~/.claude-ui/sessions.db   SQLite, mounted as Docker volume
```

## Component responsibilities

### Heartbeat hook (`hooks/claude_ui_heartbeat.sh`)
Fires on every `UserPromptSubmit`. Runs in background (`&`) so Claude is never blocked. Sends `session_id`, `cwd`, `git_branch`, `iterm_tab`, `pid` to the API. Max timeout 3 seconds; silently drops on failure.

### Stop hook (`hooks/claude_ui_stop.sh`)
Fires when a Claude session ends. Sends `session_id` and `transcript_path`. The server triggers async summary generation (Claude haiku via Anthropic API) from the transcript.

### FastAPI server (`claude_ui/server.py`)
Runs inside Docker. Handles all API routes. On first heartbeat for a session, calls the focus server's `/rename` endpoint via `host.docker.internal:7843` to rename the iTerm tab.

### SQLite (`claude_ui/db.py`)
Single `sessions` table. Migrations applied on startup via try/except (idempotent). Volume-mounted to `~/.claude-ui/sessions.db` on the host.

### Focus server (`scripts/focus_server.py`)
Pure stdlib Python, no deps. Must run on the Mac host (not Docker) because `osascript` only works on macOS. Registered as a launchd service (`com.daihi.claude-ui-focus`). CORS: allows `http://localhost:7842`.

### Dashboard (`claude_ui/static/`)
Vanilla JS, no build step. Polls `/api/sessions` every 30 seconds. Side panel shows full session metadata, editable summary, auto-saved notes. Project filter is populated dynamically from session data.

## Data model

```sql
sessions (
  session_id      TEXT PRIMARY KEY,  -- Claude's session UUID
  cwd             TEXT,              -- Working directory
  project_name    TEXT,              -- Last segment of cwd
  git_branch      TEXT,              -- Branch at last heartbeat
  iterm_tab       TEXT,              -- iTerm tab name at registration
  pid             INTEGER,           -- Claude process PID
  first_seen      TEXT,              -- ISO8601 UTC
  last_seen       TEXT,              -- ISO8601 UTC (updated on heartbeat)
  last_stop_reason TEXT,             -- From Stop hook
  summary         TEXT,              -- Auto (Claude haiku) or user-edited
  summary_source  TEXT,              -- 'auto' | 'user' | 'backfill'
  prompt_count    INTEGER,           -- Incremented on each heartbeat
  notes           TEXT               -- Manual work log (side panel)
)
```

## Status thresholds

| Status | Condition |
|--------|-----------|
| active | last_seen < 5 minutes ago |
| idle   | last_seen 5 min – 2 h ago |
| stale  | last_seen > 2 h ago |

Computed at query time in `server.py:_compute_status()`.

## Why Docker for the main app but host Python for the focus server?

`osascript` is a macOS-only binary that communicates with the macOS window server. It cannot run inside a Linux Docker container. The main FastAPI app has no such constraint, and Docker keeps its Python dependencies isolated from the host.
