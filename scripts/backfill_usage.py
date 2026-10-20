#!/usr/bin/env python3
"""
Backfill api_calls (token usage + estimated cost) from ~/.claude/projects/ transcripts.

Re-parses every session transcript plus its subagent transcripts, exactly as the Stop
hook does, and replaces the stored rows. Safe to re-run at any time; re-run it after
editing membridge/pricing.toml to reprice stored calls.

Sessions recorded before the heartbeat hook reported auth mode have none. Vertex calls
are recognised from their message ids; for direct Anthropic history pass
--auth-mode subscription (or api) so it's classified as API-equivalent (or billed).

Usage:
    uv run python scripts/backfill_usage.py [--auth-mode MODE] [--projects-dir DIR]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from membridge import db, usage

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--auth-mode", choices=usage.AUTH_MODES,
                        help="auth mode for sessions that never recorded one")
    parser.add_argument("--projects-dir", type=Path, default=CLAUDE_PROJECTS_DIR)
    args = parser.parse_args()

    db.init_db()
    transcripts = sorted(args.projects_dir.glob("*/*.jsonl"))
    calls = 0
    for i, path in enumerate(transcripts, 1):
        calls += usage.ingest_session(path.stem, str(path), args.auth_mode)
        if i % 50 == 0:
            print(f"  {i}/{len(transcripts)} transcripts, {calls} calls", file=sys.stderr)
    print(f"Ingested {calls} calls from {len(transcripts)} transcripts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
