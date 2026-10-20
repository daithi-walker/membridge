# MemBridge

A local macOS app that tracks your Claude Code sessions - what each one is working on, how long it has been running, and how to get back to it.

## The problem

When you run Claude Code across many iTerm2 tabs over days or weeks, you lose track of which session is doing what. `claude --resume <id>` is powerful, but only if you know which ID to use.

## What it does

- **Auto-registers sessions** via Claude Code hooks - no manual setup per session
- **Auto-summarises** what each session worked on when you stop, using Claude Haiku
- **Dashboard** - active / idle / stale status, git branch, prompt count, last active time
- **Focus button** - raises the right iTerm2 tab, or opens a new tab with `claude --resume <id>`
- **Push notifications** - macOS alert when Claude stops and needs your attention
- **Session links** - bidirectionally link related sessions and navigate between them
- **Session backups (sesh)** - opt in per project to snapshot a session's transcripts on every Stop via the [`sesh`](https://github.com/m-gharibi/sesh) CLI; resume then prefers `sesh resume`. MemBridge owns metadata; sesh owns content preservation and full-text search across saved sessions
- **Slash commands** - summarise, rename, note, link, and load context from inside Claude
- **Notes field** - per-session work log, auto-saved
- **Context meter** - current context size per session (amber > 200k, red > 500k), prompt-cache warm/cold, and what the next turn costs to re-read the context; plus a Claude Code status line showing the same
- **Cost estimates** - per-session and per-turn cost from the token usage Claude Code records in each transcript (subagents included), priced at list price from `membridge/pricing.toml`. Billed spend (Vertex, Bedrock, API key) is shown plainly; subscription usage shows as an italic API-equivalent figure
- **Backfill** - import existing session history from `~/.claude/projects/`
- **Dark / light theme**, persisted in localStorage

## Architecture

```
Claude Code (any session, any project)
  UserPromptSubmit hook  →  POST localhost:7842/api/heartbeat   registers session, increments prompt count
  PreToolUse hook        →  POST localhost:7842/api/touch        keeps last_seen fresh during long responses
  Stop hook              →  POST localhost:7842/api/stop         auto-summary, usage/cost ingest, sesh snapshot (if opted in)
  Notification hook      →  POST localhost:7842/api/notification fires macOS alert when Claude needs input

localhost:7842  FastAPI + SQLite   runs natively via launchd (com.membridge)
~/.membridge/sessions.db           SQLite DB, survives reinstalls
```

All hooks run in the background (`curl ... &`) - Claude Code is never blocked.

## Requirements

- macOS (osascript / iTerm2 integration)
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) - Python package manager
- An Anthropic API key (for auto-summary via Claude Haiku)

## Setup

```bash
git clone https://github.com/daithi-walker/membridge.git
cd membridge
cp .env.example .env          # add your ANTHROPIC_API_KEY
bash scripts/install.sh
```

The installer:
- Creates a Python venv via `uv` and installs the package
- Writes a launchd plist (`com.membridge`) and starts the server on port 7842
- Registers the four Claude Code hooks in `~/.claude/settings.json`
- Installs slash commands to `~/.claude/commands/`

Then restart Claude Code so the hooks take effect.

## Dashboard

Open **[http://localhost:7842](http://localhost:7842)** in your browser.

Sessions are colour-coded by status:

| Status | Condition |
|--------|-----------|
| active | Last seen < 5 minutes ago |
| idle   | Last seen 5 min - 2 hours, or PID still alive |
| stale  | Last seen > 2 hours and PID is dead |

Click any row to open the side panel: full metadata, usage and cost (with a per-turn breakdown), editable summary, notes, and linked sessions.

The **Cost** column is an estimate at list price from transcript token counts, for transcripts on this machine only. It excludes negotiated discounts and regional Vertex pricing (~10% above `global`). Hover a cell for call count and list vs billed.

The **Context** column is the size of the session's latest main-thread call. Every turn re-reads all of it, and once the prompt cache goes cold (5 minutes idle) the next turn rewrites all of it at cache-write price. Hover for warmth and next-turn cost. Big, idle contexts are the cue to `/compact` at a stopping point or `/membridge-handoff`.

### Status line

`install.sh` configures `hooks/membridge_statusline.py` as the Claude Code status line if you don't already have one: `Opus 5.5 · ctx 312k (31%) · cache warm · $7.26`. It reads only the JSON Claude Code passes it, so it works without the server. To use it alongside an existing status line, call the script from yours.

## Slash commands

| Command | What it does |
|---------|--------------|
| `/membridge-summarize` | Generate and push a summary mid-session |
| `/membridge-rename` | Set a short description for the current session |
| `/membridge-note <text>` | Inject a freeform note into session history |
| `/membridge-link` | Link the current session to another by ID prefix |
| `/membridge-context` | Load summaries, notes, and links back into Claude |
| `/membridge-archive` | Toggle archive to hide a session from the dashboard |
| `/membridge-handoff` | Save a handoff summary so you can `/clear` and continue via `/membridge-context <prefix>` in a small context |

## Configuration

Set in `.env` or as environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | - | Required for auto-summary |
| `CLAUDE_SUMMARY_MODEL` | `claude-haiku-4-5-20251001` | Model used for summaries |
| `MEMBRIDGE_DB` | `~/.membridge/sessions.db` | SQLite DB path |

Thresholds (active/idle/stale) and the dashboard refresh interval are configurable via the Settings modal in the UI.

## Backfill historical sessions

```bash
uv run python scripts/backfill.py --dry-run --days 30   # preview
uv run python scripts/backfill.py --days 30              # import
```

Load token usage and cost for existing transcripts (safe to re-run; re-run after editing `membridge/pricing.toml` to reprice):

```bash
uv run python scripts/backfill_usage.py                         # Vertex/Bedrock machine
uv run python scripts/backfill_usage.py --auth-mode subscription  # direct Anthropic history: subscription (or api)
```

New sessions record their own auth mode via the heartbeat hook; `--auth-mode` only classifies older history. Vertex calls are recognised from their message ids.

## Development

```bash
uv run pytest          # run tests
uv run ruff check .    # lint
```

Before your first commit, install the disclosure/secret guards (see [Coding Standards](docs/CODING_STANDARDS.md#disclosure-protection-public-repo)):

```bash
uv run --extra dev pre-commit install
cp .disclosure-denylist.example.txt .disclosure-denylist.txt   # then add client/project names
```

Restart the server after Python changes:
```bash
launchctl kickstart -k gui/$(id -u)/com.membridge
```

Static file changes (`membridge/static/`) are live on browser refresh - no restart needed.

## Troubleshooting

**Server won't restart / crash-loops after a `git pull` (new code not loaded, schema migration didn't run).**

Symptoms: the dashboard responds on `http://localhost:7842` but is serving *old* code (e.g. a new table like `activity_events` is missing from `~/.membridge/sessions.db`); `launchctl print gui/$(id -u)/com.membridge` shows a large `runs =` count with `last exit code = 1`.

Root cause: a stale, long-lived `uvicorn` process (often started manually or by a previous session, days/weeks old) is still holding port 7842. launchd's managed process then can't bind, exits 1, and `KeepAlive` retries forever - so the port stays owned by the old code and `kickstart -k` never wins. `init_db()` only runs at startup, so the schema is whatever the stale process created.

Fix - evict the stale holder, then reload the job from a clean state:
```bash
# 1. Find and hard-kill whatever holds the port (SIGTERM is often ignored - use -9)
lsof -nP -iTCP:7842 -sTCP:LISTEN            # note the PID
kill -9 <pid>

# 2. Reload the launchd job to clear accumulated throttle/crash-loop state
launchctl bootout   gui/$(id -u)/com.membridge                       || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.membridge.plist
launchctl kickstart gui/$(id -u)/com.membridge

# 3. Verify: fresh process, new code, table present
launchctl print gui/$(id -u)/com.membridge | grep -E 'state =|runs =|pid ='
tail -f /tmp/membridge.log                  # should show "Application startup complete"
sqlite3 ~/.membridge/sessions.db '.tables'  # confirm expected tables exist
```

Notes:
- `init_db()` is idempotent (`CREATE TABLE IF NOT EXISTS` + guarded `ALTER`s). If you only need the schema created/migrated without a full restart, run it directly: `.venv/bin/python -c "from membridge import db; db.init_db()"`.
- The `sqlite3` CLI does **not** enable `PRAGMA foreign_keys` by default, so `DELETE FROM sessions ...` there will **not** cascade to `activity_events`/`session_summaries`. The app's own connection sets the pragma, so deletes via the API/dashboard cascade correctly - only manual CLI deletes leave orphans.

## Docs

- [Architecture](docs/ARCHITECTURE.md) - system diagram, component responsibilities, data model
- [Changelog](CHANGELOG.md) - feature history
- [Releases](docs/RELEASES.md) - migration notes for breaking changes
- [Backlog](docs/BACKLOG.md) - planned features

## License

MIT - see [LICENSE](LICENSE).
