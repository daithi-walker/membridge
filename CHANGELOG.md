# MemBridge Changelog

Completed work, newest first.

---

## Unreleased

- Session backups via [`sesh`](https://github.com/m-gharibi/sesh) (`membridge/sesh.py`) - opt-in, per-project snapshots of a session's live transcripts, taken automatically on every Stop. MemBridge stays a control plane (metadata/focus/summaries); sesh owns content preservation and full-text search in a per-project `.sesh/` archive. Optional and best-effort: the wrapper no-ops if the `sesh` binary is absent or the project was never `sesh init`'d, so it's free for sessions that never enable it. Resume prefers `sesh resume` when available. New REST endpoints: `GET/POST /api/sessions/{id}/sesh`, `.../sesh/init`, `.../sesh/snapshot`, `GET .../sesh/snapshots`, and `GET /api/sesh/find`. Tests in `tests/test_sesh.py` cover the no-op degradation, the `.sesh/` ancestor walk, and the endpoints with `subprocess` mocked (no real binary invoked).
- Append-only `activity_events` table (`kind='prompt'` on `UserPromptSubmit`, `kind='stop'` when Claude finishes a turn) - one interleaved timeline per client, alongside the existing `sessions` upsert which only ever keeps `first_seen`/`last_seen`. Started as two separate tables (`heartbeat_events`/`stop_events`), consolidated into one before release since the analysis needs both merged anyway; a one-time forward migration handles the transition automatically. Also captures the full `prompt` text / `last_assistant_message` text and `transcript_path` for each event - both come through in the real hook payloads already, at essentially no extra cost, and mean a gap or block found later can be understood directly instead of requiring a separate cross-reference into the transcript. See `docs/BACKLOG.md` #7 for a follow-up idea to purge full text on session archive, since it grows with transcript volume.
- `db.get_activity_events(project_name, since, until, kind)` query helper.
- `scripts/heartbeat_report.py` / `/membridge-report [client] [from] [to] [idle-minutes]` - reconstructs real engaged-work time for a client. Pairs each prompt with the next `stop` in the same session into an "active" interval (unambiguous - Claude was working, interactively or autonomously), then merges active intervals across every session for that client into one timeline before computing gaps - so having 2-3 sessions open for the same client at once doesn't create false gaps just because one of them is idle while another is active. A gap in the merged timeline under `--idle-minutes` (default 15) counts as engaged (reading/thinking); anything longer is flagged and excluded from the billable estimate, but still shown for a sanity check against memory. This is a heuristic, not a clock - it can't see reading time with no further activity after it, and it only covers events from 2026-08-13 onward.
- 12 new tests (126 total).

## v0.2.1 - 2026-07-15

- Machine-agnostic config — launchd service renamed to `com.membridge`; server honours `MEMBRIDGE_HOST`/`MEMBRIDGE_PORT` and hooks POST to `MEMBRIDGE_URL` (defaults unchanged); removed hardcoded home-dir paths from tests, comments, and docs
- Added `.github/CODEOWNERS`

## v0.2.0 - 2026-07-12

- Thinking pulse — `PreToolUse` hook broadcasts `tool_start` SSE event with tool name; new `PostToolBatch` hook broadcasts `tool_end`; active session's ◉ button pulses fast (0.55s) with green fill while a tool is executing; `tool_name` shown on hover; clears on batch complete or Stop
- 5 new tests for thinking pulse (112 total)

## v0.1.0 - 2026-07-11

Initial public release.

## 2026-06

- Pin order button (⊞) in header - freezes row order so sessions don't shuffle during active work; auto-pins when a session panel is opened (prevents table jitter while modal is up); unpin to re-sort
- Sort fix: sessions now order by status band (active → idle → stale), then starred within band, then recency - starred stale sessions no longer float above active ones
- Ticket base URL setting - configure a base URL (Jira, ADO, Linear, etc.) in Settings; ticket IDs in the panel become clickable links; multi-tracker friendly (one URL per workspace)
- `/membridge-note <text>` slash command - inject freeform text verbatim into session history with `source: user`; no summarization, no file params, single line
- `/membridge-rename` replaces `/membridge-tag` - same action (set session description), clearer name
- `/membridge-link` slash command - link current session to another by ID prefix; no-arg lists existing links
- 🔗 link indicator moved to dedicated rightmost `col-links` column (36px, centred)
- Session links - bidirectional cross-session linking via `session_links` join table; link chips in the panel with search-to-add, click-to-navigate, and × to remove; 🔗 indicator in table; `/membridge-context` appends linked sessions block; 18 new tests (108 total)
- Bug fix: panel modal re-render suppressed while ticket input or notes textarea has focus (same SSE race as inline description edit); `sessions[]` synced on ticket/notes save
- Description column wraps text - `white-space: normal` on `td.col-desc`; 120-char JS truncation removed; rows grow to fit long descriptions
- Bug fix: column resize now works on all columns - `overflow:hidden` was clipping the `::after` drag handle on `th` elements; split into `th` (visible) and `td` (hidden) rules; resize handle widened from 4px to 8px; hotzone widened to 12px; drag baseline uses live `rect.width` so columns don't snap on first drag
- Table width changed from `max-content/min-width:100%` to `width:100%` - prevents description/branch columns from bloating beyond viewport width
- Brain emoji favicon (inline SVG data URI, no extra file)
- Bug fix: inline table description edit no longer lost when SSE refresh or poll timer fires mid-edit - `editingInline` flag suppresses `render()` while input is active; `sessions[]` updated on save so next render has the correct value
- Bug fix: `notification_type` field (not `type`) now read correctly from Notification hook payload; was causing all notifications to store as `"notification:"` with empty type, breaking `?` icon
- Bug fix: any `last_stop_reason` starting with `"notification:"` now shows `?` icon - covers all notification types, not just `permission_prompt`
- FastAPI lifespan migration - `@app.on_event("startup")` replaced with `@asynccontextmanager _lifespan()` in `server.py`; deprecation warnings eliminated; poll task cancelled cleanly on shutdown
- Security: AppleScript shell injection fix in `focus.py` - `_safe_path()`/`_safe_id()` regex validators applied before `cwd`/`session_id` interpolation into `write text` command
- Security: server binds to `127.0.0.1` by default (`MEMBRIDGE_HOST` env var for LAN); DOMPurify sanitisation on all `marked.parse()` output; SRI hashes on CDN scripts; security headers middleware (X-Content-Type-Options, X-Frame-Options, Referrer-Policy)
- Test suite - 90 tests across `test_db.py`, `test_server.py`, `test_focus.py`, `test_summariser.py`; 80% total coverage
- CI - GitHub Actions (`.github/workflows/lint.yml`) runs ruff + mypy + pytest on push/PR
- `docs/CODING_STANDARDS.md` - security, error handling, DB, testing, and style rules
- `docs/COVERAGE.md` - per-release coverage tracking with improvement targets
- ADR 012 - documents Docker removal decision; ADR 004 marked superseded
- Mobile card view - below 768px, table is replaced by stacked cards showing status icon, focus button, project, status pill, description, branch, last active, and short ID; modal slides up as bottom sheet on mobile
- Mobile: pull-to-refresh works (browser native gesture); `window.location.origin` replaces hardcoded `localhost:7842` so focus/sync work from LAN (phone); fixed single-quote bug from revert that was sending literal `${BASE}` as the URL
- Mobile: modal sheet uses `92dvh` so Chrome iOS persistent toolbars do not clip the top; drag handle pill + larger ✕ button for close affordance; home indicator safe area padding on card list
- Inline description editing in table row - click description cell, type, Enter to save, Escape to revert; row click still opens modal
- Column resize rewritten - widths driven by `<colgroup><col>` elements; resizing one column never shifts others; table scrolls horizontally if needed; drag target is right edge of any header
- Bug fix: modal description edit no longer shows wrong session's text (stale closure fixed)
- `/membridge-tag <text>` slash command - set or update session description instantly; Claude can self-tag its own sessions
- Activity column and vestigial › chevron removed; Description column fills remaining width
- Session ID as separate column (short 8-char prefix); click to copy full UUID to clipboard
- Modal: copy button (⎘) next to full session ID in header
- Bug fix: `ask_user_question` stop reason now shows `?` icon (same as `permission_prompt`); previously showed `✎` pencil
- Focus button icons: `?` for decision prompts, `✎` for text input, `◉` for working - distinguished via `last_stop_reason`
- Bug fix: `last_stop_reason` preserved when Stop hook fires after Notification hook (previously overwritten with empty string)
- Bug fix: `touch_session` now clears `awaiting_input` so answering a decision transitions immediately to working state
- `ideas/` catalog added under `docs/` - speculative features blocked on external capabilities
- Notification prefs in Settings modal - Pop-ups and Sound toggles (sound off by default); prefs synced to DB
- `Notification` hook (matcher: `permission_prompt`) - sets `awaiting_input` immediately when Claude asks permission mid-turn
- SSE push-refresh (`/api/events`) - dashboard updates instantly on heartbeat/stop; eliminates 30s poll lag
- `awaiting_input` DB flag - set on Stop/Notification hook, cleared on heartbeat; drives green ◉ state
- 4-state focus button: green ◉ awaiting / orange ◉ working / amber ↩ resume / grey ⌘ idle (ADR 010)
- macOS notification on Stop - fires only on 0→1 awaiting transition; suppressed if session tab is frontmost
- Header badge "◉ N awaiting input" - pulsing green, clickable (scrolls + flashes first awaiting row)
- Legend under toolbar explains all 4 focus button states
- `POST /api/sessions/{id}/push-summary` - slash command pushes text direct to DB; no file, no 30s poll lag
- `/membridge-summarize` uses tmpfile pipeline to preserve real newlines in markdown
- `RELEASES.md` - migration notes for breaking changes; `CLAUDE.md` rewritten for native process
- Star/focus buttons moved into Status column (no dedicated column, no wasted space)
- Star sessions to pin them to the top; Show ▾ has Starred filter option
- **Drop Docker** - membridge runs natively via launchd; single plist on port 7842; osascript/focus calls direct (no port 7843 hop); static file changes live on browser refresh; `scripts/install.sh` rewrites to uv venv
- `membridge/focus.py` - osascript logic extracted; `/focus` `/rename` `/pid/<pid>` `/sync-tabs` routes merged into main server
- Resizable table columns - drag handles on all headers, widths persisted to localStorage
- Activity column (was "iTerm Tab") - shows live Claude Code task title, updated every heartbeat
- Auto-summary text-match dedup - same bracketed description not re-inserted even when transcript grows
- Removed heartbeat tab rename on UUID change - was resetting all tab names after container rebuild (ADR 009)
- Focus button resumes dead sessions: UUID match → PID/TTY → open new tab with `claude --resume` in correct cwd
- Bulk-fixed 106 sessions with bad home-dir paths from a symlinked-home backfill; `Path.resolve()` guard added to upsert
- Show ▾ filter dropdown (active/idle/stale/archived) replaces stale + archived checkboxes

- Auto-summary dedup by `transcript_path:file_size` - Stop hook fires every turn, not just session close; dedup prevents duplicate history entries
- ADRs 001-008 documenting all major architectural decisions
- `/membridge-recall` slash command - list recent sessions or dump summaries by session ID prefix
- `/membridge-archive` slash command - toggles archived state for current session via PATCH API
- `/membridge-summarize` delta awareness - fetches prior summaries before writing, covers only new work
- Unified "Show ▾" filter dropdown (active/idle/stale/archived) replacing stale + archived checkboxes
- Multi-select project filter with All/None buttons; fixed filter inversion bug
- Archive session feature - `archived` boolean on sessions, toggle in modal, hidden by default
- Rename `claude-ui` → `membridge` across all files, Docker image, launchd labels
- Vertex AI ADC volume mount in Docker for summariser auth
- Re-summarise endpoint (`POST /api/sessions/{id}/summarise`)
- Delete session endpoint (`DELETE /api/sessions/{id}`)
- Summary file poller (30s interval, dedup by file path)
- `/membridge-summarize` slash command (Bash heredoc, dynamic session path)
- Markdown rendering in modal summary and history entries (marked.js)
- History UI - always visible in modal, grouped by source file, collapsible
- `session_summaries` append-only log table with source tracking (auto/skill/user)
- `sessions.description` as short AI one-liner (`[bracket]` format), separate from history
- Session modal (replaced side panel) - metadata, description, history, notes, actions
- `PreToolUse` hook → `/api/touch` - keeps sessions active during long tool chains
- Dark/light theme toggle, persisted to localStorage
- Backfill script for historical sessions from `~/.claude/projects/`
- Copy resume command button (`claude --resume <id>`)
- iTerm2 UUID-based tab stability - UUID as stable identity, display name tracked separately
- Focus button - raises iTerm2 window via focus server (osascript / iTerm2 Python API)
- Project filter dropdown
- Session modal with metadata, summary, notes
- Dashboard with active/idle/stale status, git branch, iTerm tab, prompt count
- Auto-summary on Stop via Claude haiku (Anthropic SDK + Vertex AI backend)
- Session registration via `UserPromptSubmit` hook (heartbeat upsert, first-seen tracking)
