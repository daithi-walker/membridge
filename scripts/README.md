# Scripts

## install.sh

One-time setup: builds the Docker image, registers Claude Code hooks, and installs the launchd service.

```bash
bash scripts/install.sh
```

After running, the dashboard is at http://localhost:7842 and starts automatically at login via OrbStack/Docker + launchd.

## backfill.py

Imports historical sessions from existing `~/.claude/projects/` transcripts into the DB.
Run this once after install to populate past sessions, or any time you want to catch up.

```bash
# Dry run — see what would be imported
python scripts/backfill.py --dry-run

# Import all sessions from the last 30 days
python scripts/backfill.py --days 30

# Import everything (can be slow for large history)
python scripts/backfill.py

# Also generate Vertex AI summaries for sessions missing one
python scripts/backfill.py --days 30 --summarise

# Skip very short sessions (default: skip < 2 turns)
python scripts/backfill.py --min-turns 5
```

**What it imports:**
- `session_id`, `cwd`, `project_name` from the transcript path and content
- `first_seen` / `last_seen` from user-turn timestamps
- `prompt_count` of real human turns
- Claude's `ai-title` as the initial summary (shown with `[brackets]`)

**What it can't import:**
- Git branch (not stored in transcripts)
- iTerm tab name (not stored in transcripts)

These will be filled in naturally as you resume and use sessions.

**Env vars:**
- `MEMBRIDGE_DB` — path to SQLite DB (default: `~/.membridge/sessions.db`)
