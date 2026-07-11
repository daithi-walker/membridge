# ADR 005: Slash Command Writes Files, Not Direct API Calls

**Date:** 2026-06-23  
**Status:** Accepted

## Context

The `/membridge-summarize` slash command needs to get a summary from Claude into the MemBridge server. The two obvious approaches are:

1. Call `curl -X POST http://localhost:7842/api/...` directly from the command
2. Write a file to a watched directory and let the server poll for it

## Decision

The command writes a structured `.md` file to `~/.membridge/summaries/<session-id>/<timestamp>.md`. The server polls that directory every 30 seconds and ingests new files.

## Why not direct API call?

The original intent was to use the Write tool to write the summary file, but the Write tool receives a static path from Claude Code — it does not expand `$CLAUDE_CODE_SESSION_ID` at write time, so files would land under a fixed path rather than the correct session directory.

Rewriting the command to use a Bash heredoc solved the path problem, making a direct `curl` call possible in principle. However, by then the file-polling approach had additional advantages that made it worth keeping:

- **Survives server restarts** — files written while the server is down are ingested on the next poll cycle
- **Natural audit trail** — raw summary files on disk are readable without the server
- **Decoupled from HTTP** — the slash command has no dependency on the server being up at write time
- **Dedup is trivially correct** — `file_path` in `session_summaries` is the absolute path; already-ingested files are skipped by a single `SELECT`

## Consequences

- 30-second lag between writing a summary and it appearing in the dashboard
- The `~/.membridge/summaries/` directory accumulates `.md` files indefinitely — no pruning
- The server must have the summaries directory volume-mounted (Docker) or accessible at the same path (host)
- Any process that knows the session ID and the directory convention can inject summaries — intentionally open for future tooling
