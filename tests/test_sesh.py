"""Tests for the sesh integration: the wrapper module, resume preference, and the
REST endpoints. No real `sesh` binary is invoked — subprocess is mocked and the
binary path is monkeypatched.
"""
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ["MEMBRIDGE_DB"] = ":memory:"

from membridge import db  # noqa: E402
from membridge import focus  # noqa: E402
from membridge import sesh  # noqa: E402
from membridge.server import app  # noqa: E402


# ── project_root / is_enabled ─────────────────────────────────────────────────

class TestProjectRoot:
    def test_none_cwd(self):
        assert sesh.project_root(None) is None
        assert sesh.is_enabled(None) is False

    def test_missing_dir(self, tmp_path):
        assert sesh.project_root(str(tmp_path / "nope")) is None

    def test_no_sesh_dir(self, tmp_path):
        assert sesh.project_root(str(tmp_path)) is None
        assert sesh.is_enabled(str(tmp_path)) is False

    def test_sesh_dir_here(self, tmp_path):
        (tmp_path / ".sesh").mkdir()
        assert sesh.project_root(str(tmp_path)) == str(tmp_path.resolve())
        assert sesh.is_enabled(str(tmp_path)) is True

    def test_sesh_dir_in_ancestor(self, tmp_path):
        (tmp_path / ".sesh").mkdir()
        child = tmp_path / "a" / "b"
        child.mkdir(parents=True)
        assert sesh.project_root(str(child)) == str(tmp_path.resolve())
        assert sesh.is_enabled(str(child)) is True


# ── availability / no-op behavior when sesh is absent ─────────────────────────

class TestNoBinary:
    def test_available_false(self, monkeypatch):
        monkeypatch.setattr(sesh, "_SESH_BIN", None)
        assert sesh.available() is False

    def test_init_reports_not_installed(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sesh, "_SESH_BIN", None)
        assert sesh.init(str(tmp_path))["ok"] is False

    def test_snapshot_noop(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sesh, "_SESH_BIN", None)
        assert sesh.snapshot(str(tmp_path)) is False

    def test_find_empty(self, monkeypatch):
        monkeypatch.setattr(sesh, "_SESH_BIN", None)
        assert sesh.find("anything") == ""


# ── subprocess invocation shape ───────────────────────────────────────────────

class TestInvocation:
    def test_snapshot_requires_enabled(self, monkeypatch, tmp_path):
        # sesh present but project not initialized → no subprocess, returns False
        monkeypatch.setattr(sesh, "_SESH_BIN", "/fake/sesh")
        with patch("membridge.sesh.subprocess.run") as run:
            assert sesh.snapshot(str(tmp_path)) is False
            run.assert_not_called()

    def test_snapshot_runs_when_enabled(self, monkeypatch, tmp_path):
        (tmp_path / ".sesh").mkdir()
        monkeypatch.setattr(sesh, "_SESH_BIN", "/fake/sesh")
        with patch("membridge.sesh.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            assert sesh.snapshot(str(tmp_path), tag="checkpoint") is True
            args = run.call_args[0][0]
            assert args == ["/fake/sesh", "snapshot", "-t", "checkpoint"]
            assert run.call_args[1]["cwd"] == str(tmp_path)

    def test_find_global_when_not_enabled(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sesh, "_SESH_BIN", "/fake/sesh")
        with patch("membridge.sesh.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0, stdout="hit\n", stderr="")
            out = sesh.find("dynamic workflow", cwd=str(tmp_path))
            assert out == "hit"
            args = run.call_args[0][0]
            assert "-g" in args
            assert args[-2:] == ["dynamic", "workflow"]

    def test_find_scoped_when_enabled(self, monkeypatch, tmp_path):
        (tmp_path / ".sesh").mkdir()
        monkeypatch.setattr(sesh, "_SESH_BIN", "/fake/sesh")
        with patch("membridge.sesh.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0, stdout="hit", stderr="")
            sesh.find("query", cwd=str(tmp_path))
            args = run.call_args[0][0]
            assert "-g" not in args
            assert run.call_args[1]["cwd"] == str(tmp_path)


# ── focus resume preference ───────────────────────────────────────────────────

class TestResumeCommand:
    def test_plain_claude_when_not_enabled(self, monkeypatch):
        monkeypatch.setattr(focus._sesh, "is_enabled", lambda cwd: False)
        cmd = focus._resume_command("/bin/claude", "/tmp/proj", "abc123")
        assert cmd == "/bin/claude --resume abc123"

    def test_prefers_sesh_when_enabled(self, monkeypatch):
        monkeypatch.setattr(focus._sesh, "available", lambda: True)
        monkeypatch.setattr(focus._sesh, "is_enabled", lambda cwd: True)
        monkeypatch.setattr(focus._sesh, "_SESH_BIN", "/usr/local/bin/sesh")
        cmd = focus._resume_command("/bin/claude", "/tmp/proj", "abc123")
        assert cmd == "/usr/local/bin/sesh resume abc123 || /bin/claude --resume abc123"

    def test_falls_back_if_sesh_unavailable(self, monkeypatch):
        monkeypatch.setattr(focus._sesh, "available", lambda: False)
        monkeypatch.setattr(focus._sesh, "is_enabled", lambda cwd: True)
        cmd = focus._resume_command("/bin/claude", "/tmp/proj", "abc123")
        assert cmd == "/bin/claude --resume abc123"


# ── REST endpoints ────────────────────────────────────────────────────────────

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


def _make_session(client, session_id="s1", cwd="/tmp/proj"):
    client.post("/api/heartbeat", json={"session_id": session_id, "cwd": cwd})


class TestEndpoints:
    def test_status_404_unknown_session(self, client):
        assert client.get("/api/sessions/nope/sesh").status_code == 404

    def test_status_reports_availability(self, client, monkeypatch):
        _make_session(client)
        monkeypatch.setattr("membridge.server._sesh.available", lambda: True)
        monkeypatch.setattr("membridge.server._sesh.is_enabled", lambda cwd: False)
        monkeypatch.setattr("membridge.server._sesh.project_root", lambda cwd: None)
        body = client.get("/api/sessions/s1/sesh").json()
        assert body == {"available": True, "enabled": False, "root": None}

    def test_init_503_when_unavailable(self, client, monkeypatch):
        _make_session(client)
        monkeypatch.setattr("membridge.server._sesh.available", lambda: False)
        assert client.post("/api/sessions/s1/sesh/init").status_code == 503

    def test_init_success(self, client, monkeypatch):
        _make_session(client)
        monkeypatch.setattr("membridge.server._sesh.available", lambda: True)
        monkeypatch.setattr(
            "membridge.server._sesh.init",
            lambda cwd: {"ok": True, "root": cwd, "output": "initialized"},
        )
        res = client.post("/api/sessions/s1/sesh/init")
        assert res.status_code == 200
        assert res.json()["ok"] is True

    def test_snapshot_400_when_not_enabled(self, client, monkeypatch):
        _make_session(client)
        monkeypatch.setattr("membridge.server._sesh.is_enabled", lambda cwd: False)
        assert client.post("/api/sessions/s1/sesh/snapshot").status_code == 400

    def test_snapshots_log(self, client, monkeypatch):
        _make_session(client)
        monkeypatch.setattr("membridge.server._sesh.is_enabled", lambda cwd: True)
        monkeypatch.setattr("membridge.server._sesh.snapshots", lambda cwd: "snap log")
        body = client.get("/api/sessions/s1/sesh/snapshots").json()
        assert body == {"enabled": True, "log": "snap log"}

    def test_find_requires_query(self, client):
        assert client.get("/api/sesh/find?q=").status_code == 400

    def test_find_returns_result(self, client, monkeypatch):
        monkeypatch.setattr("membridge.server._sesh.available", lambda: True)
        monkeypatch.setattr("membridge.server._sesh.find", lambda q, cwd=None: "found it")
        body = client.get("/api/sesh/find?q=workflow").json()
        assert body["result"] == "found it"
