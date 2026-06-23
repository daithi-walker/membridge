#!/usr/bin/env python3
"""
Backfill membridge sessions DB from existing ~/.claude/projects/ transcripts.

Reads every .jsonl transcript Claude has stored locally, extracts:
  - session_id       from the filename
  - cwd              decoded from the project folder name
  - ai_title         Claude's auto-generated session title (used as summary)
  - first/last seen  from user-turn timestamps
  - prompt_count     number of human turns

Usage:
    python scripts/backfill.py [--dry-run] [--summarise] [--days N]

Options:
    --dry-run     Print what would be imported without writing to DB
    --summarise   Generate Vertex AI summaries for sessions missing one
                  (slow — calls Claude API per session)
    --days N      Only import sessions active in the last N days (default: all)
    --min-turns N Skip sessions with fewer than N user turns (default: 2)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
MEMBRIDGE_DB = Path(os.getenv("MEMBRIDGE_DB", Path.home() / ".membridge" / "sessions.db"))


def decode_cwd(folder_name: str) -> str:
    """Convert Claude's folder encoding back to a path, e.g. -Users-you-git-myproject → /Users/you/git/myproject"""
    return folder_name.replace("-", "/", 1).replace("-", "/")


def parse_transcript(jsonl_path: Path) -> dict | None:
    session_id = jsonl_path.stem
    cwd = decode_cwd(jsonl_path.parent.name)
    project_name = Path(cwd).name

    first_seen = None
    last_seen = None
    prompt_count = 0
    ai_title = None

    try:
        with jsonl_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                t = obj.get("type")

                if t == "ai-title" and not ai_title:
                    ai_title = obj.get("aiTitle")

                if t == "user":
                    msg = obj.get("message", {})
                    content = msg.get("content", "")
                    # Only count real human turns, not tool results
                    is_human = isinstance(content, str) and content.strip()
                    if not is_human and isinstance(content, list):
                        is_human = any(
                            b.get("type") == "text" for b in content
                            if isinstance(b, dict)
                        )
                    if is_human:
                        prompt_count += 1

                    ts = obj.get("timestamp")
                    if ts:
                        try:
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if first_seen is None or dt < first_seen:
                                first_seen = dt
                            if last_seen is None or dt > last_seen:
                                last_seen = dt
                        except ValueError:
                            pass

    except (OSError, UnicodeDecodeError) as e:
        print(f"  WARN: could not read {jsonl_path}: {e}", file=sys.stderr)
        return None

    if first_seen is None:
        return None  # Empty/unreadable transcript

    return {
        "session_id": session_id,
        "cwd": cwd,
        "project_name": project_name,
        "ai_title": ai_title,
        "first_seen": first_seen.isoformat(),
        "last_seen": last_seen.isoformat() if last_seen else first_seen.isoformat(),
        "prompt_count": prompt_count,
        "transcript_path": str(jsonl_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill membridge sessions DB")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing")
    parser.add_argument("--summarise", action="store_true", help="Generate AI summaries via Vertex")
    parser.add_argument("--days", type=int, default=0, help="Only import sessions active in last N days")
    parser.add_argument("--min-turns", type=int, default=2, help="Skip sessions with fewer than N human turns")
    args = parser.parse_args()

    if not CLAUDE_PROJECTS_DIR.exists():
        print(f"ERROR: {CLAUDE_PROJECTS_DIR} not found", file=sys.stderr)
        sys.exit(1)

    cutoff = None
    if args.days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    # Collect all .jsonl files across all project dirs
    jsonl_files = list(CLAUDE_PROJECTS_DIR.glob("*/*.jsonl"))
    print(f"Found {len(jsonl_files)} transcript files across {len(list(CLAUDE_PROJECTS_DIR.glob('*')))} projects")

    sessions = []
    skipped_empty = 0
    skipped_cutoff = 0
    skipped_turns = 0

    for path in sorted(jsonl_files):
        result = parse_transcript(path)
        if result is None:
            skipped_empty += 1
            continue

        if cutoff:
            last = datetime.fromisoformat(result["last_seen"])
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last < cutoff:
                skipped_cutoff += 1
                continue

        if result["prompt_count"] < args.min_turns:
            skipped_turns += 1
            continue

        sessions.append(result)

    print(f"Importing: {len(sessions)} sessions")
    print(f"Skipped:   {skipped_empty} empty, {skipped_cutoff} outside date range, {skipped_turns} too short")

    if args.dry_run:
        print("\n--- DRY RUN ---")
        for s in sessions:
            print(f"  {s['session_id'][:8]}… {s['project_name']:20} {s['prompt_count']:3} turns  {s['last_seen'][:10]}  {s['ai_title'] or '(no title)'}")
        return

    # Import into DB
    sys.path.insert(0, str(Path(__file__).parent.parent))
    os.environ.setdefault("MEMBRIDGE_DB", str(MEMBRIDGE_DB))

    from claude_ui.db import init_db, upsert_heartbeat, update_summary, record_stop
    import sqlite3

    init_db()

    imported = 0
    updated_summary = 0

    for s in sessions:
        upsert_heartbeat(
            session_id=s["session_id"],
            cwd=s["cwd"],
            branch=None,
            iterm_tab=None,
        )
        # Stamp accurate timestamps and prompt count directly (bypass upsert defaults)
        conn = sqlite3.connect(MEMBRIDGE_DB)
        conn.execute(
            """UPDATE sessions
               SET first_seen = ?, last_seen = ?, prompt_count = ?
               WHERE session_id = ?""",
            (s["first_seen"], s["last_seen"], s["prompt_count"], s["session_id"]),
        )
        conn.commit()
        conn.close()

        # Use ai-title as summary if present and no summary yet
        if s["ai_title"]:
            summary_label = f"[{s['ai_title']}]"
            update_summary(s["session_id"], summary_label, source="backfill")
            updated_summary += 1

        imported += 1
        print(f"  ✓ {s['session_id'][:8]}… {s['project_name']:20} {s['prompt_count']:3} turns  {s.get('ai_title') or ''}")

    print(f"\nDone. Imported {imported} sessions, {updated_summary} with titles.")

    if args.summarise:
        print("\nGenerating AI summaries (this may take a while)...")
        from claude_ui.summariser import summarise
        from claude_ui.db import get_session

        for s in sessions:
            session = get_session(s["session_id"])
            if not session:
                continue
            if session.get("summary_source") == "user":
                continue
            summary = summarise(s["transcript_path"])
            if summary:
                update_summary(s["session_id"], summary, source="auto")
                print(f"  ✓ {s['session_id'][:8]}… {summary[:80]}")


if __name__ == "__main__":
    main()
