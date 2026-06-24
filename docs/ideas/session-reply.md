# Idea: Reply to a Session from the Dashboard

## What
Send a text reply or decision choice (1/2/3) to a waiting Claude session directly from the MemBridge UI — without switching to the terminal tab.

## Why it's interesting
The primary pain point: Claude is waiting for input in a background session, you're mid-task in another tab. Ideally you'd answer without context-switching.

## How (speculative)
Requires a way to inject keystrokes into a specific iTerm2 session. Options:
1. **osascript**: `tell session <uuid> to write text "my reply"` — works but requires Accessibility permission
2. **tmux send-keys**: if sessions run in tmux, trivial
3. **Claude Code local API**: if Anthropic ever exposes one, ideal

## Decision input case
If the session is awaiting a `1/2/3` choice (permission prompt), we know the valid responses. The UI could show the options from the notification payload and let you click one.

## Blocker
osascript write-text works in principle but needs Accessibility permission (separate from notification permission). UX for free-text replies is also awkward in a small dashboard row.

## Revisit when
- terminal-notifier clickable notifications are in place (clicks could open a reply panel)
- Anthropic exposes a session input API
