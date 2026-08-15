"""Unit tests for membridge.db using an in-memory SQLite database."""
import os

import pytest

# Point at an in-memory DB before importing db module
os.environ["MEMBRIDGE_DB"] = ":memory:"

from membridge import db  # noqa: E402 — import after env var is set


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Each test gets a fresh on-disk temp DB so the module-level DB_PATH doesn't share state."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()
    yield


# ── heartbeat upsert ──────────────────────────────────────────────────────────

def test_upsert_creates_new_session():
    result = db.upsert_heartbeat(
        session_id="abc123", cwd="/tmp/proj", branch="main",
        iterm_tab="proj · main", pid=9999,
    )
    assert result.is_new
    session = db.get_session("abc123")
    assert session is not None
    assert session["project_name"] == "proj"
    assert session["prompt_count"] == 1


def test_upsert_increments_prompt_count():
    db.upsert_heartbeat(session_id="abc123", cwd="/tmp/proj", branch="main", iterm_tab=None)
    db.upsert_heartbeat(session_id="abc123", cwd="/tmp/proj", branch="main", iterm_tab=None)
    session = db.get_session("abc123")
    assert session["prompt_count"] == 2


def test_upsert_existing_returns_not_new():
    db.upsert_heartbeat(session_id="abc123", cwd="/tmp/proj", branch="main", iterm_tab=None)
    result = db.upsert_heartbeat(session_id="abc123", cwd="/tmp/proj", branch="main", iterm_tab=None)
    assert not result.is_new


def test_upsert_detects_uuid_change():
    db.upsert_heartbeat(
        session_id="abc123", cwd="/tmp", branch=None, iterm_tab=None,
        iterm_session_uuid="uuid-old",
    )
    result = db.upsert_heartbeat(
        session_id="abc123", cwd="/tmp", branch=None, iterm_tab=None,
        iterm_session_uuid="uuid-new",
    )
    assert result.uuid_changed


# ── record_stop / awaiting_input ─────────────────────────────────────────────

def test_record_stop_sets_awaiting_input():
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    was_awaiting = db.record_stop("s1", "end_turn")
    assert not was_awaiting
    session = db.get_session("s1")
    assert session["awaiting_input"] == 1


def test_record_stop_returns_true_if_already_awaiting():
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    db.record_stop("s1", "end_turn")
    was_awaiting = db.record_stop("s1", "end_turn")
    assert was_awaiting


def test_touch_clears_awaiting_input():
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    db.record_stop("s1", "end_turn")
    db.touch_session("s1")
    session = db.get_session("s1")
    assert session["awaiting_input"] == 0


# ── summary dedup ─────────────────────────────────────────────────────────────

def test_add_summary_and_retrieve():
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    db.add_summary("s1", "Summary text", source="auto")
    summaries = db.get_summaries("s1")
    assert len(summaries) == 1
    assert summaries[0]["text"] == "Summary text"


def test_last_auto_summary_text():
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    assert db.last_auto_summary_text("s1") is None
    db.add_summary("s1", "First", source="auto")
    db.add_summary("s1", "Second", source="auto")
    assert db.last_auto_summary_text("s1") == "Second"


def test_summary_file_already_ingested():
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    assert not db.summary_file_already_ingested("/tmp/test.md")
    db.add_summary("s1", "text", source="skill", file_path="/tmp/test.md")
    assert db.summary_file_already_ingested("/tmp/test.md")


# ── settings ──────────────────────────────────────────────────────────────────

def test_default_settings_present():
    settings = db.get_settings()
    assert "active_threshold_secs" in settings
    assert settings["active_threshold_secs"] == 300


def test_update_settings():
    db.update_settings({"active_threshold_secs": 120})
    settings = db.get_settings()
    assert settings["active_threshold_secs"] == 120


# ── status helpers ────────────────────────────────────────────────────────────

def test_list_sessions_empty():
    assert db.list_sessions() == []


def test_list_sessions_returns_session_row():
    db.upsert_heartbeat(session_id="s1", cwd="/tmp/p", branch="feat", iterm_tab=None)
    rows = db.list_sessions()
    assert len(rows) == 1
    assert rows[0]["session_id"] == "s1"


def test_delete_session():
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    db.delete_session("s1")
    assert db.get_session("s1") is None


def test_set_archived_and_starred():
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    db.set_archived("s1", True)
    db.set_starred("s1", True)
    s = db.get_session("s1")
    assert s["archived"] == 1
    assert s["starred"] == 1


# ── session links ─────────────────────────────────────────────────────────────

def _make(sid, branch="main"):
    db.upsert_heartbeat(session_id=sid, cwd=f"/tmp/{sid}", branch=branch, iterm_tab=None)


def test_add_link_bidirectional():
    _make("aaa")
    _make("bbb")
    assert db.add_link("aaa", "bbb") is True
    assert [lnk["session_id"] for lnk in db.get_links("aaa")] == ["bbb"]
    assert [lnk["session_id"] for lnk in db.get_links("bbb")] == ["aaa"]


def test_add_link_canonical_dedup():
    _make("aaa")
    _make("bbb")
    db.add_link("aaa", "bbb")
    # Adding in reverse order should be a no-op
    assert db.add_link("bbb", "aaa") is False
    assert len(db.get_links("aaa")) == 1


def test_add_link_self_returns_false():
    _make("aaa")
    assert db.add_link("aaa", "aaa") is False
    assert db.get_links("aaa") == []


def test_remove_link():
    _make("aaa")
    _make("bbb")
    db.add_link("aaa", "bbb")
    assert db.remove_link("aaa", "bbb") is True
    assert db.get_links("aaa") == []
    assert db.get_links("bbb") == []


def test_remove_link_nonexistent():
    _make("aaa")
    _make("bbb")
    assert db.remove_link("aaa", "bbb") is False


def test_get_links_empty():
    _make("aaa")
    assert db.get_links("aaa") == []


def test_get_links_metadata():
    _make("aaa")
    _make("bbb", branch="feat")
    db.update_notes("bbb", "some notes")
    db.add_link("aaa", "bbb")
    links = db.get_links("aaa")
    assert len(links) == 1
    assert links[0]["session_id"] == "bbb"
    assert links[0]["project_name"] == "bbb"
    assert links[0]["git_branch"] == "feat"
    assert "last_seen" in links[0]


def test_cascade_delete_removes_links():
    _make("aaa")
    _make("bbb")
    db.add_link("aaa", "bbb")
    db.delete_session("aaa")
    # Link should be gone from both sides
    assert db.get_links("bbb") == []


def test_list_sessions_includes_linked_ids():
    _make("aaa")
    _make("bbb")
    db.add_link("aaa", "bbb")
    rows = {r["session_id"]: r for r in db.list_sessions()}
    assert "bbb" in rows["aaa"]["linked_session_ids"]
    assert "aaa" in rows["bbb"]["linked_session_ids"]


# ── activity_events (append-only, kind='prompt'/'stop') ───────────────────────

def test_prompt_event_recorded_on_new_session():
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj", branch="main", iterm_tab=None)
    events = db.get_activity_events(kind="prompt")
    assert len(events) == 1
    assert events[0]["session_id"] == "aaa"
    assert events[0]["project_name"] == "proj"
    assert events[0]["kind"] == "prompt"
    assert "ts" in events[0]


def test_prompt_event_stores_full_text_and_transcript_path():
    db.upsert_heartbeat(
        session_id="aaa", cwd="/tmp/proj", branch="main", iterm_tab=None,
        prompt="what's the shape of the data?",
        transcript_path="/Users/x/.claude/projects/-tmp-proj/aaa.jsonl",
    )
    events = db.get_activity_events(kind="prompt")
    assert events[0]["text"] == "what's the shape of the data?"
    assert events[0]["transcript_path"] == "/Users/x/.claude/projects/-tmp-proj/aaa.jsonl"


def test_prompt_event_text_defaults_to_none():
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj", branch="main", iterm_tab=None)
    events = db.get_activity_events(kind="prompt")
    assert events[0]["text"] is None
    assert events[0]["transcript_path"] is None


def test_prompt_event_recorded_on_every_prompt():
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj", branch="main", iterm_tab=None)
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj", branch="main", iterm_tab=None)
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj", branch="main", iterm_tab=None)
    events = db.get_activity_events(kind="prompt")
    assert len(events) == 3
    # last_seen on the session row only keeps the endpoints, unlike the event log
    session = db.get_session("aaa")
    assert session["prompt_count"] == 3


def test_activity_events_filtered_by_project():
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj-a", branch=None, iterm_tab=None)
    db.upsert_heartbeat(session_id="bbb", cwd="/tmp/proj-b", branch=None, iterm_tab=None)
    events = db.get_activity_events(project_name="proj-a")
    assert len(events) == 1
    assert events[0]["session_id"] == "aaa"


def test_activity_events_filtered_by_time_range():
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj", branch=None, iterm_tab=None)
    all_events = db.get_activity_events()
    ts = all_events[0]["ts"]
    # since == ts is inclusive
    assert len(db.get_activity_events(since=ts)) == 1
    # a since strictly after ts excludes it
    assert len(db.get_activity_events(since=ts + "1")) == 0


def test_activity_events_ordered_oldest_first():
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj", branch=None, iterm_tab=None)
    db.upsert_heartbeat(session_id="bbb", cwd="/tmp/proj", branch=None, iterm_tab=None)
    events = db.get_activity_events()
    assert [e["session_id"] for e in events] == ["aaa", "bbb"]


def test_cascade_delete_removes_activity_events():
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj", branch=None, iterm_tab=None)
    db.delete_session("aaa")
    assert db.get_activity_events() == []


def test_stop_event_stores_full_text_and_transcript_path():
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj", branch=None, iterm_tab=None)
    db.record_stop(
        "aaa", "end_turn",
        last_assistant_message="here's the answer...",
        transcript_path="/Users/x/.claude/projects/-tmp-proj/aaa.jsonl",
    )
    events = db.get_activity_events(kind="stop")
    assert events[0]["text"] == "here's the answer..."
    assert events[0]["transcript_path"] == "/Users/x/.claude/projects/-tmp-proj/aaa.jsonl"


def test_stop_event_recorded():
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj", branch=None, iterm_tab=None)
    db.record_stop("aaa", "end_turn")
    events = db.get_activity_events(kind="stop")
    assert len(events) == 1
    assert events[0]["session_id"] == "aaa"
    assert events[0]["project_name"] == "proj"
    assert events[0]["stop_reason"] == "end_turn"


def test_stop_event_not_recorded_for_unknown_session():
    # No prior heartbeat -> no sessions row -> stop event skipped (FK safety)
    db.record_stop("never-seen", "end_turn")
    assert db.get_activity_events(kind="stop") == []


def test_stop_events_recorded_on_every_stop():
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj", branch=None, iterm_tab=None)
    db.record_stop("aaa", "end_turn")
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj", branch=None, iterm_tab=None)
    db.record_stop("aaa", "end_turn")
    assert len(db.get_activity_events(kind="stop")) == 2


def test_prompt_and_stop_events_interleave_in_one_timeline():
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj", branch=None, iterm_tab=None)
    db.record_stop("aaa", "end_turn")
    events = db.get_activity_events()
    assert [e["kind"] for e in events] == ["prompt", "stop"]


def test_cascade_delete_removes_stop_events():
    db.upsert_heartbeat(session_id="aaa", cwd="/tmp/proj", branch=None, iterm_tab=None)
    db.record_stop("aaa", "end_turn")
    db.delete_session("aaa")
    assert db.get_activity_events(kind="stop") == []


# ── session tags ────────────────────────────────────────────────────────────

def _mk(session_id="aaa", cwd="/tmp/proj"):
    db.upsert_heartbeat(session_id=session_id, cwd=cwd, branch=None, iterm_tab=None)


def test_add_and_get_session_tag():
    _mk()
    assert db.add_session_tag("aaa", "client-x") is True
    tags = db.get_session_tags("aaa")
    assert tags == [{"tag": "client-x", "weight": 1.0}]


def test_add_session_tag_blank_rejected():
    _mk()
    assert db.add_session_tag("aaa", "   ") is False
    assert db.get_session_tags("aaa") == []


def test_add_session_tag_trims_whitespace():
    _mk()
    db.add_session_tag("aaa", "  client-x  ")
    assert db.get_session_tags("aaa") == [{"tag": "client-x", "weight": 1.0}]


def test_add_session_tag_reweights_on_conflict():
    _mk()
    db.add_session_tag("aaa", "client-x", 1.0)
    db.add_session_tag("aaa", "client-x", 0.25)
    assert db.get_session_tags("aaa") == [{"tag": "client-x", "weight": 0.25}]


def test_remove_session_tag():
    _mk()
    db.add_session_tag("aaa", "client-x")
    assert db.remove_session_tag("aaa", "client-x") is True
    assert db.get_session_tags("aaa") == []


def test_remove_session_tag_nonexistent():
    _mk()
    assert db.remove_session_tag("aaa", "nope") is False


def test_set_session_tags_replaces_set():
    _mk()
    db.add_session_tag("aaa", "old")
    result = db.set_session_tags("aaa", [
        {"tag": "client-x", "weight": 0.75},
        {"tag": "client-y", "weight": 0.25},
    ])
    assert result == [
        {"tag": "client-x", "weight": 0.75},
        {"tag": "client-y", "weight": 0.25},
    ]
    # 'old' is gone; only the new set remains
    got = {t["tag"] for t in db.get_session_tags("aaa")}
    assert got == {"client-x", "client-y"}


def test_set_session_tags_accepts_mapping_and_drops_blanks():
    _mk()
    db.set_session_tags("aaa", {"client-x": 1.0, "  ": 2.0, "client-y": 0.5})
    got = {t["tag"] for t in db.get_session_tags("aaa")}
    assert got == {"client-x", "client-y"}


def test_set_session_tags_bad_weight_falls_back_to_one():
    _mk()
    db.set_session_tags("aaa", [{"tag": "client-x", "weight": "notanumber"}])
    assert db.get_session_tags("aaa") == [{"tag": "client-x", "weight": 1.0}]


def test_set_session_tags_empty_clears():
    _mk()
    db.add_session_tag("aaa", "client-x")
    db.set_session_tags("aaa", [])
    assert db.get_session_tags("aaa") == []


def test_list_all_tags_orders_by_usage():
    _mk("aaa")
    _mk("bbb", cwd="/tmp/proj2")
    db.add_session_tag("aaa", "common")
    db.add_session_tag("bbb", "common")
    db.add_session_tag("aaa", "rare")
    assert db.list_all_tags() == ["common", "rare"]


def test_get_tags_for_sessions_bulk():
    _mk("aaa")
    _mk("bbb", cwd="/tmp/proj2")
    db.add_session_tag("aaa", "client-x")
    db.add_session_tag("bbb", "client-y")
    got = db.get_tags_for_sessions(["aaa", "bbb", "ccc"])
    assert got["aaa"] == [{"tag": "client-x", "weight": 1.0}]
    assert got["bbb"] == [{"tag": "client-y", "weight": 1.0}]
    assert "ccc" not in got


def test_get_tags_for_sessions_empty_input():
    assert db.get_tags_for_sessions([]) == {}


def test_cascade_delete_removes_tags():
    _mk()
    db.add_session_tag("aaa", "client-x")
    db.delete_session("aaa")
    assert db.get_tags_for_sessions(["aaa"]) == {}


def test_list_sessions_includes_tags():
    _mk()
    db.add_session_tag("aaa", "client-x", 0.5)
    rows = {r["session_id"]: r for r in db.list_sessions()}
    assert rows["aaa"]["tags"] == [{"tag": "client-x", "weight": 0.5}]
