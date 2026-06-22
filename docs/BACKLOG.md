# MemBridge Backlog

Planned and future work, roughly ordered by priority.

---

## Near-term

### Settings modal
Gear icon in header opens a modal to configure:
- Active / idle / stale thresholds (defaults: active < 5 min, idle < 2 h, stale > 2 h)
- Auto-refresh interval
- Stored in a `settings` table in SQLite, served via `GET/PATCH /api/settings`

### Context usage % in dashboard
Show how full the context window is for each active session.
- Transcript JSONL contains `usage.input_tokens + usage.cache_read_input_tokens` in each `assistant` entry
- The `Stop` hook can read the last assistant entry and post token usage to `/api/stop`
- Display as a progress bar or percentage in the side panel
- Requires knowing the model's context window limit (look up by model ID)

### Offline hook queue
If the app is down when a hook fires, the heartbeat is silently dropped.
- Hooks write to `~/.claude-ui/queue/` on disk as JSON files when the POST fails
- A background thread in the server drains the queue on startup
- Low priority until the app is more production-hardened

---

## Medium-term

### GCS transcript archival (pre-compaction)
Periodically sweep `~/.claude/projects/` and upload transcripts to GCS before Claude Code's auto-compaction discards them.
- Triggered by the `Stop` hook or a cron job
- Stored at `gs://<bucket>/transcripts/<session-id>.jsonl`
- Enables session state recovery and audit
- Requires a GCS bucket and service account

### `/summarize` slash command
A Claude Code slash command that POSTs a detailed summary + next steps to `PATCH /api/sessions/{id}`.
- User types `/summarize` in Claude Code
- Claude reads the transcript and writes a structured work log
- Stored in the `notes` field, displayed in the side panel

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
