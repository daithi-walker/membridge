# Claude UI — Technical Design

**Status:** Draft v1  
**Date:** 2026-06-22  
**Branch:** worktree-feat+claude-ui

---

## 1. Problem

You run many Claude Code sessions across iTerm tabs and projects. There's no way to see at a glance:
- What sessions are active / idle / dead
- What each session is working on
- How to resume a specific session

The goal is a local-first webapp that tracks Claude sessions, shows their status, and lets you annotate them with a summary and Jira key — eventually becoming a lightweight UI layer over your Claude workflow.

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Claude Code (any session)                               │
│  hooks:                                                  │
│    UserPromptSubmit → POST /api/heartbeat               │
│    Stop             → POST /api/stop                    │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP (localhost:7842)
┌──────────────────────▼───────────────────────────────────┐
│  FastAPI server  (claude-ui)                             │
│  SQLite DB       (sessions, heartbeats)                  │
│  Static HTML/JS  (dashboard)                             │
└──────────────────────────────────────────────────────────┘
                       │
              launchd (always-on)
```

Everything runs locally on port **7842** (chosen to avoid conflicts). No authentication — localhost only.

---

## 3. Data Model

### `sessions` table

| column | type | notes |
|--------|------|-------|
| `session_id` | TEXT PK | Claude's session_id from hook payload |
| `cwd` | TEXT | working directory at first heartbeat |
| `project_name` | TEXT | derived: basename of cwd |
| `git_branch` | TEXT | from `git branch --show-current` in hook script |
| `jira_key` | TEXT | parsed from branch name (e.g. `ALGDE-123`) or user-entered |
| `iterm_tab` | TEXT | osascript capture at first heartbeat (best-effort) |
| `first_seen` | DATETIME | UTC |
| `last_seen` | DATETIME | UTC, updated on every heartbeat |
| `last_stop_reason` | TEXT | `end_turn` / `max_tokens` / `tool_use` |
| `summary` | TEXT | user-written or auto-generated; editable in UI |
| `status` | TEXT | computed: `active` / `idle` / `stale` (see §6) |
| `prompt_count` | INTEGER | total heartbeats received |

No separate heartbeats table for now — `last_seen` + `prompt_count` is enough. Can add later for timeline views.

---

## 4. Hook Scripts

Two global hooks registered in `~/.claude/settings.json`:

### `UserPromptSubmit` hook — `claude_ui_heartbeat.sh`

Fires on every prompt submission. Sends a heartbeat to the server.

```bash
#!/bin/bash
# Read payload from stdin
PAYLOAD=$(cat)
SESSION_ID=$(echo "$PAYLOAD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['session_id'])")
CWD=$(echo "$PAYLOAD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['cwd'])")
BRANCH=$(git -C "$CWD" branch --show-current 2>/dev/null || echo "")
ITERM_TAB=$(osascript -e 'tell application "iTerm2" to get name of current tab of current window' 2>/dev/null || echo "")

curl -s -X POST http://localhost:7842/api/heartbeat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"cwd\":\"$CWD\",\"branch\":\"$BRANCH\",\"iterm_tab\":\"$ITERM_TAB\"}" \
  &>/dev/null &
# Background curl — never blocks Claude
```

### `Stop` hook — `claude_ui_stop.sh`

Fires when Claude finishes a response. Records stop reason and optionally reads a summary from the transcript.

```bash
#!/bin/bash
PAYLOAD=$(cat)
SESSION_ID=$(echo "$PAYLOAD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['session_id'])")
STOP_REASON=$(echo "$PAYLOAD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('stop_reason',''))")
TRANSCRIPT=$(echo "$PAYLOAD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('transcript_path',''))")

curl -s -X POST http://localhost:7842/api/stop \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"stop_reason\":\"$STOP_REASON\",\"transcript_path\":\"$TRANSCRIPT\"}" \
  &>/dev/null &
```

Both hooks exit 0 always — they never block Claude.

---

## 5. API

**Base:** `http://localhost:7842`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/heartbeat` | Upsert session, update last_seen |
| POST | `/api/stop` | Update stop_reason |
| GET | `/api/sessions` | List all sessions (query: `?status=active`) |
| PATCH | `/api/sessions/{id}` | Update summary, jira_key (user edits) |
| GET | `/api/sessions/{id}/transcript` | Return transcript path for client-side link |
| GET | `/` | Dashboard HTML |

---

## 6. Status Logic

Status is computed on read (not stored), based on `last_seen`:

| Status | Condition |
|--------|-----------|
| `active` | last_seen within 5 minutes |
| `idle` | last_seen 5–60 minutes ago |
| `stale` | last_seen > 60 minutes ago |

These thresholds are configurable via a small config file.

---

## 7. Dashboard

Single-page HTML served by FastAPI. Vanilla JS (no framework — keep it simple and zero-build).

**Columns:**
- Status badge (green/yellow/grey)
- Project name (from cwd basename)
- Jira key (clickable → Jira URL, editable inline)
- Git branch
- iTerm tab name
- Last seen (relative time, e.g. "3 min ago")
- Prompt count
- Summary (editable inline textarea)
- Resume button → copies `claude --resume <session_id>` to clipboard

**Behaviour:**
- Auto-refreshes every 30 seconds
- Inline edit: click summary or Jira key → textarea → blur saves via PATCH
- Sorted: active first, then idle, then stale
- Stale sessions (>24h) hidden by default, toggle to show

---

## 8. Session Resume

**Core problem:** You have many iTerm tabs running Claude sessions and no way to know which `session_id` corresponds to which piece of work. The dashboard solves this by showing session_id alongside project, branch, Jira key, and your summary — so you can identify the session you want and resume it.

The "Resume" button copies `claude --resume <session_id>` to clipboard. You paste it in a new iTerm tab. Simple and reliable.

Future v1: osascript to open a new iTerm tab and type the command automatically.

## 8a. Long-Term Vision: Orchestration Layer

This app is designed to grow into a UI control plane for Claude workflows:
- **Phase 1–2 (now):** Passive tracker — hooks report in, dashboard shows status
- **Phase 3:** Active management — submit new Claude sessions from the UI, kill/pause sessions
- **Phase 4:** Workflow orchestration — run Claude in Docker/Temporal containers, dispatch isolated jobs per task, manage multi-agent pipelines from the dashboard

The data model (session_id, status, summary, jira_key) is intentionally generic to support managed sessions (created by the app) alongside observed sessions (created by the user in iTerm). A future `source` column (`observed` vs `managed`) will distinguish them.

---

## 9. Auto-Summary

On every `Stop` event, the hook POSTs `session_id`, `stop_reason`, and `transcript_path` to `/api/stop`. The server:

1. Reads the transcript JSON (last 20 assistant+user turns)
2. Calls Claude API (`claude-haiku-4-5` — fast, cheap) with prompt: *"In 2 sentences: what is this Claude session working on, and where did it get to?"*
3. Stores the result in `sessions.summary`
4. Updates on every stop (summary reflects the most recent state)

Summary is also **editable** in the dashboard — user edits take precedence and are flagged as `summary_source: "user"` vs `"auto"`.

**Transcript format:** Claude stores transcripts as JSONL at `transcript_path`. Each line is a turn `{role, content}`. We read the file, take the last 20 turns, and pass them as the conversation context to the summary prompt.

**Failure handling:** If Claude API is unavailable or transcript unreadable, the summary stays as whatever it was before (no crash, no block on Claude).

---

## 10. Always-On: launchd

A `launchd` plist starts the FastAPI server at login and restarts it on crash.

Location: `~/Library/LaunchAgents/com.daihi.claude-ui.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.daihi.claude-ui</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/venv/bin/uvicorn</string>
    <string>claude_ui.server:app</string>
    <string>--host</string>
    <string>127.0.0.1</string>
    <string>--port</string>
    <string>7842</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardErrorPath</key>
  <string>/tmp/claude-ui.log</string>
</dict>
</plist>
```

---

## 11. Project Structure

```
root/projects/claude_ui/
├── context/
│   └── design.md          ← this file
├── claude_ui/
│   ├── __init__.py
│   ├── server.py           ← FastAPI app, routes
│   ├── db.py               ← SQLite init + queries
│   ├── models.py           ← Pydantic models
│   └── static/
│       ├── index.html      ← dashboard
│       └── app.js          ← vanilla JS
├── hooks/
│   ├── claude_ui_heartbeat.sh
│   └── claude_ui_stop.sh
├── scripts/
│   └── install.sh          ← registers hooks, installs launchd plist
├── pyproject.toml
└── README.md
```

---

## 12. Implementation Phases

| Phase | Scope | Est. effort |
|-------|-------|-------------|
| **1 — MVP** | Heartbeat + Stop hooks, FastAPI + SQLite, dashboard table, status colours, resume copy | ~2–3h |
| **1b — Auto-summary** | Read transcript on stop, call Claude API (haiku) for 2-sentence summary | ~1h |
| **2 — Polish** | Inline edit (summary + Jira), launchd install script, iTerm tab capture | ~1h |
| **3 — Resume UX** | osascript iTerm integration, open-in-tab button | ~30min |
| **4 — Orchestration** | Submit Claude sessions from UI, Docker/Temporal dispatch, managed sessions | future |

---

## 13. Out of Scope (v1)

- Authentication
- Multi-machine sync
- Timeline / activity graph
- Per-project configuration
- Search / filter UI
