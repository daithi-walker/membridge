#!/usr/bin/env python3
"""
Match open iTerm2 tabs to MemBridge sessions and print resume commands.

Useful after a reboot when Claude processes are dead but iTerm2 tabs
still show the AI-generated session titles that MemBridge stored.

Usage:
    python3 scripts/suggest_resumes.py
    python3 scripts/suggest_resumes.py --all   # include stale sessions too
"""

import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

DB_PATH = Path(os.getenv("MEMBRIDGE_DB", Path.home() / ".membridge" / "sessions.db"))


def get_iterm_sessions() -> list[dict]:
    script = """
tell application "iTerm2"
    set output to {}
    repeat with w in windows
        set wIdx to 1
        repeat with t in tabs of w
            repeat with s in sessions of t
                try
                    set sTty to tty of s
                    set sName to name of s
                    set end of output to (sTty & "|" & sName)
                end try
            end repeat
            set wIdx to wIdx + 1
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
    for item in result.stdout.strip().split(", "):
        item = item.strip()
        if "|" in item:
            tty, _, name = item.partition("|")
            sessions.append({"tty": tty.strip().removeprefix("/dev/"), "name": name.strip()})
    return sessions


def get_db_sessions() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT session_id, project_name, git_branch, iterm_tab, cwd, last_seen FROM sessions "
        "WHERE iterm_tab IS NOT NULL AND iterm_tab != '' ORDER BY last_seen DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()

    print("Scanning iTerm2 tabs...", file=sys.stderr)
    iterm = get_iterm_sessions()
    iterm_names = {s["name"] for s in iterm}
    print(f"  {len(iterm)} open tabs", file=sys.stderr)

    db_sessions = get_db_sessions()

    matched = []
    for s in db_sessions:
        stored_name = s["iterm_tab"]
        # Match if the stored name is still open (exact or substring)
        found = next((n for n in iterm_names if stored_name in n or n in stored_name), None)
        if found:
            matched.append({**s, "current_name": found})

    if not matched:
        print("\nNo open iTerm2 tabs matched any MemBridge session.")
        print("This is normal if all Claude processes restarted after reboot and")
        print("iTerm2 tab names no longer match the stored session titles.")
        return

    print(f"\n{'='*72}")
    print(f"Found {len(matched)} tab(s) matching MemBridge sessions:\n")
    for m in matched:
        branch = f"  branch: {m['git_branch']}" if m['git_branch'] else ""
        print(f"  Tab:     {m['current_name']}")
        print(f"  Project: {m['project_name']}{branch}")
        print(f"  Last active: {m['last_seen'][:16].replace('T', ' ')}")
        print(f"  Resume:  claude --resume {m['session_id']}")
        print()

    print(f"{'='*72}")
    print("\nTip: run the resume command inside the matching iTerm2 tab to")
    print("continue where you left off.")


if __name__ == "__main__":
    main()
