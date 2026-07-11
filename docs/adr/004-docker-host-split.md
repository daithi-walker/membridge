# ADR 004: Docker + Host Process Split

**Date:** 2026-06-23  
**Status:** Superseded by [ADR 012](012-drop-docker-native-process.md)

## Context

MemBridge needs to:
1. Run a persistent API server and SQLite database
2. Focus iTerm2 windows and rename tabs via `osascript` and the iTerm2 Python API

`osascript` and the iTerm2 Python runtime cannot run inside a Docker container — they require direct access to macOS GUI APIs that are not exposed to containerised processes.

## Decision

Split into two processes:

**Docker container (port 7842)** — FastAPI server, SQLite DB, summary poller, all business logic. Runs via `docker compose` managed by launchd (`com.daihi.membridge`).

**Host Python process (port 7843, `scripts/focus_server.py`)** — Handles all macOS-native operations: iTerm2 focus, tab rename, PID alive-check. Runs directly on the host via a separate launchd plist (`com.daihi.membridge-focus`).

The container calls the focus server via `http://host.docker.internal:7843`. The focus server is a thin FastAPI app with no persistence of its own.

## Known limitations

This is not the desired end state. The split introduces:

- **Two processes to manage** — two launchd plists, two log files, two failure modes
- **Network dependency between them** — the container silently degrades if the focus server is down
- **Install complexity** — `scripts/install.sh` must detect the iTerm2 Python binary path and bake it into the plist at install time
- **Credential coupling** — ADC credentials must be volume-mounted into Docker separately (see ADR 007)

## Desired state

A fully self-contained process — ideally a native macOS app or a plain Python process managed by a single launchd plist — that owns both the API server and the iTerm2 integration without a container boundary. Docker was chosen for iteration speed; it is not the right runtime for a tool that needs deep macOS integration.

Candidate paths:
- **Drop Docker, run uvicorn directly on the host** — simplest; loses container isolation but gains full macOS access. Likely the right move.
- **Homebrew formula** — packages the Python env, installs launchd plist, no Docker dependency
- **macOS app bundle** — longer term; enables menu bar icon, native notifications
