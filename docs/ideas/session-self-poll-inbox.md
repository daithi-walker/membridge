# Idea: Session Self-Polls an Inbox (feedback without injection)

## What

Instead of MemBridge *delivering into* a session, the already-open session **pulls its
own queued input**. A standing scheduled wakeup inside the Claude Code session polls a
MemBridge inbox endpoint on each idle tick, drains any queued messages, acts on them, and
marks them consumed.

```
You (browser / external HTML doc / phone)
        │  POST feedback, tagged with session ID
        ▼
MemBridge  →  per-session inbox queue  (GET /api/sessions/{id}/inbox)
        ▲
        │  session's own ScheduleWakeup polls each idle tick,
        │  drains queue, acts, marks consumed
   Open Claude Code session
```

## Why this is different from the existing backlog items

The current approaches all push *into* the session:

- **Near-term #1 (dashboard reply)** - osascript `write text` injects keystrokes into iTerm2.
- **Future (`claude --resume --print`)** - spawns a *fresh headless subprocess* turn.
- **telegram-mobile-reply.md** - same osascript injection at the end.

This variant inverts it: the **live, already-open interactive session** does the fetching.

It sidesteps the two blockers those docs flag:
- **No launchd Accessibility permission** - nothing injects keystrokes.
- **No `--print` black box** - it's the real interactive session, so tool calls, diffs, and
  reasoning stay fully visible in the terminal (and to any observer layer). No separate
  subprocess turn that only returns a final string.

It also reuses a pattern MemBridge already runs in production: ADR 005 has the *server*
polling a watched directory for summary files. This is the same polling idea, pointed the
other way (session polls server).

## Mechanism

- **MemBridge side:** per-session inbox queue + a submit surface. Submit can be a dashboard
  textarea, an external HTML doc POSTing to `localhost:7842`, or a phone. `GET
  /api/sessions/{id}/inbox` returns unconsumed messages; a consume/ack marks them done.
- **Session side:** a standing `ScheduleWakeup` (or CronCreate) loop in the session polls
  the inbox each idle tick, processes messages in order, acks them.

## Constraint (acceptable)

Only fires while a session is **open and idle** - the wakeup can't run if Claude Code is
quit, and each tick consumes a turn. This matches how MemBridge is actually used (sessions
kept open), so it's fine for "I'll be feeding notes over the next while," not for
"pick this up tomorrow."

## Bonus

Same mechanism captures out-of-band review feedback generally. Example from real use: a
formatted review HTML (e.g. the daniel-info comment-review doc) could POST per-thread notes
to the session inbox instead of downloading a file for manual re-read.

## Revisit when

- We want to feed a *running* session without touching the keyboard, and want full
  in-terminal visibility (rules out the `--print` path).
- The inbox endpoint + a small submit UI are cheap to add alongside the existing summary
  polling infrastructure.
