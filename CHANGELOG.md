# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] — 2026-06-22

Initial release.

### Features

- **Session tracking** — Claude Code `UserPromptSubmit` hook registers every session with `session_id`, working directory, git branch, iTerm tab name, and PID
- **Heartbeat polling** — `prompt_count` and `last_seen` updated on every user prompt; no manual intervention required
- **Session stop recording** — `Stop` hook captures stop reason and triggers async summarisation
- **Auto-summary** — Vertex AI (Claude haiku) generates a session summary from the transcript on stop; skipped if user has edited the summary
- **Dashboard** at `http://localhost:7842` — status pills (active / idle / stale), project filter, relative timestamps, prompt counts
- **Side panel** — click any row for full session metadata: session ID, cwd, PID, iTerm tab, first seen, editable summary, auto-saved notes
- **Project filter** — filter session list by project name
- **Focus / Open button** — focuses the iTerm2 tab by name via `osascript`; falls back to opening a new tab with the resume command
- **Copy resume** — copies `claude --resume <session-id>` to clipboard
- **Tab rename** — renames the iTerm2 tab to `<project> · <branch>` on first session registration
- **Inline summary editing** — edit the session summary directly in the side panel; marked as `user` source to prevent auto-overwrite
- **Notes field** — per-session free-text work log in the side panel, auto-saved on input
- **Dark / light theme** toggle, persisted to localStorage; dark is default
- **Backfill script** (`scripts/backfill.py`) — imports existing session history from `~/.claude/projects/`
- **Docker / OrbStack deployment** — main app in Docker on port 7842, SQLite persisted to `~/.membridge/sessions.db`
- **Focus server** — host-side Python HTTP server (port 7843) for iTerm2 integration; registered as launchd service
