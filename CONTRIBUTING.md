# Contributing

## Setup

```bash
git clone https://github.com/daithi-walker/membridge.git
cd membridge
cp .env.example .env   # add ANTHROPIC_API_KEY
bash scripts/install.sh
```

## Making changes

### Static files (`membridge/static/`)
Changes are live on browser refresh - no restart needed (editable install).

### Python (`membridge/`)
Restart the server after changes:
```bash
launchctl kickstart -k gui/$(id -u)/com.membridge
```

### Hooks (`hooks/*.sh`)
No restart needed - hooks are read fresh on each invocation.

### DB migrations
Add a new entry to `_MIGRATIONS` in `db.py`. Migrations run on startup and are idempotent.

## Before submitting a PR

```bash
uv run pytest          # tests must pass
uv run ruff check .    # no lint errors
```

Tests use in-memory SQLite - no setup required.

## Scope

MemBridge is intentionally macOS-only (osascript, iTerm2). PRs that introduce Linux/Windows support are welcome but must not break the macOS integration path.

Features that require a cloud backend, external accounts, or break the single-machine model are out of scope.
