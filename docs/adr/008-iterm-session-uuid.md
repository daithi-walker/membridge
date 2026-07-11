# ADR 008: iTerm2 Session UUID as Stable Tab Identity

**Date:** 2026-06-23  
**Status:** Accepted

## Context

MemBridge renames iTerm2 tabs to reflect the project and branch of each Claude session. Tab names are mutable — the user can rename them, and the rename API itself changes the name. We need a stable identity for each tab to avoid renaming the wrong tab or renaming a tab that's already been correctly named.

## Decision

The heartbeat payload includes `iterm_session_uuid` — the iTerm2 internal UUID for the tab (`$ITERM_SESSION_ID` env var, available in all iTerm2 shells). This is:

- **Stable** — never changes for the lifetime of the tab, even after renames
- **Unique** — UUID format, no collisions
- **Free** — available as an env var, no API call needed

The `sessions` table stores `iterm_session_uuid`. On the first heartbeat, if no UUID is known for the session, the `iterm_tab` name (the display name) is also stored. Subsequent heartbeats update `iterm_tab` only when `iterm_session_uuid` is not yet recorded — preventing stale tab names from overwriting a correctly-set one.

The focus server (`scripts/focus_server.py`) uses the UUID to identify which tab to raise, falling back to PID-based window matching if the UUID isn't available.

`sync_iterm_tabs.py` uses the iTerm2 Python API to enumerate all open tabs, match by UUID, and update the display name if it has drifted from what MemBridge expects.

## Consequences

- Sessions opened in terminals other than iTerm2 have no UUID — `iterm_session_uuid` is NULL and tab features degrade gracefully
- The `iterm_tab` column reflects the tab name at first heartbeat; it can drift if the user renames the tab manually between syncs
- `sync_iterm_tabs.py` must be run manually or via a scheduled launchd job to keep names current (see BACKLOG: Auto sync_iterm_tabs)
