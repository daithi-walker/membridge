#!/usr/bin/env python3
"""
Sync iTerm2 session state to MemBridge DB.

Prefers the iTerm2 Python API (reads titleOverride = user-set tab alias).
Falls back to osascript TTY matching if the API isn't available.

Updates:
  - iterm_tab: user alias if set, otherwise the auto-generated name
  - iterm_session_uuid: the stable session UUID from $ITERM_SESSION_ID

Usage:
    python3 scripts/sync_iterm_tabs.py [--dry-run]
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

DB_PATH = Path(os.getenv("MEMBRIDGE_DB", Path.home() / ".membridge" / "sessions.db"))

# Set ITERM2_PYTHON to override, e.g. in ~/.zshrc:
#   export ITERM2_PYTHON=~/"Library/Application Support/iTerm2/iterm2env-3.10.19/versions/3.14.0/bin/python3.14"
_ITERM2_PYTHON: str | None = os.getenv("ITERM2_PYTHON")
_QUERY_SCRIPT = Path(__file__).parent / "_iterm2_query.py"


def get_iterm_sessions_api() -> list[dict] | None:
    """Use iTerm2 Python API to get sessions with titleOverride. Returns None if unavailable."""
    if not _ITERM2_PYTHON or not Path(_ITERM2_PYTHON).exists():
        return None
    try:
        result = subprocess.run(
            [_ITERM2_PYTHON, str(_QUERY_SCRIPT)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout.strip())
    except Exception:
        return None


def get_iterm_sessions_osascript() -> list[dict]:
    """Fallback: osascript TTY+name only (no titleOverride)."""
    script = """
tell application "iTerm2"
    set output to ""
    repeat with w in windows
        repeat with t in tabs of w
            repeat with s in sessions of t
                try
                    set sessionTty to tty of s
                    set sessionName to name of s
                    set output to output & sessionTty & "|" & sessionName & "\n"
                end try
            end repeat
        end repeat
    end repeat
    return output
end tell
"""
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    sessions = []
    for line in result.stdout.strip().splitlines():
        if "|" in line:
            tty, _, name = line.partition("|")
            sessions.append({"tty": tty.strip(), "name": name.strip(), "title_override": None, "uuid": None})
    return sessions


def pid_to_tty(pid: int) -> str | None:
    try:
        result = subprocess.run(["ps", "-o", "tty=", "-p", str(pid)], capture_output=True, text=True, timeout=3)
        tty = result.stdout.strip()
        return tty if tty and tty != "??" else None
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("Querying iTerm2...", file=sys.stderr)
    api_sessions = get_iterm_sessions_api()

    if api_sessions is not None:
        print(f"  API: {len(api_sessions)} sessions (titleOverride available)", file=sys.stderr)
        # Index by UUID and by TTY (normalised, no /dev/)
        by_uuid = {s["uuid"]: s for s in api_sessions if s.get("uuid")}
        by_tty  = {(s["tty"] or "").removeprefix("/dev/"): s for s in api_sessions if s.get("tty")}
    else:
        print("  iTerm2 Python API unavailable, falling back to osascript", file=sys.stderr)
        fallback = get_iterm_sessions_osascript()
        print(f"  osascript: {len(fallback)} sessions (no titleOverride)", file=sys.stderr)
        by_uuid = {}
        by_tty  = {s["tty"].removeprefix("/dev/"): s for s in fallback if s.get("tty")}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT session_id, project_name, pid, iterm_tab, iterm_session_uuid "
        "FROM sessions WHERE pid IS NOT NULL ORDER BY last_seen DESC"
    ).fetchall()

    updated = 0
    for row in rows:
        iterm_s = None

        # Prefer UUID match (most reliable)
        if row["iterm_session_uuid"] and row["iterm_session_uuid"] in by_uuid:
            iterm_s = by_uuid[row["iterm_session_uuid"]]
        else:
            # Fall back to PID → TTY match
            tty = pid_to_tty(row["pid"])
            if tty:
                iterm_s = by_tty.get(tty)

        if not iterm_s:
            continue

        # Prefer user alias (titleOverride), fall back to auto name
        display_name = iterm_s.get("title_override") or iterm_s.get("name") or ""
        uuid = iterm_s.get("uuid")

        old_tab  = row["iterm_tab"] or ""
        old_uuid = row["iterm_session_uuid"] or ""
        tab_changed  = display_name and display_name != old_tab
        uuid_changed = uuid and uuid != old_uuid

        if not tab_changed and not uuid_changed:
            continue

        alias_indicator = " [alias]" if iterm_s.get("title_override") else ""
        print(f"  {row['project_name']} (pid={row['pid']}): '{old_tab}' → '{display_name}'{alias_indicator}")

        if not args.dry_run:
            conn.execute(
                "UPDATE sessions SET iterm_tab = ?, iterm_session_uuid = COALESCE(?, iterm_session_uuid) WHERE session_id = ?",
                (display_name or old_tab, uuid or None, row["session_id"]),
            )
        updated += 1

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(f"\n{'Would update' if args.dry_run else 'Updated'} {updated} session(s).")


if __name__ == "__main__":
    main()
