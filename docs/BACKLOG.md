# MemBridge Backlog

Planned work, ordered by priority within each tier. See `docs/adr/` for the decisions behind items marked with an ADR reference.

---

## Near-term

### 1. Drop Docker — migrate to native host process
**Priority: High** | ADR 004

Docker was chosen for iteration speed but is the wrong runtime for a tool that needs deep macOS integration. The Docker/host split (two launchd plists, volume-mounted credentials, `host.docker.internal` network hop) adds complexity that compounds every other near-term item.

Migration path:
- Run uvicorn directly on the host via a single launchd plist
- Move ADC credential handling to native env var (`GOOGLE_APPLICATION_CREDENTIALS`)
- Consolidate focus server into the main process — no more split
- Update `scripts/install.sh` to manage a venv instead of Docker

Unblocks: static file live-reload, credential cleanup, simpler install.

### 2. Test suite
**Priority: High**

No automated tests exist. Cover these in rough order:

- `db.py`: heartbeat upsert (new vs existing), `add_summary()`, `summary_file_already_ingested()`, dedup key format (`path:size`), settings CRUD, `set_archived()`
- `server.py`: status computation (active/idle/stale, PID-alive override), auto-summary dedup (same transcript size = skip, grown = new entry), PATCH endpoint field routing
- File poller: mock filesystem, verify dedup prevents double-ingest
- Focus server: `/pid/<pid>` alive check

### 3. Context usage % in session modal

Transcript JSONL has `usage.input_tokens + usage.cache_read_input_tokens` in each `assistant` entry. Plan:
- Stop hook reads the last assistant entry, posts token count to `/api/stop`
- New `last_token_count` column on `sessions`
- Modal shows a progress bar; requires a model → context limit lookup table

### 4. "Thinking" session indicator

When Claude is mid-response, show a pulsing indicator in the dashboard rather than relying on the heartbeat timestamp.
- `PreToolUse` hook posts a `thinking=true` flag to `/api/touch`
- New `last_thinking_at` timestamp column on `sessions`
- Dashboard polls at 5s during active thinking window, falls back to normal interval

### 5. Offline hook queue

Heartbeats are silently dropped if the server is down when a hook fires.
- Hooks write to `~/.membridge/queue/<timestamp>.json` on `curl` failure
- Server drains the queue directory on startup

---

## Medium-term

### Drop Docker volume mount for static files
Blocked by item 1 (Drop Docker) — becomes a non-issue once the server runs natively. If Docker is kept, mount `./claude_ui/static:/app/claude_ui/static` to avoid rebuilding on every frontend change.

### GCS transcript archival
Sweep `~/.claude/projects/` and upload transcripts to GCS before Claude Code's auto-compaction discards them. Gives session state recovery and audit trail without relying on local disk.
- Trigger: Stop hook or scheduled cron
- Target: `gs://<bucket>/transcripts/<session-id>.jsonl`

### Auto sync_iterm_tabs
Run `sync_iterm_tabs.py` on a schedule (5 min via launchd) so tab names stay current without manual intervention. Currently the sync button in the UI is the only trigger.

---

## Future

### Multi-machine / cloud hosting
- Host on Cloud Run behind IAP for mobile read access
- Expose a minimal read-only API: recent sessions, resume IDs
- Multi-user: team members see each other's active sessions

### Launch and manage sessions from the UI
- `claude --resume <id>` from the dashboard
- New session in a named directory
- Temporal integration for long-running agent workflows

---

See `docs/CHANGELOG.md` for completed work.
