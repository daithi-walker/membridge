# MemBridge

Local Claude Code session tracker. See README.md for full setup.

## Structure

```
claude_ui/          FastAPI app (Python)
  server.py         API routes + heartbeat/stop handlers
  db.py             SQLite helpers (sessions table)
  summariser.py     Vertex AI summary generation
  static/
    index.html      Dashboard HTML + CSS
    app.js          Dashboard JS (vanilla, no build step)

hooks/
  claude_ui_heartbeat.sh   UserPromptSubmit hook — POST /api/heartbeat
  claude_ui_stop.sh        Stop hook — POST /api/stop

scripts/
  focus_server.py   Host-side HTTP server (port 7843) for iTerm2 tab focus/rename
  backfill.py       Import historical sessions from ~/.claude/projects/
  install.sh        One-shot setup (hooks, launchd, Docker)
```

## Running locally

```bash
docker compose up -d          # main app (port 7842)
python3 scripts/focus_server.py &   # iTerm focus server (port 7843)
```

## Key design decisions

- **Docker for the main app** — keeps Python deps isolated; SQLite volume at `~/.claude-ui/sessions.db`
- **Host-side focus server** — osascript must run on the Mac host, not inside Linux Docker
- **Hooks fire in background** — `curl --max-time 3 ... &` so Claude is never blocked
- **Vertex AI** — uses ADC, not an API key; `AnthropicVertex(project_id=..., region="global")`
- **`notes` vs `summary`** — `summary` is auto-generated/brief; `notes` is a manual work log in the side panel

## Database

SQLite at `~/.claude-ui/sessions.db` (host volume, survives rebuilds).

Key columns: `session_id`, `cwd`, `project_name`, `git_branch`, `pid`, `first_seen`, `last_seen`, `prompt_count`, `summary`, `summary_source`, `notes`.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Anthropic API key for auto-summary (default provider) |
| `CLAUDE_SUMMARY_MODEL` | `claude-haiku-4-5-20251001` | Model for auto-summary |
| `CLAUDE_UI_DB` | `~/.claude-ui/sessions.db` | SQLite DB path (inside container: `/data/sessions.db`) |
| `CLAUDE_CODE_USE_VERTEX` | — | Set to `1` to use Vertex AI instead of Anthropic API |
| `ANTHROPIC_VERTEX_PROJECT_ID` | — | GCP project ID (Vertex only) |
| `CLOUD_ML_REGION` | `global` | Vertex AI region (Vertex only) |
