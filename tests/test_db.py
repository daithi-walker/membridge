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
