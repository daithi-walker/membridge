#!/usr/bin/env python3
"""
Report real engaged-work time for a client, built from MemBridge's
activity_events (kind='prompt' on UserPromptSubmit, kind='stop' when Claude
finishes a turn and is awaiting input).

Core heuristic:
  - Each prompt is paired with the next stop IN THE SAME SESSION -> an "active"
    interval (Claude was working the whole span, whether interactively or
    autonomously). This is unambiguous engaged time.
  - The gap between one session's stop and its own next prompt is ambiguous
    (reading/thinking vs actually away) -- but if you have multiple sessions
    open for the same client, another session's active interval overlapping
    that gap is real evidence you were still working, just elsewhere. So every
    session's active intervals for a client are merged into ONE timeline
    before gaps are computed -- overlapping sessions don't create false gaps.
  - A short gap in the merged timeline (<= --idle-minutes) is counted as
    engaged (reading/typing the next prompt). A longer gap is flagged as a
    likely break and excluded from the billable estimate, but still shown so
    you can sanity-check it against memory.

This is a heuristic, not a clock -- it cannot see reading time that isn't
followed by more activity, and it only covers events from 2026-08-13 onward.

Usage:
    # Group ALL recorded activity by inferred client (top-level dir under ~/git/)
    python scripts/heartbeat_report.py

    # One client, all subdirectories rolled up
    python scripts/heartbeat_report.py --path-prefix ~/git/bb

    # Exact project_name match only (no subdirectory rollup)
    python scripts/heartbeat_report.py --project bb

    # Restrict to a date range (local time, inclusive)
    python scripts/heartbeat_report.py --path-prefix ~/git/bb --from 2026-08-08 --to 2026-08-09

    # Treat gaps up to 20 minutes as still-engaged reading/thinking time (default: 15)
    python scripts/heartbeat_report.py --path-prefix ~/git/bb --idle-minutes 20
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from membridge import db  # noqa: E402 — import after sys.path tweak


def fmt_local(dt: datetime) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def infer_client(cwd: str) -> str:
    """Best-effort client name: the directory right after '.../git/', else the
    top-level project_name. Matches this machine's ~/git/<client>/... layout."""
    parts = Path(cwd).parts
    if "git" in parts:
        idx = parts.index("git")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return Path(cwd).name


def build_active_intervals(
    events: list[dict],
) -> tuple[list[tuple[datetime, datetime, bool]], list[dict]]:
    """Pair each prompt with the next stop in the SAME session_id. Returns
    ((start, end, closed) tuples, orphan_stops) -- closed=False means no stop
    was ever recorded for that prompt (still working, or the Stop hook never
    fired). orphan_stops are 'stop' events with no preceding prompt in this
    data -- typically a session already mid-turn when tracking started, i.e.
    the real prompt exists but predates this table's history."""
    by_session: dict[str, list[dict]] = {}
    for ev in events:
        by_session.setdefault(ev["session_id"], []).append(ev)

    intervals: list[tuple[datetime, datetime, bool]] = []
    orphan_stops: list[dict] = []
    for evs in by_session.values():
        evs.sort(key=lambda e: e["_dt"])
        pending_prompt: dict | None = None
        for ev in evs:
            if ev["kind"] == "prompt":
                if pending_prompt is not None:
                    # Two prompts with no stop between them (a missed/crashed hook) --
                    # close the dangling one at its own timestamp, flagged as open.
                    intervals.append((pending_prompt["_dt"], pending_prompt["_dt"], False))
                pending_prompt = ev
            elif ev["kind"] == "stop":
                if pending_prompt is not None:
                    intervals.append((pending_prompt["_dt"], ev["_dt"], True))
                    pending_prompt = None
                else:
                    orphan_stops.append(ev)
        if pending_prompt is not None:
            intervals.append((pending_prompt["_dt"], pending_prompt["_dt"], False))
    return intervals, orphan_stops


def merge_intervals(intervals: list[tuple[datetime, datetime, bool]]) -> list[tuple[datetime, datetime]]:
    """Union overlapping/touching (start, end) spans across all sessions."""
    spans = sorted(((s, e) for s, e, _ in intervals), key=lambda x: x[0])
    merged: list[list[datetime]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def report_active_time(events: list[dict], idle_minutes: int) -> float:
    """Print merged active blocks and flagged gaps; return the billable estimate (hours)."""
    open_prompts = [e for e in events if e["kind"] == "prompt"]
    stops = [e for e in events if e["kind"] == "stop"]
    intervals, orphan_stops = build_active_intervals(events)
    dangling = [i for i in intervals if not i[2]]
    merged = merge_intervals(intervals)

    if not merged:
        print(f"  No paired prompt/stop activity in this range "
              f"({len(open_prompts)} prompt(s), {len(stops)} stop(s), none paired).")
        if orphan_stops:
            print(f"  Note: {len(orphan_stops)} stop(s) had no matching prompt in this data "
                  "(session already mid-turn when tracking started).")
        return 0.0

    idle_gap = timedelta(minutes=idle_minutes)
    billable_hours = 0.0
    print(f"  {len(open_prompts)} prompt(s), {len(stops)} stop(s), "
          f"{len(merged)} merged active block(s) across all sessions:\n")

    prev_end: datetime | None = None
    for start, end in merged:
        if prev_end is not None:
            gap = start - prev_end
            gap_hours = gap.total_seconds() / 3600
            if gap <= idle_gap:
                billable_hours += gap_hours
                print(f"    ... {gap_hours * 60:.0f}m gap (<= {idle_minutes}m, counted as reading/thinking)")
            else:
                print(f"    !!! {gap_hours:.2f}h gap ({fmt_local(prev_end)} -> {fmt_local(start)}) "
                      f"-- NOT counted, check against memory")
        span_hours = (end - start).total_seconds() / 3600
        billable_hours += span_hours
        print(f"  {fmt_local(start)}  ->  {fmt_local(end)}  ({span_hours:.2f}h active)")
        prev_end = end

    if dangling:
        print(f"\n  Note: {len(dangling)} prompt(s) with no recorded stop yet "
              "(still in progress, or the Stop hook didn't fire) -- not included above.")
    if orphan_stops:
        print(f"  Note: {len(orphan_stops)} stop(s) with no matching prompt in this data "
              "(the session was already mid-turn when tracking started) -- not included above.")

    print(f"\n  Billable estimate: {billable_hours:.2f}h "
          f"(active spans + gaps <= {idle_minutes}m; longer gaps excluded, shown above for review)")
    return billable_hours


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", help="Exact project_name to filter to (e.g. 'bb') — no subdirectory rollup")
    parser.add_argument("--path-prefix", help="cwd prefix to filter to, any subdirectory (e.g. ~/git/bb)")
    parser.add_argument("--from", dest="from_date", help="Start date, local time (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", help="End date, local time (YYYY-MM-DD), inclusive")
    parser.add_argument("--idle-minutes", type=int, default=15,
                         help="Gaps up to this long (minutes) count as still-engaged reading/thinking "
                              "time; longer gaps are flagged and excluded (default: 15)")
    args = parser.parse_args()

    since = None
    until = None
    if args.from_date:
        since = datetime.strptime(args.from_date, "%Y-%m-%d").astimezone(UTC).isoformat()
    if args.to_date:
        until = (datetime.strptime(args.to_date, "%Y-%m-%d") + timedelta(days=1)).astimezone(UTC).isoformat()

    events = db.get_activity_events(project_name=args.project, since=since, until=until)

    if args.path_prefix:
        prefix = str(Path(args.path_prefix).expanduser())
        events = [e for e in events if e["cwd"].startswith(prefix)]

    if not events:
        print("No activity events found for this filter.")
        return

    for ev in events:
        ev["_dt"] = datetime.fromisoformat(ev["ts"])

    if args.project or args.path_prefix:
        report_active_time(events, args.idle_minutes)
        return

    # No filter given — group by inferred client so each separates out automatically
    by_client: dict[str, list[dict]] = {}
    for ev in events:
        by_client.setdefault(infer_client(ev["cwd"]), []).append(ev)

    grand_total = 0.0
    for client in sorted(by_client):
        print(f"\n=== {client} ===")
        grand_total += report_active_time(by_client[client], args.idle_minutes)

    print(f"\nGrand total across all clients: {grand_total:.2f}h")


if __name__ == "__main__":
    main()
