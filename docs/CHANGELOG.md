# MemBridge Changelog

Completed work, newest first.

---

## 2026-06

- Resizable table columns — drag handles on all headers, widths persisted to localStorage
- iTerm Tab column renamed to Activity — shows live Claude Code task title, updated every heartbeat
- Auto-summary text-match dedup — same bracketed description not re-inserted even when transcript grows
- Removed heartbeat tab rename on UUID change — was resetting all tab names after container rebuild (ADR 009)
- Focus button resumes dead sessions: UUID match → PID/TTY → open new tab with `claude --resume` in correct cwd
- Tab name set immediately on resume (osascript names tab before writing command)
- Tab rename on first heartbeat after `claude --resume` (UUID change detection in upsert)
- Bulk-fixed 106 sessions with bad `/Users/david/walker/` paths (other machine backfill); `Path.resolve()` guard added to upsert
- Show ▾ filter dropdown (active/idle/stale/archived) replaces stale + archived checkboxes

- Auto-summary dedup by `transcript_path:file_size` — Stop hook fires every turn, not just session close; dedup prevents duplicate history entries
- ADRs 001–008 documenting all major architectural decisions
- `/membridge-recall` slash command — list recent sessions or dump summaries by session ID prefix
- `/membridge-archive` slash command — toggles archived state for current session via PATCH API
- `/membridge-summarize` delta awareness — fetches prior summaries before writing, covers only new work
- Unified "Show ▾" filter dropdown (active/idle/stale/archived) replacing stale + archived checkboxes
- Multi-select project filter with All/None buttons; fixed filter inversion bug
- Archive session feature — `archived` boolean on sessions, toggle in modal, hidden by default
- Rename `claude-ui` → `membridge` across all files, Docker image, launchd labels
- Vertex AI ADC volume mount in Docker for summariser auth
- Re-summarise endpoint (`POST /api/sessions/{id}/summarise`)
- Delete session endpoint (`DELETE /api/sessions/{id}`)
- Summary file poller (30s interval, dedup by file path)
- `/membridge-summarize` slash command (Bash heredoc, dynamic session path)
- Markdown rendering in modal summary and history entries (marked.js)
- History UI — always visible in modal, grouped by source file, collapsible
- `session_summaries` append-only log table with source tracking (auto/skill/user)
- `sessions.description` as short AI one-liner (`[bracket]` format), separate from history
- Session modal (replaced side panel) — metadata, description, history, notes, actions
- `PreToolUse` hook → `/api/touch` — keeps sessions active during long tool chains
- Dark/light theme toggle, persisted to localStorage
- Backfill script for historical sessions from `~/.claude/projects/`
- Copy resume command button (`claude --resume <id>`)
- iTerm2 UUID-based tab stability — UUID as stable identity, display name tracked separately
- Focus button — raises iTerm2 window via focus server (osascript / iTerm2 Python API)
- Project filter dropdown
- Session modal with metadata, summary, notes
- Dashboard with active/idle/stale status, git branch, iTerm tab, prompt count
- Auto-summary on Stop via Claude haiku (Anthropic SDK + Vertex AI backend)
- Session registration via `UserPromptSubmit` hook (heartbeat upsert, first-seen tracking)
