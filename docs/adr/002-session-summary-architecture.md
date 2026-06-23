# ADR 002: Session Summary Architecture

**Date:** 2026-06-23  
**Status:** Accepted

## Context

We need to capture what each Claude Code session worked on. There are two distinct use cases:

1. **At-a-glance identity** — a short label visible in the session table without opening the modal
2. **History log** — a full audit trail of what happened over the lifetime of a session

Early versions stored a single `summary` column on the `sessions` table. This was overwritten on each auto-summary, losing history, and the same column was used for both the short label and the long narrative.

## Decision

### Two storage layers

**`sessions.description`** — short one-liner, updated only by `source="auto"` summaries. Format: `[bracketed phrase]`, e.g. `[Fix heartbeat dedup in server.py]`. This is what the table shows. Users can edit it directly; edits go straight to this column and do not create a history entry.

**`session_summaries`** — append-only log table. Every summary, regardless of source, gets a row here. Columns: `session_id`, `created_at`, `source`, `text`, `file_path`.

### Three summary sources

| Source | Trigger | Updates `description`? | Stored in history? |
|--------|---------|----------------------|-------------------|
| `auto` | Session stop hook → Claude haiku reads transcript | Yes | Yes |
| `skill` | `/membridge-summarize` slash command | No | Yes |
| `user` | Direct edit of description field in modal | No (writes direct) | No |

### `file_path` as dedup key

Both skill summaries and auto-summaries store a `file_path` for deduplication:

- **Skill summaries**: `file_path` = path to the `.md` file written by the command (e.g. `~/.membridge/summaries/<session-id>/2026-06-23-1430.md`). The 30s poller checks `summary_file_already_ingested(file_path)` before inserting.
- **Auto summaries**: `file_path` = `<transcript_path>:<file_size_bytes>`. This prevents re-summarising the same transcript snapshot when the Stop hook fires multiple times for the same session state.

## Consequences

- The `sessions.description` column is always the latest AI-generated one-liner; user edits overwrite it but aren't logged
- History grows over long sessions — no pruning currently implemented
- The dedup key `path:size` means a session that generates a new response (transcript grows) will get a new auto-summary entry on next stop — this is intentional
- If the transcript hasn't changed since the last stop event, no duplicate entry is created
