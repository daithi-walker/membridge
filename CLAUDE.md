# MemBridge

Local Claude Code session tracker. See README.md for full setup.

## Structure

```
membridge/          FastAPI app (Python)
  server.py         API routes + heartbeat/stop handlers
  db.py             SQLite helpers (sessions + settings tables)
  summariser.py     Anthropic API summary generation
  static/
    index.html      Dashboard HTML + CSS
    app.js          Dashboard JS (vanilla, no build step)

hooks/
  claude_ui_heartbeat.sh   UserPromptSubmit hook — POST /api/heartbeat (increments prompt_count)
  claude_ui_tool_use.sh    PreToolUse hook — POST /api/touch (updates last_seen, keeps session active during long responses)
  claude_ui_stop.sh        Stop hook — POST /api/stop (triggers auto-summary)

scripts/
  focus_server.py      Host-side HTTP server (port 7843) for iTerm2 tab focus/rename/PID check
  sync_iterm_tabs.py   Sync iTerm2 titleOverride aliases to DB (run after renaming tabs)
  _iterm2_query.py     Helper: reads all iTerm2 sessions via Python API (titleOverride)
  suggest_resumes.py   Post-reboot: match open iTerm2 tabs to DB sessions
  backfill.py          Import historical sessions from ~/.claude/projects/
  install.sh           One-shot setup (hooks, launchd, Docker)

docs/
  ARCHITECTURE.md   System design and data model
  BACKLOG.md        Planned features
```

## Running locally

```bash
docker compose up -d                     # main app (port 7842)
python3 scripts/focus_server.py &        # iTerm2 focus/rename server (port 7843)
```

The focus server is also registered as a launchd service:
```bash
launchctl load ~/Library/LaunchAgents/com.daihi.membridge-focus.plist
```

## Making changes

### Static files (index.html, app.js)
Static files are **baked into the Docker image** — a rebuild is required after every change:
```bash
docker compose build --no-cache && docker compose up -d
```
Then hard-refresh the browser (`Cmd+Shift+R`).

### Backend (server.py, db.py, summariser.py)
Same — rebuild Docker:
```bash
docker compose build --no-cache && docker compose up -d
```

### Focus server (scripts/focus_server.py)
Runs on the host, not in Docker. Restart it directly:
```bash
pkill -f focus_server.py
python3 scripts/focus_server.py &
# or via launchd:
launchctl kickstart -k gui/$UID/com.daihi.membridge-focus
```

### Hooks (hooks/*.sh)
No restart needed — hooks are shell scripts read fresh on each invocation.

### DB migrations
Add a new `ALTER TABLE` statement to `_MIGRATIONS` in `db.py`. Migrations run on Docker startup (idempotent). For the live DB without a rebuild:
```bash
sqlite3 ~/.membridge/sessions.db "ALTER TABLE sessions ADD COLUMN new_col TEXT;"
```

## Key design decisions

- **Docker for the main app** — keeps Python deps isolated; SQLite volume at `~/.membridge/sessions.db`
- **Host-side focus server** — `osascript` must run on the Mac host, not inside Linux Docker
- **Hooks fire in background** — `curl --max-time 3 ... &` so Claude is never blocked
- **Anthropic API** — uses `ANTHROPIC_API_KEY` for auto-summary; optionally Vertex AI via `CLAUDE_CODE_USE_VERTEX=1`
- **`notes` vs `summary`** — `summary` is auto-generated/brief; `notes` is a manual work log in the side panel
- **PID liveness** — `GET /pid/<pid>` on focus server; stale sessions with a live PID show as idle
- **iTerm2 titleOverride** — user-set tab aliases read via iTerm2 Python API; `sync_iterm_tabs.py` syncs them to DB

## Database

SQLite at `~/.membridge/sessions.db` (host volume, survives Docker rebuilds).

Key columns: `session_id`, `cwd`, `project_name`, `git_branch`, `pid`, `iterm_tab`, `iterm_session_uuid`, `first_seen`, `last_seen`, `prompt_count`, `summary`, `summary_source`, `notes`.

Settings in a separate `settings` table: `active_threshold_secs`, `idle_threshold_secs`, `refresh_interval_secs`.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Anthropic API key for auto-summary |
| `CLAUDE_SUMMARY_MODEL` | `claude-haiku-4-5-20251001` | Model for auto-summary |
| `MEMBRIDGE_DB` | `~/.membridge/sessions.db` | SQLite DB path (inside container: `/data/sessions.db`) |
| `CLAUDE_CODE_USE_VERTEX` | — | Set to `1` to use Vertex AI instead of Anthropic API |
| `ANTHROPIC_VERTEX_PROJECT_ID` | — | GCP project ID (Vertex only) |
| `CLOUD_ML_REGION` | `global` | Vertex AI region (Vertex only) |
| `ITERM2_PYTHON` | — | Path to iTerm2's bundled Python (for `sync_iterm_tabs.py` alias reading) |

### Setting ITERM2_PYTHON

Add to `~/.zshrc`:
```bash
export ITERM2_PYTHON=~/Library/"Application Support"/iTerm2/iterm2env-3.10.19/versions/3.14.0/bin/python3.14
```

Find the right path on your machine:
```bash
ls ~/Library/"Application Support"/iTerm2/iterm2env-*/versions/*/bin/python3.*
```
Pick the one that works: `"$ITERM2_PYTHON" -c "import iterm2; print('ok')"`

## iTerm2 requirements

1. iTerm2 with shell integration installed (`iTerm2 > Install Shell Integration`)
2. iTerm2 Python runtime installed (`Scripts > Manage > Install Python Runtime`)
3. `ITERM2_PYTHON` env var set (see above)

These are only needed for `sync_iterm_tabs.py` to read user-set tab aliases (titleOverride). The dashboard works without them; iTerm tab names will show the auto-generated AI summary title instead.

## Syncing tab aliases

After renaming an iTerm2 tab:
```bash
python3 ~/git/membridge/scripts/sync_iterm_tabs.py
```
Then click the ↻ refresh button in the dashboard.

The `--dry-run` flag shows what would change without writing to the DB.

## Gotcha — ITERM2_PYTHON not set after install

The focus server is managed by launchd (`com.daihi.membridge-focus`). launchd does **not** inherit shell env vars, so `ITERM2_PYTHON` from `~/.zshrc` is invisible to the process. The ↻ refresh button's tab sync will silently fall back to osascript TTY matching and tab aliases won't update.

**Fix:** `install.sh` now auto-detects and bakes `ITERM2_PYTHON` into the launchd plist. If you set up before this was fixed, update the plist manually:

```xml
<key>EnvironmentVariables</key>
<dict>
  <key>ITERM2_PYTHON</key>
  <string>/Users/<you>/Library/Application Support/iTerm2/iterm2env-3.10.19/versions/3.14.0/bin/python3.14</string>
</dict>
```

Find the right path: `ls ~/Library/"Application Support"/iTerm2/iterm2env-*/versions/3.14.0/bin/python3.14`

Then reload: `launchctl unload ~/Library/LaunchAgents/com.daihi.membridge-focus.plist && launchctl load ~/Library/LaunchAgents/com.daihi.membridge-focus.plist`
