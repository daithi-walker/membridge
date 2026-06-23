# MemBridge Release Notes

Migration notes and breaking changes for each significant update. See `CHANGELOG.md` for the full feature history.

---

## 2026-06-23 — Drop Docker / Native Host Process

**Breaking change — requires manual migration on every machine.**

### What changed

MemBridge no longer runs in Docker. The server (`uvicorn`) now runs natively on the Mac host via a single launchd plist (`com.daihi.membridge`). The separate focus server (port 7843) is gone — focus/rename/pid endpoints are now part of the main server on port 7842.

### Migration steps

```bash
git pull
bash scripts/install.sh
```

`install.sh` will:
- Stop and remove the Docker container
- Remove the old `com.daihi.membridge-focus` launchd plist
- Create a Python venv at `.venv/` (editable install — static file changes are live)
- Load the new `com.daihi.membridge` plist on port 7842

### Other actions required

**1. Create `.env` if it doesn't exist:**
```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
```

**2. Fix bad cwd paths (if from the other machine backfill):**
```bash
sqlite3 ~/.membridge/sessions.db \
  "UPDATE sessions SET cwd = REPLACE(cwd, '/Users/david/walker/', '/Users/david.walker/') WHERE cwd LIKE '/Users/david/walker/%';"
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
launchctl kickstart -k gui/$(id -u)/com.daihi.membridge

# Health check
curl http://localhost:7842/api/sessions | python3 -c "import sys,json; s=json.load(sys.stdin); print(len(s), 'sessions')"
```

---

## 2026-06-23 — Notification hook + awaiting_input state machine

**No breaking changes — but `scripts/install.sh` must be re-run to register the new hook.**

### What changed

- `Notification` hook (`permission_prompt` matcher) — sets `awaiting_input` immediately when Claude asks mid-turn permission, not just on Stop
- `awaiting_input` DB column — drives 4-state focus button (green ◉ awaiting / orange ◉ working / amber ↩ resume / grey ⌘ idle)
- SSE push-refresh — dashboard updates instantly on heartbeat/stop; no more 30s lag for state changes
- `POST /api/sessions/{id}/push-summary` — `/membridge-summarize` now pushes text direct to DB
- Notification prefs in Settings modal — Pop-ups + Sound toggles (sound off by default)
- Header badge "◉ N awaiting input" — clickable, jumps to first awaiting row

### Migration steps

```bash
git pull
bash scripts/install.sh
```

`install.sh` will register the new `Notification` hook in `~/.claude/settings.json`. Restart Claude Code after running it to pick up the hook.

The `awaiting_input` DB column is added automatically on server start (idempotent migration).

---

## Earlier

No formal release notes — see `CHANGELOG.md` for full history.
