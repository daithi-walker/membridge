"""Aggregate engaged-work time per tag per local day.

Domain-neutral: this turns `activity_events` + `session_tags` into
``{local_date: {tag: hours}}``. MemBridge attaches no meaning to a tag; a
downstream consumer (e.g. a timesheet filler) owns any tag -> external-code
mapping. Nothing here knows about clients, projects, or timesheets.

Model
-----
1. Per session, pair each prompt with the next stop in the same session into an
   active interval (Claude was working the whole span). Small within-session gaps
   (<= ``idle_seconds``) are bridged as reading/thinking time.
2. Each interval is split at LOCAL midnight so a session that runs past midnight
   is attributed to both days.
3. A session's time for a day is split across its tags by normalised weight; an
   untagged session's time buckets under ``UNTAGGED`` so nothing is silently lost.

Caveats (v1): two sessions that carry the same tag and overlap in wall-clock time
are summed, so genuinely-parallel same-tag work can over-count. Cross-session gap
bridging (see scripts/heartbeat_report.py, which merges across sessions for one
client) is intentionally not applied here, because per-tag weighting and
cross-session interval union don't compose cleanly. Refine when it matters.
"""
from __future__ import annotations

from datetime import datetime, timedelta, tzinfo

from . import db

UNTAGGED = "(untagged)"


def _active_intervals_by_session(
    events: list[dict],
) -> dict[str, list[tuple[datetime, datetime]]]:
    """Pair prompt -> next stop per session. Mirrors heartbeat_report's pairing but
    keys the result by session_id and drops zero-length (still-open) intervals."""
    by_session: dict[str, list[dict]] = {}
    for ev in events:
        by_session.setdefault(ev["session_id"], []).append(ev)

    out: dict[str, list[tuple[datetime, datetime]]] = {}
    for sid, evs in by_session.items():
        evs.sort(key=lambda e: e["_dt"])
        spans: list[tuple[datetime, datetime]] = []
        pending: datetime | None = None
        for ev in evs:
            if ev["kind"] == "prompt":
                pending = ev["_dt"]  # a new prompt supersedes an unclosed one
            elif ev["kind"] == "stop" and pending is not None:
                if ev["_dt"] > pending:
                    spans.append((pending, ev["_dt"]))
                pending = None
        if spans:
            out[sid] = spans
    return out


def _merge(
    spans: list[tuple[datetime, datetime]], tolerance_seconds: int
) -> list[tuple[datetime, datetime]]:
    """Union spans that overlap or sit within `tolerance_seconds` of each other."""
    if not spans:
        return []
    tol = timedelta(seconds=tolerance_seconds)
    ordered = sorted(spans, key=lambda x: x[0])
    merged: list[list[datetime]] = [list(ordered[0])]
    for s, e in ordered[1:]:
        if s <= merged[-1][1] + tol:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _split_by_local_day(
    start: datetime, end: datetime, tz: tzinfo | None
) -> list[tuple[str, float]]:
    """Break [start, end) at local midnight -> [(YYYY-MM-DD, seconds), ...]."""
    start = start.astimezone(tz)
    end = end.astimezone(tz)
    out: list[tuple[str, float]] = []
    cur = start
    while cur < end:
        next_midnight = cur.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        seg_end = min(end, next_midnight)
        out.append((cur.date().isoformat(), (seg_end - cur).total_seconds()))
        cur = seg_end
    return out


def active_seconds_by_tag(
    since: str | None = None,
    until: str | None = None,
    tz: tzinfo | None = None,
    idle_seconds: int = 900,
) -> dict[str, dict[str, float]]:
    """Return ``{local_date: {tag: seconds}}`` over the given event window.

    `since`/`until` are ISO-8601 UTC strings matched against event timestamps (as
    in db.get_activity_events). `tz` defaults to the host's local zone. Untagged
    sessions bucket under :data:`UNTAGGED`."""
    events = db.get_activity_events(since=since, until=until)
    if not events:
        return {}
    for ev in events:
        ev["_dt"] = datetime.fromisoformat(ev["ts"])

    intervals = _active_intervals_by_session(events)
    tag_map = db.get_tags_for_sessions(list(intervals.keys()))

    result: dict[str, dict[str, float]] = {}
    for sid, spans in intervals.items():
        merged = _merge(spans, idle_seconds)
        # Normalised {tag: fraction} for this session (untagged -> single bucket).
        tags = tag_map.get(sid) or []
        total_w = sum(t["weight"] for t in tags) or 0.0
        fractions = (
            {t["tag"]: t["weight"] / total_w for t in tags}
            if total_w > 0
            else {UNTAGGED: 1.0}
        )
        for start, end in merged:
            for day, secs in _split_by_local_day(start, end, tz):
                bucket = result.setdefault(day, {})
                for tag, frac in fractions.items():
                    bucket[tag] = bucket.get(tag, 0.0) + secs * frac
    return result


def active_hours_by_tag(
    since: str | None = None,
    until: str | None = None,
    tz: tzinfo | None = None,
    idle_seconds: int = 900,
    round_to: int = 2,
) -> dict[str, dict[str, float]]:
    """Same as :func:`active_seconds_by_tag` but in hours, rounded to `round_to`."""
    secs = active_seconds_by_tag(since=since, until=until, tz=tz, idle_seconds=idle_seconds)
    return {
        day: {tag: round(s / 3600, round_to) for tag, s in tags.items()}
        for day, tags in secs.items()
    }
