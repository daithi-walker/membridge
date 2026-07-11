# ADR 011 — Notification Hook for Mid-Turn Permission Prompts

## Status
Accepted

## Context

The Stop hook fires when Claude finishes a turn. But Claude Code also pauses mid-turn to ask the user to approve a tool call (e.g. "Do you want to make this edit?"). During this pause:
- The Stop hook has not fired (the turn hasn't ended)
- The session stays `active` (orange ◉) even though Claude is waiting for input
- No existing hook covered this case

## Decision

Register a `Notification` hook with `matcher: "permission_prompt"` in `~/.claude/settings.json`. This hook fires the moment Claude Code displays a permission dialog, before the user responds.

The hook POSTs to `POST /api/notification`, which:
1. Calls `db.record_stop()` to set `awaiting_input = 1` (reusing the same flag as Stop)
2. Broadcasts an SSE `refresh` event so the dashboard updates instantly
3. Calls `_notify_stop()` to fire a macOS notification if prefs allow

## Why the Notification hook over alternatives

- **Polling the process state** (`ps -o stat`): `S+` means waiting for terminal input, but Claude is always in `S+` even when working — not distinguishable.
- **Timeout heuristic** (active for >N seconds without new heartbeat): noisy, requires tuning, produces false positives.
- **Notification hook**: event-driven, zero lag, semantically correct. The `permission_prompt` matcher is exactly the signal we need.

## Consequences

- Sessions that were already showing a permission prompt when the hook was registered miss the signal — no backfill possible.
- The `awaiting_input` flag is shared between Stop and Notification — both set it to `1`. The heartbeat clears it when the user responds. This means the green ◉ appears for both "turn complete" and "mid-turn permission" without needing separate states.
- `install.sh` registers the hook automatically going forward.
