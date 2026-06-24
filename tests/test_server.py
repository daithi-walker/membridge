"""API-level tests for membridge.server — covers documented hard-won features.

Each test is pegged to a feature in docs/CHANGELOG.md so regressions are visible.
"""
import os

import pytest
from fastapi.testclient import TestClient

os.environ["MEMBRIDGE_DB"] = ":memory:"

from membridge import db  # noqa: E402
from membridge.server import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ── Heartbeat / session registration ─────────────────────────────────────────
# CHANGELOG: "Session registration via UserPromptSubmit hook (heartbeat upsert, first-seen tracking)"

def test_heartbeat_creates_session(client):
    res = client.post("/api/heartbeat", json={
        "session_id": "s1", "cwd": "/tmp/proj", "branch": "main",
    })
    assert res.status_code == 200
    assert res.json()["ok"] is True
    session = db.get_session("s1")
    assert session is not None
    assert session["project_name"] == "proj"


def test_heartbeat_clears_awaiting_input(client):
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    db.record_stop("s1", "end_turn")
    assert db.get_session("s1")["awaiting_input"] == 1
    client.post("/api/heartbeat", json={"session_id": "s1", "cwd": "/tmp", "branch": "main"})
    assert db.get_session("s1")["awaiting_input"] == 0


# ── Stop hook / awaiting_input state machine ─────────────────────────────────
# CHANGELOG: "awaiting_input DB flag — set on Stop/Notification hook, cleared on heartbeat"
# CHANGELOG: "Bug fix: last_stop_reason preserved when Stop hook fires after Notification hook"

def test_stop_sets_awaiting_input(client):
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    res = client.post("/api/stop", json={"session_id": "s1", "stop_reason": "end_turn"})
    assert res.status_code == 200
    assert db.get_session("s1")["awaiting_input"] == 1


def test_stop_preserves_last_stop_reason_when_already_awaiting(client):
    """Notification hook fires first with a reason, then Stop hook fires with empty reason.
    The original reason must be preserved (ADR 010, CHANGELOG 2026-06).
    """
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    client.post("/api/notification", json={
        "session_id": "s1", "notif_type": "ask_user_question",
    })
    session_before = db.get_session("s1")
    original_reason = session_before["last_stop_reason"]

    # Stop hook fires with empty reason after notification already set awaiting
    client.post("/api/stop", json={"session_id": "s1", "stop_reason": ""})
    session_after = db.get_session("s1")
    assert session_after["last_stop_reason"] == original_reason


# ── Touch / PreToolUse hook ───────────────────────────────────────────────────
# CHANGELOG: "PreToolUse hook → /api/touch — keeps sessions active during long tool chains"
# CHANGELOG: "Bug fix: touch_session now clears awaiting_input"

def test_touch_clears_awaiting_input(client):
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    db.record_stop("s1", "end_turn")
    res = client.post("/api/touch", json={"session_id": "s1"})
    assert res.status_code == 200
    assert db.get_session("s1")["awaiting_input"] == 0


# ── Session PATCH — inline editing ───────────────────────────────────────────
# CHANGELOG: "Inline description editing in table row"
# CHANGELOG: "Archive session feature"
# CHANGELOG: "Star sessions to pin them to the top"

def test_patch_description(client):
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    res = client.patch("/api/sessions/s1", json={"description": "Working on auth refactor"})
    assert res.status_code == 200
    assert db.get_session("s1")["description"] == "Working on auth refactor"


def test_patch_archived(client):
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    res = client.patch("/api/sessions/s1", json={"archived": True})
    assert res.status_code == 200
    assert db.get_session("s1")["archived"] == 1


def test_patch_starred(client):
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    res = client.patch("/api/sessions/s1", json={"starred": True})
    assert res.status_code == 200
    assert db.get_session("s1")["starred"] == 1


def test_patch_tickets(client):
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    res = client.patch("/api/sessions/s1", json={"tickets": "PROJ-123,PROJ-456"})
    assert res.status_code == 200
    assert db.get_session("s1")["tickets"] == "PROJ-123,PROJ-456"


def test_patch_unknown_session_returns_404(client):
    res = client.patch("/api/sessions/doesnotexist", json={"description": "x"})
    assert res.status_code == 404


# ── Delete session ────────────────────────────────────────────────────────────
# CHANGELOG: "Delete session endpoint (DELETE /api/sessions/{id})"

def test_delete_session(client):
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    res = client.delete("/api/sessions/s1")
    assert res.status_code == 200
    assert db.get_session("s1") is None


def test_delete_unknown_session_returns_404(client):
    res = client.delete("/api/sessions/doesnotexist")
    assert res.status_code == 404


# ── Push summary ──────────────────────────────────────────────────────────────
# CHANGELOG: "POST /api/sessions/{id}/push-summary — slash command pushes text direct to DB"
# CHANGELOG: "Auto-summary text-match dedup"

def test_push_summary(client):
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    res = client.post("/api/sessions/s1/push-summary", json={"text": "Doing auth work", "source": "skill"})
    assert res.status_code == 200
    assert res.json()["status"] == "added"
    summaries = db.get_summaries("s1")
    assert summaries[0]["text"] == "Doing auth work"


def test_push_summary_dedup(client):
    db.upsert_heartbeat(session_id="s1", cwd="/tmp", branch=None, iterm_tab=None)
    client.post("/api/sessions/s1/push-summary", json={"text": "Same text", "source": "auto"})
    res = client.post("/api/sessions/s1/push-summary", json={"text": "Same text", "source": "auto"})
    assert res.json()["status"] == "unchanged"
    assert len(db.get_summaries("s1")) == 1


# ── Settings ──────────────────────────────────────────────────────────────────
# CHANGELOG: "Notification prefs in Settings modal — Pop-ups and Sound toggles"

def test_get_default_settings(client):
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert "active_threshold_secs" in data
    assert data["notif_popup"] == 1
    assert data["notif_sound"] == 0


def test_patch_settings(client):
    res = client.patch("/api/settings", json={"active_threshold_secs": 60})
    assert res.status_code == 200
    assert res.json()["active_threshold_secs"] == 60


def test_patch_settings_empty_body_returns_400(client):
    res = client.patch("/api/settings", json={})
    assert res.status_code == 400


# ── Status computation ────────────────────────────────────────────────────────
# CHANGELOG: "Dashboard with active/idle/stale status"

def test_sessions_list_includes_status(client):
    db.upsert_heartbeat(session_id="s1", cwd="/tmp/proj", branch="main", iterm_tab=None)
    res = client.get("/api/sessions")
    assert res.status_code == 200
    sessions = res.json()
    assert len(sessions) == 1
    assert sessions[0]["status"] in ("active", "idle", "stale")


# ── Security headers ──────────────────────────────────────────────────────────
# Added in quality review 2026-06-23

def test_security_headers_present(client):
    res = client.get("/api/sessions")
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.headers.get("x-frame-options") == "DENY"
    assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
