# MemBridge Changelog

Completed work, newest first.

---

## 2026-06

- Mobile card view — below 768px, table is replaced by stacked cards showing status icon, focus button, project, status pill, description, branch, last active, and short ID; modal slides up from bottom on mobile
- Inline description editing in table row — click description cell, type, Enter to save, Escape to revert; row click still opens modal
- Column resize rewritten — widths driven by `<colgroup><col>` elements; resizing one column never shifts others; table scrolls horizontally if needed; drag target is right edge of any header
- Bug fix: modal description edit no longer shows wrong session's text (stale closure fixed)
- `/membridge-tag <text>` slash command — set or update session description instantly; Claude can self-tag its own sessions
- Activity column and vestigial › chevron removed; Description column fills remaining width
- Session ID as separate column (short 8-char prefix); click to copy full UUID to clipboard
- Modal: copy button (⎘) next to full session ID in header
- Focus button icons: `?` for decision prompts, `✎` for text input, `◉` for working — distinguished via `last_stop_reason`
- Bug fix: `last_stop_reason` preserved when Stop hook fires after Notification hook (previously overwritten with empty string)
- Bug fix: `touch_session` now clears `awaiting_input` so answering a decision transitions immediately to working state
- `ideas/` catalog added under `docs/` — speculative features blocked on external capabilities
- Notification prefs in Settings modal — Pop-ups and Sound toggles (sound off by default); prefs synced to DB
- `Notification` hook (matcher: `permission_prompt`) — sets `awaiting_input` immediately when Claude asks permission mid-turn
- SSE push-refresh (`/api/events`) — dashboard updates instantly on heartbeat/stop; eliminates 30s poll lag
- `awaiting_input` DB flag — set on Stop/Notification hook, cleared on heartbeat; drives green ◉ state
- 4-state focus button: green ◉ awaiting / orange ◉ working / amber ↩ resume / grey ⌘ idle (ADR 010)
- macOS notification on Stop — fires only on 0→1 awaiting transition; suppressed if session tab is frontmost
- Header badge "◉ N awaiting input" — pulsing green, clickable (scrolls + flashes first awaiting row)
- Legend under toolbar explains all 4 focus button states
- `POST /api/sessions/{id}/push-summary` — slash command pushes text direct to DB; no file, no 30s poll lag
- `/membridge-summarize` uses tmpfile pipeline to preserve real newlines in markdown
- `RELEASES.md` — migration notes for breaking changes; `CLAUDE.md` rewritten for native process
- Star/focus buttons moved into Status column (no dedicated column, no wasted space)
- Star sessions to pin them to the top; Show ▾ has Starred filter option
- **Drop Docker** — membridge runs natively via launchd; single plist on port 7842; osascript/focus calls direct (no port 7843 hop); static file changes live on browser refresh; `scripts/install.sh` rewrites to uv venv
- `membridge/focus.py` — osascript logic extracted; `/focus` `/rename` `/pid/<pid>` `/sync-tabs` routes merged into main server
- Resizable table columns — drag handles on all headers, widths persisted to localStorage
- Activity column (was "iTerm Tab") — shows live Claude Code task title, updated every heartbeat
- Auto-summary text-match dedup — same bracketed description not re-inserted even when transcript grows
- Removed heartbeat tab rename on UUID change — was resetting all tab names after container rebuild (ADR 009)
- Focus button resumes dead sessions: UUID match → PID/TTY → open new tab with `claude --resume` in correct cwd
- Bulk-fixed 106 sessions with bad `/Users/david/walker/` paths; `Path.resolve()` guard added to upsert
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
