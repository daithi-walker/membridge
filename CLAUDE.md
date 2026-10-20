# MemBridge

Local Claude Code session tracker. See README.md for full setup.

## Structure

```
membridge/          FastAPI app (Python)
  server.py         API routes + heartbeat/stop handlers
  db.py             SQLite helpers (sessions, summaries, activity_events, tags, api_calls)
  summariser.py     Anthropic API summary generation
  focus.py          iTerm2 osascript helpers (focus, rename, pid, list)
  usage.py          Transcript -> api_calls ingest (per-call token usage, subagents)
  costs.py          Price API calls from pricing.toml; per-turn + per-session rollups
  pricing.toml      Claude list prices per model (edit, restart, re-run backfill_usage.py)
  static/
    index.html      Dashboard HTML + CSS
    app.js          Dashboard JS (vanilla, no build step)

hooks/
  claude_ui_heartbeat.sh   UserPromptSubmit hook — POST /api/heartbeat (incl. auth_mode)
  claude_ui_tool_use.sh    PreToolUse hook — POST /api/touch
  claude_ui_stop.sh        Stop hook — POST /api/stop (auto-summary + usage ingest)
  membridge_statusline.py  Claude Code statusLine (context, cache warmth, cost; stdin only, no server)

scripts/
  run.sh            Entrypoint for launchd — starts uvicorn on port 7842
  install.sh        One-shot setup (venv, launchd plist, hooks, slash commands)
  backfill.py       Import historical sessions from ~/.claude/projects/
  backfill_usage.py Ingest token usage + cost from existing transcripts

commands/
  membridge-summarize.md   /membridge-summarize slash command
  membridge-archive.md     /membridge-archive slash command
  membridge-context.md     /membridge-context slash command
  membridge-handoff.md     /membridge-handoff — handoff summary, then /clear + /membridge-context

docs/
  ARCHITECTURE.md      System design and data model
  CHANGELOG.md         Feature history (newest first)
  RELEASES.md          Migration notes for breaking changes
  BACKLOG.md           Planned features
  CODING_STANDARDS.md  Security, error handling, testing, and style rules
  COVERAGE.md          Test coverage baselines and improvement targets per release
  adr/                 Architecture Decision Records (001–014)

tests/
  test_db.py        DB unit tests (pytest, in-memory SQLite)
```

## After pulling new code

Always check `docs/RELEASES.md` for migration steps before running. If a release section exists for commits you just pulled, follow it before doing anything else — it may require re-running `install.sh` or manual DB changes.

Quick check:
```bash
git log --oneline origin/main..HEAD   # what you're about to pull
git diff HEAD..origin/main -- docs/RELEASES.md   # any new release sections
```

## Running locally

```bash
bash scripts/install.sh    # first time / after breaking changes
```

Server runs natively via launchd (`com.membridge`) on port 7842. No Docker.

```bash
launchctl kickstart -k gui/$(id -u)/com.membridge   # restart
tail -f /tmp/membridge.log                                  # logs
curl http://localhost:7842/api/sessions                     # health check
```

## Making changes

Before writing code, read `docs/CODING_STANDARDS.md` — it documents required patterns for security (AppleScript injection, XSS, SRI hashes), error handling (toast on save failure, task done-callbacks), DB conventions (TypedDict, migrations), and testing.

Run `uv run pytest` and `uv run ruff check .` before committing.

### Static files (index.html, app.js)
No rebuild needed — editable install means changes are live on browser refresh.

### Backend (server.py, db.py, summariser.py, focus.py)
Restart the server to pick up Python changes:
```bash
launchctl kickstart -k gui/$(id -u)/com.membridge
```

### Hooks (hooks/*.sh)
No restart needed — hooks are shell scripts read fresh on each invocation.

### DB migrations
Add a new `ALTER TABLE` statement to `_MIGRATIONS` in `db.py`. Migrations run on server startup (idempotent). For the live DB immediately:
```bash
sqlite3 ~/.membridge/sessions.db "ALTER TABLE sessions ADD COLUMN new_col TEXT;"
```

## Release conventions

When shipping a significant change:

1. **CHANGELOG.md** — add a bullet under the current month section (newest first). Keep it short: feature/fix in one line.
2. **RELEASES.md** — add a dated section only when there are breaking changes or migration steps required on other machines. Include: what changed, how to migrate, and any one-off SQL/commands needed.
3. **ADR** — add `docs/adr/NNN-title.md` when a non-obvious architectural decision is made that should be documented for future reference.

## Key design decisions

- **Native host process** — uvicorn runs directly on macOS via launchd; no Docker. osascript/iTerm2 calls work directly.
- **Editable install** — `uv pip install -e .` so static file changes are live without reinstalling.
- **focus.py** — all osascript logic (focus, rename, pid_alive, list) lives here; server imports it directly.
- **Hooks fire in background** — `curl --max-time 3 ... &` so Claude is never blocked.
- **Anthropic API** — uses `ANTHROPIC_API_KEY` for auto-summary.
- **Auto-summary dedup** — Stop hook checks `last_auto_summary_text()` before inserting; same text is skipped even when transcript grows.
- **session_summaries table** — append-only log; never overwrites. Auto/skill/user sources tracked separately.
- **Cost from transcripts (ADR 014)** — on every Stop, `usage.ingest_session` re-parses the session transcript + `subagents/*.jsonl` into `api_calls`, one row per API call keyed by (message id, request id) because Claude Code repeats `usage` on every content block. Cost is list price from `pricing.toml`, set at ingest; billing class comes from `auth_mode` (`subscription` = API-equivalent, NULL = unknown, anything else = billed). Vertex calls are detected from `msg_vrtx_` ids. Estimate covers this machine's transcripts only.

## Database

SQLite at `~/.membridge/sessions.db` (survives reinstalls).

Key columns: `session_id`, `cwd`, `project_name`, `git_branch`, `pid`, `iterm_tab`, `iterm_session_uuid`, `first_seen`, `last_seen`, `prompt_count`, `summary`, `summary_source`, `notes`, `archived`, `starred`.

`sessions.auth_mode` (vertex | bedrock | foundry | api | subscription) is set by the heartbeat hook from Claude Code's environment. `api_calls` holds per-call token counts and `cost_usd`; it has no FK to `sessions` because backfilled transcripts can predate the session row.

Settings in a separate `settings` table: `active_threshold_secs`, `idle_threshold_secs`, `refresh_interval_secs`.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Anthropic API key for auto-summary |
| `CLAUDE_SUMMARY_MODEL` | `claude-haiku-4-5-20251001` | Model for auto-summary |
| `MEMBRIDGE_DB` | `~/.membridge/sessions.db` | SQLite DB path |

Copy `.env.example` → `.env` and set `ANTHROPIC_API_KEY`.
