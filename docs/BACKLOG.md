# MemBridge Backlog

Planned and future work, roughly ordered by priority.

---

## Near-term

### Tests — HIGHEST PRIORITY
No automated tests exist. Need pytest coverage for:
- Heartbeat upsert (new vs existing session)
- Status computation (active/idle/stale/PID-alive override)
- `add_summary()` / `get_summaries()` / `summary_file_already_ingested()`
- Settings CRUD
- Summary file poller (mock filesystem, verify dedup by file_path)
- `/api/sessions/{id}/summarise` endpoint (mock `_generate_summary`)
- Focus server `/pid/<pid>` endpoint
- `sync_iterm_tabs.py` dry-run output (mock iTerm2 API response)

### Mount static files as Docker volume
Static files are currently baked into the image — every frontend change requires `docker compose build`. Mounting `claude_ui/static/` as a volume would allow live edits without rebuilding.

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

---

## Completed

- ✅ Session registration via UserPromptSubmit hook
- ✅ Auto-summary on Stop via Claude haiku (Anthropic + Vertex)
- ✅ Dashboard with active/idle/stale status, git branch, prompt count
- ✅ Project filter
- ✅ Session modal (detail view: metadata, summary, notes, history)
- ✅ Focus button (iTerm2 integration, osascript)
- ✅ iTerm tab name column in main table
- ✅ Stale UUID auto-clear in sync_iterm_tabs.py
- ✅ Copy resume command
- ✅ Backfill from ~/.claude/projects/
- ✅ Dark/light theme toggle
- ✅ PreToolUse hook → /api/touch (keeps session active during long responses)
- ✅ session_summaries append-only log table
- ✅ History UI in modal — always visible, grouped by file, collapsible
- ✅ Markdown rendering in summary and history entries
- ✅ /membridge-summarize slash command (Bash heredoc, dynamic path)
- ✅ Summary file poller (30s, dedup by file_path)
- ✅ Delete session endpoint
- ✅ Re-summarise endpoint
- ✅ Vertex AI ADC mount in Docker
- ✅ Rename claude-ui → membridge
- ✅ Multi-select project filter with All/None buttons (fixed inversion bug)
- ✅ Archive session feature (toggle via modal button or /membridge-archive command)
- ✅ /membridge-archive slash command (toggles archive via PATCH API)
- ✅ /membridge-recall slash command (list recent sessions or dump summaries by prefix)
- ✅ /membridge-summarize delta awareness (fetches prior summaries, only covers new work)
