# MemBridge Backlog

Planned work, ordered by priority within each tier. See `docs/adr/` for the decisions behind items marked with an ADR reference.

---

## Near-term

### 1. Session feedback / reply from dashboard

Allow sending a follow-up prompt to a waiting Claude session directly from the MemBridge dashboard.

Design:
- `Stop` hook sets a new `awaiting_input` flag on the session (or we derive it from `last_stop_reason`)
- `/api/stop` fires a macOS notification via osascript: `display notification "project is waiting" with title "MemBridge"`
- Dashboard shows a reply textarea for sessions in `awaiting_input` state
- Send button calls `focus.py` `write text "your message\n"` to the session's iTerm2 UUID
- Guard: check session is still `awaiting_input` before writing - avoid injecting into an active response
- Inline focus button in table row turns amber when `awaiting_input`

### 3. Clickable macOS notifications - focus iTerm tab on click

`osascript display notification` is fire-and-forget; clicking the banner does nothing. Replace with `terminal-notifier` (Homebrew) so:
- Clicking the notification focuses the correct iTerm2 tab (calls `focus.py focus_session()`)
- Notifications are more reliable from launchd context (osascript banners can be suppressed there)

Implementation in `_notify_stop()` (`server.py`):
- Call `terminal-notifier -title "..." -message "..." -execute "osascript -e 'tell app iTerm2...'"` 
- Fall back to plain `osascript display notification` if `terminal-notifier` is not installed (`shutil.which`)
- `install.sh` can optionally `brew install terminal-notifier` with a prompt

Alternative (no Homebrew dependency): small Swift helper using `UNUserNotificationCenter` with a registered click action - more work but no external dep.

### 3. Show model name per session

Capture the Claude model from hook payloads (`model` field in some events), store in `sessions` table, surface as a tooltip or small tag in the dashboard row.

Small migration: one new column, one extra field in heartbeat extraction.

### 3. Improve `server.py` test coverage (67% → 80%+)

90 tests exist (`test_db.py`, `test_server.py`, `test_focus.py`, `test_summariser.py`). Remaining gaps in `server.py`:

- `_notify_stop()` - mock `subprocess.Popen`; test sound/no-sound and frontmost-session skip
- `_generate_summary()` async task - mock `summarise()` + asyncio task creation
- SSE `/api/events` stream - async generator test client
- `/sync-tabs` - mock `threading.Thread` / `subprocess.run`

### 3. Context usage % in session modal

Transcript JSONL has `usage.input_tokens + usage.cache_read_input_tokens` in each `assistant` entry. Plan:
- Stop hook reads the last assistant entry, posts token count to `/api/stop`
- New `last_token_count` column on `sessions`
- Modal shows a progress bar; requires a model → context limit lookup table

### 4. "Thinking" session indicator

When Claude is mid-response, show a pulsing indicator in the dashboard rather than relying on the heartbeat timestamp.
- `PreToolUse` hook posts a `thinking=true` flag to `/api/touch`
- New `last_thinking_at` timestamp column on `sessions`
- Dashboard polls at 5s during active thinking window, falls back to normal interval

### 5. Offline hook queue

Heartbeats are silently dropped if the server is down when a hook fires.
- Hooks write to `~/.membridge/queue/<timestamp>.json` on `curl` failure
- Server drains the queue directory on startup

### 6. Ticket relationship links (replace flat `tickets` string)

Sessions can already be tagged with multiple tickets (`tickets` column, comma-separated IDs), but there's no way to say which one a session's activity actually belongs to when more than one is linked.

Design (from 2026-07-11 discussion):
- Reuse the existing `tickets` column but store JSON instead of a comma string: `[{"id": "ADO-123", "rel": "working_on"}, {"id": "ADO-456", "rel": "relates_to"}]`
- Relationship vocab kept small and MemBridge-native - `working_on` / `relates_to` to start - rather than mirroring Jira's and ADO's own (incompatible) link-type ontologies
- Exactly one `working_on` ticket allowed per session; enforced client- and server-side. This is what any future ticket-write-back command (e.g. posting a summary as a comment) reads to know where to post
- One-time data migration: existing comma-separated values become JSON with `rel: "relates_to"` for every entry (can't safely infer which was primary) - dashboard should surface sessions with tickets but no `working_on` pick
- UI: star/pin toggle per ticket tag; setting one clears the flag on any other tag for that session

Prerequisite for any Jira/ADO write-back automation (see `docs/ideas/` if that gets scoped out).

---

## Medium-term

### Drop Docker volume mount for static files
Blocked by item 1 (Drop Docker) - becomes a non-issue once the server runs natively. If Docker is kept, mount `./membridge/static:/app/membridge/static` to avoid rebuilding on every frontend change.

### GCS transcript archival
Sweep `~/.claude/projects/` and upload transcripts to GCS before Claude Code's auto-compaction discards them. Gives session state recovery and audit trail without relying on local disk.
- Trigger: Stop hook or scheduled cron
- Target: `gs://<bucket>/transcripts/<session-id>.jsonl`

### Auto sync_iterm_tabs
Run `sync_iterm_tabs.py` on a schedule (5 min via launchd) so tab names stay current without manual intervention. Currently the sync button in the UI is the only trigger.

---

## Future

### Multi-machine / cloud hosting
- Host on Cloud Run behind IAP for mobile read access
- Expose a minimal read-only API: recent sessions, resume IDs
- Multi-user: team members see each other's active sessions

### Launch and manage sessions from the UI
- `claude --resume <id>` from the dashboard
- New session in a named directory
- Temporal integration for long-running agent workflows

### Headless session reply via `claude --resume --print`

Allow replying to a waiting session from anywhere (dashboard, Telegram, phone) by driving Claude Code as a subprocess rather than injecting keystrokes into iTerm.

**How it works:**
```
POST /api/sessions/{id}/message  {"text": "yes, proceed"}
  → MemBridge calls: claude --resume <id> --print "<text>"
  → captures stdout
  → stores response as a session turn
  → SSE pushes to dashboard
```

No osascript, no Accessibility permission, no container latency. Hooks (`Stop`, `PreToolUse`) fire normally because it's the real Claude Code binary on the host. The repo and transcript are already on disk - nothing to mount.

**Trade-offs:**
- Response arrives only on completion (no streaming mid-turn) - acceptable for decision prompts
- `--dangerously-skip-permissions` needed to avoid interactive approval prompts in headless mode - caller must opt in explicitly
- iTerm session is bypassed; the headless turn doesn't appear in the iTerm history, only in MemBridge

**Path to Telegram integration:**
Once this works, wiring Telegram is straightforward - inbound Telegram message → `POST /api/sessions/{id}/message` → response back via `sendMessage`. See `docs/ideas/telegram-mobile-reply.md` for the full Telegram architecture.

**Effort:** Medium - `claude --print` subprocess wrapper, response capture, new DB turn type, SSE push.

---

---

See `docs/CHANGELOG.md` for completed work.
