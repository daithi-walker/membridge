"""Thin wrapper around the `sesh` CLI — opt-in, per-project session snapshots.

MemBridge is a control plane: it tracks session metadata, summaries, and focus,
but deliberately does NOT preserve transcript content. `sesh` (a separate,
zero-dependency CLI) does exactly that — APFS copy-on-write snapshots of a
project's live transcripts, plus full-text search across them. This module lets
MemBridge *orchestrate* sesh per session without owning any of its storage.

Everything here is best-effort: if the `sesh` binary is missing, or a project has
never been `sesh init`'d, every call degrades to a no-op / empty result rather
than raising. sesh keys its storage on a project directory (`.sesh/`), not on a
Claude session id, so all operations take a `cwd` and run the CLI there.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve the sesh binary once. PATH first (respects a user symlink), then the two
# conventional install spots. None means "sesh not installed" — every call no-ops.
_SESH_BIN = (
    shutil.which("sesh")
    or next(
        (
            p
            for p in (
                os.path.expanduser("~/.local/bin/sesh"),
                os.path.expanduser("~/git/sesh/bin/sesh"),
            )
            if os.path.isfile(p) and os.access(p, os.X_OK)
        ),
        None,
    )
)

_TIMEOUT = 20  # seconds — snapshots clone files; a big project can take a moment


def available() -> bool:
    """True if the sesh CLI is installed and runnable."""
    return _SESH_BIN is not None


def project_root(cwd: str | None) -> str | None:
    """Return the directory that owns the `.sesh/` archive for `cwd`, or None.

    sesh stores per-project; a `.sesh/` in `cwd` or any ancestor governs it. We
    mirror sesh's own upward walk so `is_enabled` and the UI agree on scope.
    """
    if not cwd:
        return None
    try:
        here = Path(cwd).resolve()
    except (OSError, RuntimeError):
        return None
    if not here.is_dir():
        return None
    for d in (here, *here.parents):
        if (d / ".sesh").is_dir():
            return str(d)
    return None


def is_enabled(cwd: str | None) -> bool:
    """True if `cwd` (or an ancestor) has been `sesh init`'d."""
    return project_root(cwd) is not None


def _run(args: list[str], cwd: str) -> subprocess.CompletedProcess | None:
    """Run `sesh <args>` in `cwd`. Returns None if sesh is unavailable or errors.

    stdin is closed (sesh's mirror hook reads stdin; interactive commands check
    isatty) so nothing here can block on a terminal.
    """
    if not _SESH_BIN:
        return None
    if not cwd or not os.path.isdir(cwd):
        return None
    try:
        return subprocess.run(
            [_SESH_BIN, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("sesh %s failed in %s: %s", args[0] if args else "?", cwd, e)
        return None


def init(cwd: str) -> dict:
    """Enable sesh for the project at `cwd` (creates `.sesh/`, snapshots live sessions).

    Idempotent: sesh reports "already initialized" if it exists. Returns a small
    status dict for the API layer.
    """
    if not _SESH_BIN:
        return {"ok": False, "error": "sesh not installed"}
    proc = _run(["init"], cwd)
    if proc is None:
        return {"ok": False, "error": "sesh init could not run"}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()[:500]}
    return {
        "ok": True,
        "root": project_root(cwd) or cwd,
        "output": proc.stdout.strip(),
    }


def snapshot(cwd: str, tag: str | None = None) -> bool:
    """Checkpoint the project's live sessions. No-op unless sesh is enabled here.

    Called on Stop, so it must be cheap and silent — a False return just means
    "nothing snapshotted" (sesh missing, project not opted in, or the CLI errored).
    """
    if not is_enabled(cwd):
        return False
    args = ["snapshot"]
    if tag:
        args += ["-t", tag]
    proc = _run(args, cwd)
    return bool(proc and proc.returncode == 0)


def snapshots(cwd: str) -> str:
    """Return sesh's own `log` rendering for the project (raw text; sesh has no JSON)."""
    if not is_enabled(cwd):
        return ""
    proc = _run(["log"], cwd)
    if proc is None or proc.returncode != 0:
        return ""
    return proc.stdout.rstrip()


def find(query: str, cwd: str | None = None, limit: int = 20) -> str:
    """Full-text search across saved sessions (raw sesh text output).

    With `cwd` set and enabled, searches that project's archive; otherwise searches
    globally (`-g`) across all Claude projects, which needs no `.sesh/`.
    """
    if not _SESH_BIN or not query.strip():
        return ""
    terms = query.split()
    run_cwd = cwd if (cwd and is_enabled(cwd)) else os.path.expanduser("~")
    args = ["find", "-n", str(limit)]
    if not (cwd and is_enabled(cwd)):
        args.append("-g")
    args += terms
    proc = _run(args, run_cwd)
    if proc is None or proc.returncode != 0:
        return ""
    return proc.stdout.rstrip()
