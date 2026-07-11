# ADR 006: Three-Hook Design

**Date:** 2026-06-23  
**Status:** Accepted

## Context

Claude Code exposes lifecycle hooks that fire at different points in a session. MemBridge needs to:

- Register a session when it starts
- Keep the session alive while Claude is doing work (not just while the user is typing)
- Trigger a summary when a session ends

## Decision

Three hooks are registered in `~/.claude/settings.json`:

**`UserPromptSubmit` → `claude_ui_heartbeat.sh`**  
Fires when the user sends a message. Sends session ID, cwd, git branch, iTerm tab name, and PID to `/api/heartbeat`. This is the registration event — the first heartbeat creates the session row; subsequent ones increment `prompt_count` and update `last_seen`.

**`PreToolUse` → `claude_ui_tool_use.sh`**  
Fires before every tool call. Sends a lightweight touch to `/api/touch`, which updates `last_seen` only. This prevents a session from appearing stale or idle during long multi-step tool chains where the user hasn't typed anything for minutes.

**`Stop` → `claude_ui_stop.sh`**  
Fires when Claude finishes generating a response (after every turn, not just session close). Records the stop reason and triggers auto-summary generation if a transcript path is available.

## Why `PreToolUse` and not `PostToolUse`?

`PreToolUse` fires before the tool runs, so it keeps the session alive during the tool execution itself. `PostToolUse` would update `last_seen` after the tool completes — fine for short tools, but a long-running tool (e.g. `Bash` running tests) could push `last_seen` far enough back to flip the session to idle before the tool finishes.

## Known issue: Stop fires on every turn

`Stop` does not mean "the user closed the session" — it means "Claude finished a response". This caused duplicate auto-summaries on every turn until dedup by `transcript_path:file_size` was added (see ADR 002). The naming is misleading; the hook is better understood as `ResponseComplete`.

## Consequences

- A session stays `active` as long as tool chains are running, even with no user input
- Auto-summary is attempted after every response, not just on explicit session close — covered by dedup
- There is no hook for session open/close; first heartbeat acts as open, and there is no reliable close event
- If the server is down when a hook fires, the event is silently dropped (no queue — see BACKLOG)
