# MemBridge Release Notes

Migration notes and breaking changes for each significant update. See `CHANGELOG.md` for the full feature history.

---

## 2026-07-22 - Fix: sessions no longer flip to idle during long tool calls

**Migration: restart the server so the `working` column migration runs.**

```bash
git pull
launchctl kickstart -k gui/$(id -u)/com.membridge
```

No `install.sh` / hook changes required — the migration is idempotent and runs on startup.

### What changed

- New `working` column on `sessions`: set on heartbeat (prompt submitted) and on tool-start (`/api/touch` with `thinking: true`), cleared on Stop/Notification.
- `/api/sessions` now forces status `active` when a session is mid-turn (`working=1`) and its PID is alive, even if `last_seen` has aged past `active_threshold_secs`.
- Fixes the bug where a session running a single long tool call (or generating a long response) slid to `idle` after 5 min, then snapped back to `active` on the next tool call. The `working` flag is gated on PID-alive, so a crashed session (flag never cleared) still ages out correctly.

---

## 2026-07-15 - Machine-agnostic config (v0.2.1)

**Migration: re-run `install.sh` (launchd service renamed to `com.membridge`).**

- launchd service renamed to `com.membridge`. Re-run `bash scripts/install.sh`. If an older MemBridge service is still loaded (it will fight for port 7842), unload and delete its plist from `~/Library/LaunchAgents/` first.
- The server honours `MEMBRIDGE_HOST` / `MEMBRIDGE_PORT`; hooks POST to `MEMBRIDGE_URL` (default `http://localhost:7842`). Defaults are unchanged, so no action is needed unless you override them.
- Removed hardcoded home-dir paths from tests, comments, and docs.

---

## 2026-07-12 - Thinking pulse (v0.2.0)

**Re-run `install.sh` to register the new `PostToolBatch` hook, then restart Claude Code.**

### What changed

- `PreToolUse` hook now sends `thinking: true` + `tool_name` to `/api/touch`; server broadcasts a `tool_start` SSE event to connected dashboards
- New `hooks/claude_ui_tool_batch.sh` (`PostToolBatch` event) broadcasts `tool_end` SSE + refresh when a tool batch completes
- `Stop` hook also broadcasts `tool_end` to clear any stale thinking state
- Dashboard: active session's green ◉ button pulses at 0.55s (vs 1.2s idle) with green fill while a tool is executing; hover shows `Using Bash…` / `Using Edit…` etc.; no DB change — purely ephemeral client-side state

### Steps on each machine

```bash
git pull
bash scripts/install.sh   # registers PostToolBatch hook in ~/.claude/settings.json
```

Restart Claude Code to activate the new `PostToolBatch` hook. Browser refresh is enough to pick up the CSS/JS changes (static files are live).

---

## 2026-06-26 - /slides skill + presentations

**No migration required.**

### What changed

- **`/slides` skill** - new reusable slash command that generates a self-contained, keyboard-navigable HTML slide deck from a topic or MemBridge session history (`--from-session`). Supports 6 brand themes across 3 brands (DSS, Biobase, Edge) in dark and light variants.
- **`docs/presentations/`** - new folder containing the MemBridge demo deck, a brand theme comparison page, and `slides-theme-example.css` (starter stylesheet with variables reference).
- **Theme CSS files are local-only** - `~/.claude/styles/slides-<brand>.css` files are not committed to the repo. Use `slides-theme-example.css` as a guide to create a brand theme on each machine.

### Steps on each machine

```bash
git pull
bash scripts/install.sh   # installs /slides into ~/.claude/commands/
```

Then create a theme file for your brand:
```bash
cp docs/presentations/slides-theme-example.css ~/.claude/styles/slides-mybrand.css
# edit the variables to match your brand colours
```

Generate a deck:
```
/slides <topic> --style mybrand
/slides --from-session          # build from current session history
```

---

## 2026-06-25 - Session links, /membridge-link, /membridge-rename

**No migration required.** The `session_links` table is created automatically by `init_db()` on first server start after pulling. No manual SQL or `install.sh` re-run needed.

### What changed

- **Session links** - bidirectional linking between sessions via a new `session_links` join table. Link chips appear in the session panel; 🔗 indicator in the rightmost table column.
- **`/membridge-link`** - new slash command to link the current session to another by ID prefix, or list existing links with no argument.
- **`/membridge-rename`** - replaces `/membridge-tag`. Same action (set session description), clearer name. Update any saved workflows or habits that used `/membridge-tag`.

### Steps on each machine

```bash
git pull
launchctl kickstart -k gui/$(id -u)/com.membridge  # picks up new API routes
```

Install the new/renamed slash commands:
```bash
cp commands/membridge-link.md ~/.claude/commands/
cp commands/membridge-rename.md ~/.claude/commands/
cp commands/membridge-note.md ~/.claude/commands/
rm -f ~/.claude/commands/membridge-tag.md
```

Clear stale localStorage column widths in the dashboard (new `col-links` column added):
```
localStorage.removeItem('membridge_col_widths')
```
(paste in DevTools console, then refresh)

---

## 2026-06-23 - Drop Docker / Native Host Process

**Breaking change - requires manual migration on every machine.**

### What changed

MemBridge no longer runs in Docker. The server (`uvicorn`) now runs natively on the Mac host via a single launchd plist (`com.membridge`). The separate focus server (port 7843) is gone - focus/rename/pid endpoints are now part of the main server on port 7842.

### Migration steps

```bash
git pull
bash scripts/install.sh
```

`install.sh` will:
- Stop and remove the Docker container
- Remove the old `com.membridge-focus` launchd plist
- Create a Python venv at `.venv/` (editable install - static file changes are live)
- Load the new `com.membridge` plist on port 7842

### Other actions required

**1. Create `.env` if it doesn't exist:**
```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
```

**2. Fix bad cwd paths (if from the other machine backfill):**
```bash
# Replace <old> / <new> with the mismatched home-dir prefixes for your machines.
sqlite3 ~/.membridge/sessions.db \
  "UPDATE sessions SET cwd = REPLACE(cwd, '/Users/<old>/', '/Users/<new>/') WHERE cwd LIKE '/Users/<old>/%';"
```

**3. Install slash commands (handled by `install.sh`, but verify):**
```bash
ls ~/.claude/commands/membridge-*.md
```

### Logs

```bash
tail -f /tmp/membridge.log
```

### If something goes wrong

```bash
# Check server status
launchctl list | grep membridge

# Restart
launchctl kickstart -k gui/$(id -u)/com.membridge

# Health check
curl http://localhost:7842/api/sessions | python3 -c "import sys,json; s=json.load(sys.stdin); print(len(s), 'sessions')"
```

---

## 2026-06-24 - /membridge-tag slash command

**No breaking changes - run `install.sh` to get the new command, or copy manually:**
```bash
cp commands/membridge-tag.md ~/.claude/commands/membridge-tag.md
```
Then restart Claude Code to pick it up.

### What changed

- `/membridge-tag <text>` - sets the session description instantly via `PATCH /api/sessions/{id}`
- Use it at the start of a session to label what you're working on before auto-summary kicks in
- Claude can also call it to self-tag its own sessions

---

## 2026-06-23 - UI cleanup + session ID column + bug fixes

**No breaking changes - `git pull` is sufficient.**

### What changed

- Activity column removed (was iTerm tab title, rarely useful in the table - still in modal)
- Vestigial `›` chevron column removed
- Description column now fills remaining table width
- Session ID split into its own column (8-char prefix); click copies full UUID
- Modal: copy button (⎘) next to full session ID
- Focus button: `?` for decision prompts, `✎` for text input, `◉` working - distinguished via `last_stop_reason`
- Bug fix: Notification hook reason no longer overwritten by subsequent empty Stop reason
- Bug fix: answering a decision prompt now immediately clears `awaiting_input` (transitions to working)
- Ideas catalog added at `docs/ideas/`

### Migration steps

```bash
git pull
```

Server restart not required - static file changes are live.

---

## 2026-06-23 - Notification hook + awaiting_input state machine

**No breaking changes - but `scripts/install.sh` must be re-run to register the new hook.**

### What changed

- `Notification` hook (`permission_prompt` matcher) - sets `awaiting_input` immediately when Claude asks mid-turn permission, not just on Stop
- `awaiting_input` DB column - drives 4-state focus button (green ◉ awaiting / orange ◉ working / amber ↩ resume / grey ⌘ idle)
- SSE push-refresh - dashboard updates instantly on heartbeat/stop; no more 30s lag for state changes
- `POST /api/sessions/{id}/push-summary` - `/membridge-summarize` now pushes text direct to DB
- Notification prefs in Settings modal - Pop-ups + Sound toggles (sound off by default)
- Header badge "◉ N awaiting input" - clickable, jumps to first awaiting row

### Migration steps

```bash
git pull
bash scripts/install.sh
```

`install.sh` will register the new `Notification` hook in `~/.claude/settings.json`. Restart Claude Code after running it to pick up the hook.

The `awaiting_input` DB column is added automatically on server start (idempotent migration).

---

## Earlier

No formal release notes - see `CHANGELOG.md` for full history.
