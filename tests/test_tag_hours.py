"""Tests for membridge.tag_hours — active-hours-by-tag aggregation."""
import os
from datetime import timezone

import pytest

os.environ["MEMBRIDGE_DB"] = ":memory:"

from membridge import db, tag_hours  # noqa: E402

UTC = timezone.utc


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    yield


def _session(sid, cwd="/tmp/proj"):
    """Insert a bare session row (no stray activity_events, unlike upsert_heartbeat)."""
    with db._conn() as conn:
        conn.execute(
            """INSERT INTO sessions (session_id, cwd, project_name, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?)""",
            (sid, cwd, "proj", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )


def _event(sid, kind, ts_iso, cwd="/tmp/proj"):
    with db._conn() as conn:
        conn.execute(
            """INSERT INTO activity_events (session_id, project_name, cwd, kind, ts)
               VALUES (?, 'proj', ?, ?, ?)""",
            (sid, cwd, kind, ts_iso),
        )


def _span(sid, start_iso, end_iso):
    _event(sid, "prompt", start_iso)
    _event(sid, "stop", end_iso)


def _hours(**kw):
    return tag_hours.active_hours_by_tag(tz=UTC, **kw)


def test_empty_db():
    assert tag_hours.active_seconds_by_tag(tz=UTC) == {}


def test_single_tag_single_day():
    _session("s1")
    _span("s1", "2026-08-10T10:00:00+00:00", "2026-08-10T11:00:00+00:00")
    db.add_session_tag("s1", "client-x")
    assert _hours() == {"2026-08-10": {"client-x": 1.0}}


def test_untagged_buckets_separately():
    _session("s1")
    _span("s1", "2026-08-10T10:00:00+00:00", "2026-08-10T11:00:00+00:00")
    assert _hours() == {"2026-08-10": {tag_hours.UNTAGGED: 1.0}}


def test_weight_split():
    _session("s1")
    _span("s1", "2026-08-10T10:00:00+00:00", "2026-08-10T14:00:00+00:00")  # 4h
    db.set_session_tags("s1", [
        {"tag": "client-x", "weight": 0.75},
        {"tag": "client-y", "weight": 0.25},
    ])
    assert _hours() == {"2026-08-10": {"client-x": 3.0, "client-y": 1.0}}


def test_equal_weights_default():
    _session("s1")
    _span("s1", "2026-08-10T10:00:00+00:00", "2026-08-10T12:00:00+00:00")  # 2h
    db.add_session_tag("s1", "a")
    db.add_session_tag("s1", "b")
    assert _hours() == {"2026-08-10": {"a": 1.0, "b": 1.0}}


def test_midnight_split():
    _session("s1")
    _span("s1", "2026-08-10T23:30:00+00:00", "2026-08-11T00:30:00+00:00")  # 1h across midnight
    db.add_session_tag("s1", "client-x")
    assert _hours() == {
        "2026-08-10": {"client-x": 0.5},
        "2026-08-11": {"client-x": 0.5},
    }


def test_idle_gap_bridged_within_tolerance():
    _session("s1")
    _span("s1", "2026-08-10T10:00:00+00:00", "2026-08-10T10:30:00+00:00")
    _span("s1", "2026-08-10T10:40:00+00:00", "2026-08-10T11:00:00+00:00")  # 10-min gap
    db.add_session_tag("s1", "client-x")
    # idle_seconds=900 (15m) bridges the 10m gap -> one 60m block
    assert _hours(idle_seconds=900) == {"2026-08-10": {"client-x": 1.0}}


def test_idle_gap_not_bridged_when_over_tolerance():
    _session("s1")
    _span("s1", "2026-08-10T10:00:00+00:00", "2026-08-10T10:30:00+00:00")
    _span("s1", "2026-08-10T10:40:00+00:00", "2026-08-10T11:00:00+00:00")  # 10-min gap
    db.add_session_tag("s1", "client-x")
    # idle_seconds=300 (5m) does NOT bridge -> 30m + 20m = 50m = 3000s
    got = tag_hours.active_seconds_by_tag(tz=UTC, idle_seconds=300)
    assert got["2026-08-10"]["client-x"] == pytest.approx(3000.0)


def test_two_sessions_same_day_same_tag_sum():
    _session("s1")
    _session("s2", cwd="/tmp/proj2")
    _span("s1", "2026-08-10T10:00:00+00:00", "2026-08-10T11:00:00+00:00")
    _span("s2", "2026-08-10T13:00:00+00:00", "2026-08-10T14:00:00+00:00")
    db.add_session_tag("s1", "client-x")
    db.add_session_tag("s2", "client-x")
    assert _hours() == {"2026-08-10": {"client-x": 2.0}}


def test_open_prompt_without_stop_ignored():
    _session("s1")
    _event("s1", "prompt", "2026-08-10T10:00:00+00:00")  # never closed
    db.add_session_tag("s1", "client-x")
    assert tag_hours.active_seconds_by_tag(tz=UTC) == {}


def test_since_until_window():
    _session("s1")
    _span("s1", "2026-08-10T10:00:00+00:00", "2026-08-10T11:00:00+00:00")
    _span("s1", "2026-08-12T10:00:00+00:00", "2026-08-12T11:00:00+00:00")
    db.add_session_tag("s1", "client-x")
    got = _hours(since="2026-08-11T00:00:00+00:00")
    assert got == {"2026-08-12": {"client-x": 1.0}}
