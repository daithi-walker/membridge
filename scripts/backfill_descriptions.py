#!/usr/bin/env python3
"""
Backfill missing or multiline descriptions for sessions.

Targets sessions where description is NULL or contains a newline
(i.e. old multi-paragraph summaries, not the intended one-liner).

For sessions with an existing multiline description, condenses it to
one line using Claude. For sessions with no description at all, skips
(no transcript reading — use backfill.py for those).

Usage:
    # Run inside Docker (has summariser dependencies + ADC):
    docker exec -it membridge python scripts/backfill_descriptions.py [--dry-run]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from claude_ui import db
from claude_ui.summariser import _get_client, MODEL


def condense(text: str) -> str | None:
    prompt = (
        "Condense the following session description into a single short phrase of under 80 characters. "
        "Be specific — keep the key files, features, or bug details. "
        "Output only the phrase wrapped in square brackets, e.g. [Fix heartbeat upsert in db.py]. "
        "No other text.\n\n"
        f"{text}"
    )
    try:
        client = _get_client()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip().rstrip(".")
    except Exception as e:
        print(f"    API error: {e}", file=sys.stderr)
        return None


def needs_backfill(description: str | None) -> bool:
    if not description:
        return False  # nothing to condense from — skip
    stripped = description.strip()
    # Valid format: single line enclosed in [square brackets]
    if stripped.startswith("[") and stripped.endswith("]") and "\n" not in stripped:
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Show what would change, no writes")
    args = parser.parse_args()

    db.init_db()
    sessions = db.list_sessions()
    targets = [s for s in sessions if needs_backfill(s.get("description"))]

    print(f"Found {len(targets)} session(s) with multiline descriptions (out of {len(sessions)} total)")

    updated = 0
    failed = 0
    for s in targets:
        sid = s["session_id"]
        short = sid[:8]
        existing = s["description"]
        print(f"  {short}… [{s['project_name']}]", end="", flush=True)

        if args.dry_run:
            print(f"\n    was: {existing[:100].replace(chr(10), ' ')!r}")
            continue

        one_liner = condense(existing)
        if not one_liner:
            print(" — failed")
            failed += 1
            continue

        db.update_description(sid, one_liner)
        print(f" — {one_liner}")
        updated += 1

    print(f"\n{'Would update' if args.dry_run else 'Updated'} {updated} session(s)" +
          (f", {failed} failed" if failed else "") + ".")
