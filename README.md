# MemBridge

A local webapp that tracks your Claude Code sessions so you always know what each one was working on, when it was last active, and how to get back to it.

## The problem

When you have many Claude Code sessions running across iTerm tabs, you lose track of which session corresponds to which piece of work. `claude --resume <session-id>` is powerful, but only if you know which ID to use.

## What it does

- **Auto-registers sessions** via Claude Code hooks — no manual setup per session
- **Auto-summarises** each session when you stop, using Claude haiku via Vertex AI
- **Dashboard** showing active / idle / stale status, git branch, last active time, prompt count
- **Project filter** — filter sessions by project name
- **Side panel** — click any row to open a detail drawer with full metadata, editable summary, and notes
- **Focus button** — clicks through to the right iTerm2 tab (or opens a new one with the resume command)
- **Tab rename** — renames your iTerm2 tab to the project name automatically
- **Notes field** — per-session work log, auto-saved
- **Copy resume command** — one click copies `claude --resume <session-id>` to clipboard
- **Backfill** — import your existing session history from `~/.claude/projects/`
- **Dark / light theme** toggle, preference persisted in localStorage

## Architecture

```
Claude Code (any session)
  UserPromptSubmit hook  →  POST localhost:7842/api/heartbeat  (registers prompt, increments count)
  PreToolUse hook        →  POST localhost:7842/api/touch       (keeps session active during long responses)
  Stop hook              →  POST localhost:7842/api/stop        (triggers auto-summary)

localhost:7842  FastAPI + SQLite   (Docker / OrbStack)
localhost:7843  Focus server       (host Python — needs osascript)

~/.claude-ui/sessions.db           SQLite DB (persists across rebuilds)
```

## Requirements

- macOS (osascript / iTerm2 integration)
- Docker / OrbStack
- Python 3.11+ (for the focus server and install script)
- An Anthropic API key **or** Vertex AI (for auto-summary via Claude haiku)

> **Note:** Claude Code itself can run on a Claude.ai subscription (OAuth, no API key needed). The auto-summariser runs inside Docker and calls the API directly — it requires either `ANTHROPIC_API_KEY` (default) or Vertex AI credentials (`CLAUDE_CODE_USE_VERTEX=1`). The Claude.ai subscription OAuth cannot be used here.

## Setup

### 1. Configure environment

Create a `.env` file (see `.env.example`):

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Run the installer

```bash
bash scripts/install.sh
```

This will:
- Build the Docker image
- Create `~/.claude-ui/` for the SQLite DB
- Register `UserPromptSubmit`, `PreToolUse`, and `Stop` hooks in `~/.claude/settings.json`
- Install a launchd service for the focus server (`com.daihi.claude-ui-focus`, port 7843)

### 3. Start the app

```bash
cd ~/git/membridge
docker compose up -d
```

### 4. Restart Claude Code

Hooks only take effect after a restart. New sessions will appear in the dashboard automatically.

### 5. Backfill historical sessions (optional)

```bash
cd ~/git/membridge
python3 scripts/backfill.py --dry-run --days 30   # preview
python3 scripts/backfill.py --days 30              # import
```

## Dashboard

Open **http://localhost:7842** in your browser.

| Column | Description |
|--------|-------------|
| Status | `active` (<5 min), `idle` (<2 h), `stale` (>2 h) |
| Project | Directory name + truncated session ID |
| Branch | Git branch at time of last heartbeat |
| Last Active | Relative time since last prompt |
| Prompts | Total prompt count |
| Summary | Auto-generated or user-edited (click row to edit in panel) |

Click any row to open the **side panel** with full details: session ID, cwd, PID, iTerm tab, first seen, and an editable notes field (auto-saved).

## Data

- **SQLite DB**: `~/.claude-ui/sessions.db`
- **Focus server log**: `/tmp/claude-ui-focus.log`

## Docs

- [Architecture](docs/ARCHITECTURE.md) — system diagram, component responsibilities, data model
- [Backlog](docs/BACKLOG.md) — planned and future work
