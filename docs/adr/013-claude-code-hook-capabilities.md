# ADR 013: Claude Code Hook Capabilities and MemBridge Applications

**Date:** 2026-07-12  
**Status:** Accepted

## Context

MemBridge uses four Claude Code hooks to track session activity. During a hook architecture investigation (2026-07-12) we obtained a full technical picture of all available hook events, their stdin payloads, blocking semantics, and output format. This ADR records that knowledge and maps each unused hook to its MemBridge application, so future decisions have a clear reference rather than requiring another deep-dive.

## All Available Hook Events

| Event | Fires | Blocking? | MemBridge use |
|-------|-------|-----------|---------------|
| `UserPromptSubmit` | Before Claude processes a prompt | Yes (exit 2) | ✅ `claude_ui_heartbeat.sh` — registers session, increments prompt count |
| `PreToolUse` | Before each tool call | Yes (exit 2) | ✅ `claude_ui_tool_use.sh` — `tool_start` SSE; sets `awaiting_input` for `AskUserQuestion` |
| `PostToolUse` | After each tool call succeeds | No | ❌ not used |
| `PostToolBatch` | After all parallel tools in a batch resolve | No | ✅ `claude_ui_tool_batch.sh` — `tool_end` SSE, triggers refresh |
| `Stop` | After Claude finishes a response | No (`decision: block` re-triggers Claude) | ✅ `claude_ui_stop.sh` — sets `awaiting_input`, triggers auto-summary |
| `Notification` | When Claude sends a notification (permission prompts etc.) | No | ✅ `claude_ui_notification.sh` — sets `awaiting_input` on `permission_prompt` |
| `SubagentStop` | When a spawned subagent (Agent tool) finishes | No | ❌ not used |
| `SessionStart` | Session starts or resumes | No | ❌ not used |

## Key Mechanics

**Blocking:** exit code 2 from `PreToolUse`, `UserPromptSubmit` blocks the action. Exit code 1 is non-blocking (logs and continues). All MemBridge hooks exit 0 — we are observers, not gatekeepers.

**`Stop` with `decision: block`:** returning `{"hookSpecificOutput": {"hookEventName": "Stop", "decision": "block", "reason": "..."}}` from a Stop hook makes Claude continue working with the reason as context. Useful for automated quality gates (e.g. "tests are still failing").

**`PostToolUse` payload includes `tool_result`:** the hook receives the tool's output (`success`, `message`). `PreToolUse` only sees the input — the tool hasn't run yet.

**`PostToolBatch` vs `PostToolUse`:** `PostToolUse` fires once per tool call; `PostToolBatch` fires once per batch of parallel tools. For a thinking indicator, `PostToolBatch` is the right signal — it marks the moment Claude has finished all tool work for a round and is about to respond.

**SSE event format used by MemBridge:**
- `PreToolUse` → `{"type": "tool_start", "session_id": "...", "tool_name": "Bash"}`
- `PostToolBatch` / `Stop` → `{"type": "tool_end", "session_id": "..."}`
- All other hooks → `"refresh"` (plain string, triggers full table fetch)

## Unused Hooks: MemBridge Applications

### `PostToolUse`
**Application:** tool use counter + last tool name. Increment a `tool_use_count` column and store `last_tool_name` on every successful tool call. Surface as `12p · 47✦` alongside prompt count in the dashboard row. Also the data source for a future tool stream timeline in the session modal.

**Payload of interest:**
```json
{
  "tool_name": "Bash",
  "tool_input": {"command": "npm test"},
  "tool_result": {"success": true, "message": "..."}
}
```

### `SubagentStop`
**Application:** multi-agent workflow tracking. When Claude spawns a subagent via the Agent tool, `SubagentStop` fires when it completes. MemBridge could surface these as child entries under the parent session, giving visibility into agent fan-out depth and duration.

**Payload of interest:** includes `agent_id`, `agent_type`, and the subagent's `session_id` (distinct from the parent).

### `Stop` with `decision: block`
**Application:** automated quality gate. A Stop hook could run tests or a linter and return `decision: block` with a failure reason, forcing Claude to fix the issue before the turn ends. High risk of loops — would need a cap on consecutive blocks.

### `SessionStart`
**Application:** none identified. Heartbeat already fires on `UserPromptSubmit` which is the first user action in any session. `SessionStart` fires on resume/clear/compact events — could be used to re-register a session that wasn't tracked, but the heartbeat path already handles upserts idempotently.

## Decision

No changes to existing hook registrations. This ADR serves as the design-space reference for future hook work. Planned next steps in priority order:

1. `PostToolUse` → `tool_use_count` + `last_tool_name` (backlog item #2)
2. `PostToolUse` → `tool_events` table for modal timeline (backlog item #3)
3. `SubagentStop` → child session entries (future, low priority)

## Consequences

- Future contributors have a single place to look up hook semantics and MemBridge's rationale for using or skipping each one
- No code changes in this ADR — purely a knowledge record
