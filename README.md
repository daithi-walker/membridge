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
- **Slash commands** - summarise, rename, note, link, and load context from inside Claude
- **Notes field** - per-session work log, auto-saved
- **Backfill** - import existing session history from `~/.claude/projects/`
- **Dark / light theme**, persisted in localStorage

## Architecture

```
Claude Code (any session, any project)
  UserPromptSubmit hook  →  POST localhost:7842/api/heartbeat   registers session, increments prompt count
  PreToolUse hook        →  POST localhost:7842/api/touch        keeps last_seen fresh during long responses
  Stop hook              →  POST localhost:7842/api/stop         triggers auto-summary
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

Click any row to open the side panel: full metadata, editable summary, notes, and linked sessions.

## Slash commands

| Command | What it does |
|---------|--------------|
| `/membridge-summarize` | Generate and push a summary mid-session |
| `/membridge-rename` | Set a short description for the current session |
| `/membridge-note <text>` | Inject a freeform note into session history |
| `/membridge-link` | Link the current session to another by ID prefix |
| `/membridge-context` | Load summaries, notes, and links back into Claude |
| `/membridge-archive` | Toggle archive to hide a session from the dashboard |

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

## Development

```bash
uv run pytest          # run tests
uv run ruff check .    # lint
```

Restart the server after Python changes:
```bash
launchctl kickstart -k gui/$(id -u)/com.membridge
```

Static file changes (`membridge/static/`) are live on browser refresh - no restart needed.

## Docs

- [Architecture](docs/ARCHITECTURE.md) - system diagram, component responsibilities, data model
- [Changelog](CHANGELOG.md) - feature history
- [Releases](docs/RELEASES.md) - migration notes for breaking changes
- [Backlog](docs/BACKLOG.md) - planned features

## License

MIT - see [LICENSE](LICENSE).
