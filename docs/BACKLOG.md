# MemBridge Backlog

Planned and future work, roughly ordered by priority.

---

## Near-term

### Feature tests
No automated tests exist. Need pytest coverage for:
- Heartbeat upsert (new vs existing session)
- Status computation (active/idle/stale/PID-alive override)
- Settings CRUD
- Focus server `/pid/<pid>` endpoint
- `sync_iterm_tabs.py` dry-run output

### Mount static files as Docker volume
Static files are currently baked into the image — every frontend change requires `docker compose build --no-cache`. Mounting `claude_ui/static/` as a volume would allow live edits without rebuilding.

```yaml
volumes:
  - "${HOME}/.membridge:/data"
  - "./claude_ui/static:/app/claude_ui/static"
```

### Context usage % in dashboard
Show how full the context window is for each active session.
- Transcript JSONL contains `usage.input_tokens + usage.cache_read_input_tokens` in each `assistant` entry
- The `Stop` hook can read the last assistant entry and post token usage to `/api/stop`
- Display as a progress bar or percentage in the side panel
- Requires knowing the model's context window limit (look up by model ID)

### "Waiting on response" status
When Claude is generating a response, highlight the session differently in the dashboard.
- `PreToolUse` hook sends a "thinking" heartbeat with a `thinking=true` flag
- New DB column or a separate timestamp (`last_thinking_at`)
- Dashboard shows a pulsing indicator while `thinking` and `last_thinking_at` is recent
- Requires faster poll during that window (~5s)

### Offline hook queue
If the app is down when a hook fires, the heartbeat is silently dropped.
- Hooks write to `~/.membridge/queue/` on disk as JSON files when the POST fails
- A background thread in the server drains the queue on startup

---

## Medium-term

### GCS transcript archival (pre-compaction)
Periodically sweep `~/.claude/projects/` and upload transcripts to GCS before Claude Code's auto-compaction discards them.
- Triggered by the `Stop` hook or a cron job
- Stored at `gs://<bucket>/transcripts/<session-id>.jsonl`
- Enables session state recovery and audit

### `/summarize` slash command
A Claude Code slash command that POSTs a detailed summary + next steps to `PATCH /api/sessions/{id}`.
- User types `/summarize` in Claude Code
- Claude reads the transcript and writes a structured work log
- Stored in the `notes` field, displayed in the side panel

### Auto sync_iterm_tabs
Run `sync_iterm_tabs.py` periodically (e.g. every 5 min via launchd) so tab aliases update without manual intervention. Requires `ITERM2_PYTHON` to be set and iTerm2 Python runtime installed.

---

## Future

### Mobile / cloud hosting
- Host the app on a small VM or Cloud Run instance behind auth (IAP or simple JWT)
- Expose a read-only API for mobile — see recent sessions, copy resume IDs
- Session sharing: multiple team members can view each other's active work

### Submit and manage sessions from UI
- Launch `claude --resume <id>` or a new session from the dashboard
- Potentially run sessions in Docker containers managed by the UI
- Temporal integration for long-running agent workflows
