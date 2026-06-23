# ADR 010 — Session State Machine for Focus Button

## Status
Accepted

## Context

The MemBridge dashboard shows a focus/resume button on each session row. Originally this button had two states: normal (grey `⌘`) and stale/needs-resume (amber `↩`). As we added the `awaiting_input` flag (set by the Stop hook, cleared by the next heartbeat), we needed a consistent visual language to communicate what a session is doing at a glance.

Users look at the dashboard while multitasking across several Claude sessions. The focus button is the primary call-to-action — it needs to convey enough state that a glance tells you whether action is needed.

## Decision

The focus button implements a four-state machine, priority order:

| Priority | Condition | Colour | Icon | Meaning |
|---|---|---|---|---|
| 1 | `awaiting_input = 1` | Green `#4caf50` | `◉` pulsing slow | Claude finished; wants your response |
| 2 | `status = 'stale'` | Amber `#E4A636` | `↩` | Session dead; needs `claude --resume` |
| 3 | `status = 'active'` | Orange `#E4A636` | `◉` pulsing fast | Claude is actively working |
| 4 | Otherwise (idle) | Grey | `⌘` | Alive, no action needed |

Priority 1 beats priority 2: a stale session can still be `awaiting_input` (Stop fired before the PID died). Green takes precedence because user action is needed regardless of whether resume is also required.

The header badge (green, pulsing) shows the count of sessions in state 1 — it is intentionally distinct from the per-row buttons so users can see at a glance whether anything needs attention without scanning all rows.

## `awaiting_input` lifecycle

- Set to `1` by `db.record_stop()` on every Stop hook
- Cleared to `0` by `db.upsert_heartbeat()` when the next prompt arrives
- `record_stop()` returns the *previous* value so the server can detect the 0→1 transition and decide whether to fire a macOS notification

## Notification suppression rules

A macOS notification fires only when:
1. `awaiting_input` was previously `0` (first time this turn's stop fires)
2. The session's iTerm2 tab is **not** currently frontmost (`focus.is_session_frontmost()`)

This prevents notification spam when the user is already in the session, and prevents duplicate pings when the Stop hook fires multiple times for the same turn.

## Consequences

- `active` sessions pulse orange even when Claude hasn't asked anything — this is intentional: it signals "don't interrupt, work in progress". The colour matches the SandboxAQ accent (`#E4A636`) to feel on-brand.
- We cannot detect *what kind* of input Claude wants (decision vs free text) from the hook payload alone. The green state means "Claude is waiting" without distinguishing. Finer-grained detection (e.g. watching for `AskUserQuestion` tool calls via `PreToolUse`) is a future option.
- The fast pulse (1.2s) for working vs slow pulse (2s) for awaiting gives a secondary timing cue in addition to colour.
