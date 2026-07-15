# ADR 012: Drop Docker - Run Entirely as a Native Host Process

**Date:** 2026-06-23  
**Status:** Accepted  
**Supersedes:** [ADR 004](004-docker-host-split.md)

## Context

ADR 004 described a two-process architecture: a Docker container for the FastAPI server and a separate host-side Python process (`scripts/focus_server.py`) for macOS-native operations (osascript, iTerm2 focus, tab rename). ADR 004's "Desired State" section already flagged that dropping Docker in favour of a fully native process was the right long-term direction.

The limitations of the split proved untenable in practice:

- Two launchd plists to manage and keep in sync
- Silent degradation when the focus server was unreachable from the container
- Volume-mounting ADC credentials into Docker (see ADR 007) added operational friction
- `docker compose up/down` was a heavyweight lifecycle for a single-machine tool
- No real benefit from container isolation - the tool's value is deep macOS integration, not portability

## Decision

Run MemBridge entirely as a native macOS process via a single launchd plist (`com.membridge`):

- **uvicorn** runs directly on the host, managed by launchd
- All osascript/iTerm2 operations execute in-process via `membridge/focus.py`
- `scripts/focus_server.py` is deleted (functionality absorbed by `server.py` + `focus.py`)
- `install.sh` stops any existing Docker container/plist and installs the single native plist

## Consequences

**Positive:**
- One process, one plist, one log file
- No Docker dependency - install is `uv pip install -e .` + launchd plist
- osascript calls are direct subprocess calls; no HTTP hop between processes
- ADC credentials come from the user's host environment automatically

**Negative:**
- No container isolation (not a real concern for a single-developer local tool)
- Harder to run on Linux (osascript is macOS-only - but this was always true)

## Migration

See `docs/RELEASES.md` (2026-06-23 entry) for one-time migration steps.
Re-running `scripts/install.sh` handles the full transition automatically.
