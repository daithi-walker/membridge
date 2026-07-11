# ADR 009: Do Not Override iTerm2 Tab Names

**Date:** 2026-06-23  
**Status:** Accepted

## Context

Early MemBridge builds used osascript to set a `name` override on iTerm2 sessions — renaming tabs to `project · branch` on the first heartbeat, and restoring the canonical name on resume. The goal was to make tabs identifiable at a glance.

This approach conflicted with Claude Code's own tab titling. Claude Code writes OSC escape sequences (`\e]0;title\a`) directly to the terminal on every tool use, pushing the current task description as the tab title. Since Claude Code runs continuously, it overwrites any name MemBridge sets within seconds.

## Decision

MemBridge no longer writes tab names via osascript. The `_rename_iterm_tab` call is kept only for new session registration (first heartbeat) as a best-effort label before Claude Code takes over. The `uuid_changed` rename path on resume was removed entirely — it was firing for all active sessions after a container rebuild and resetting every tab name.

The `iterm_tab` field, read from the current iTerm2 session name on every heartbeat, now reflects whatever Claude Code has set as the tab title (the current task description). This is stored and shown in the dashboard under the column "Activity" — it's more useful than a static `project · branch` label because it shows what each session is actively working on.

## Consequences

- Tab names in iTerm2 are owned by Claude Code, not MemBridge.
- The "Activity" column in the dashboard is a live read of what Claude Code is currently titling the session — updated on every prompt.
- The iTerm2 tab name can be used to select a specific tab via osascript (since it contains the task description), and copying it from the MemBridge modal is useful for scripting.
- Focus still works via UUID and PID/TTY matching — tab names are not used for navigation.
- If Claude Code is not running (stale/idle session), the activity shows the last task title before the session went quiet.
