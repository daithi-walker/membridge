#!/usr/bin/env python3
"""
Sync iTerm2 session names to MemBridge DB for all currently active sessions.

Runs osascript to list all iTerm2 sessions with their TTY, then matches
each to a DB session by PID → TTY. Updates iterm_tab in the DB.

Usage:
    python3 scripts/sync_iterm_tabs.py [--dry-run]
"""

import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


DB_PATH = Path(os.getenv("CLAUDE_UI_DB", Path.home() / ".claude-ui" / "sessions.db"))


def get_iterm_sessions() -> list[dict]:
    """Return list of {tty, name} for all iTerm2 sessions."""
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
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=10,
    )
    sessions = []
    for line in result.stdout.strip().splitlines():
        if "|" in line:
            tty, _, name = line.partition("|")
            sessions.append({"tty": tty.strip(), "name": name.strip()})
    return sessions


def pid_to_tty(pid: int) -> str | None:
    """Resolve a PID to its controlling TTY."""
    try:
        result = subprocess.run(
            ["ps", "-o", "tty=", "-p", str(pid)],
            capture_output=True, text=True, timeout=3,
        )
        tty = result.stdout.strip()
        return tty if tty and tty != "??" else None
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("Fetching iTerm2 sessions...", file=sys.stderr)
    iterm_sessions = get_iterm_sessions()
    # iTerm2 returns "/dev/ttysXXX"; ps returns "ttysXXX" — normalise both
    tty_to_name = {}
    for s in iterm_sessions:
        tty = s["tty"].removeprefix("/dev/")
        tty_to_name[tty] = s["name"]
    print(f"  Found {len(iterm_sessions)} iTerm2 sessions", file=sys.stderr)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT session_id, project_name, pid, iterm_tab FROM sessions WHERE pid IS NOT NULL ORDER BY last_seen DESC"
    ).fetchall()

    updated = 0
    for row in rows:
        pid = row["pid"]
        tty = pid_to_tty(pid)
        if not tty:
            continue
        name = tty_to_name.get(tty)
        if not name:
            continue

        old = row["iterm_tab"] or ""
        if name == old:
            continue

        print(f"  {row['project_name']} (pid={pid}): '{old}' → '{name}'")
        if not args.dry_run:
            conn.execute(
                "UPDATE sessions SET iterm_tab = ? WHERE session_id = ?",
                (name, row["session_id"]),
            )
        updated += 1

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(f"\n{'Would update' if args.dry_run else 'Updated'} {updated} session(s).")


if __name__ == "__main__":
    main()
