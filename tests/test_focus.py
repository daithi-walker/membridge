"""Unit tests for membridge/focus.py.

All osascript/subprocess calls are mocked — no real iTerm2 required.
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from membridge import focus

# ── Validator helpers ─────────────────────────────────────────────────────────

class TestSafePath:
    def test_accepts_normal_path(self):
        assert focus._safe_path("/Users/you/git/myproject") == "/Users/you/git/myproject"

    def test_accepts_path_with_spaces(self):
        assert focus._safe_path("/Users/foo/my project") == "/Users/foo/my project"

    def test_rejects_semicolon(self):
        with pytest.raises(ValueError, match="Unsafe path"):
            focus._safe_path("/tmp/proj; echo pwned")

    def test_rejects_backtick(self):
        with pytest.raises(ValueError, match="Unsafe path"):
            focus._safe_path("/tmp/`id`")

    def test_rejects_ampersand(self):
        with pytest.raises(ValueError, match="Unsafe path"):
            focus._safe_path("/tmp/a && rm -rf /")

    def test_rejects_dollar(self):
        with pytest.raises(ValueError, match="Unsafe path"):
            focus._safe_path("/tmp/$HOME")


class TestSafeId:
    def test_accepts_uuid_style_id(self):
        sid = "abc123-DEF456_ok"
        assert focus._safe_id(sid) == sid

    def test_rejects_semicolon(self):
        with pytest.raises(ValueError, match="Unsafe session_id"):
            focus._safe_id("abc;rm -rf /")

    def test_rejects_slash(self):
        with pytest.raises(ValueError, match="Unsafe session_id"):
            focus._safe_id("abc/def")

    def test_rejects_space(self):
        with pytest.raises(ValueError, match="Unsafe session_id"):
            focus._safe_id("abc def")


# ── pid_alive ─────────────────────────────────────────────────────────────────

class TestPidAlive:
    def test_alive_pid(self):
        with patch("membridge.focus.os.kill") as mock_kill:
            mock_kill.return_value = None  # no exception = process exists
            assert focus.pid_alive(12345) is True
            mock_kill.assert_called_once_with(12345, 0)

    def test_dead_pid(self):
        with patch("membridge.focus.os.kill", side_effect=ProcessLookupError):
            assert focus.pid_alive(99999) is False

    def test_no_permission_means_alive(self):
        # PermissionError = process exists but we can't signal it
        with patch("membridge.focus.os.kill", side_effect=PermissionError):
            assert focus.pid_alive(1) is True


# ── pid_to_tty ────────────────────────────────────────────────────────────────

class TestPidToTty:
    def test_returns_tty(self):
        mock_result = MagicMock()
        mock_result.stdout = "s003\n"
        with patch("membridge.focus.subprocess.run", return_value=mock_result) as mock_run:
            tty = focus.pid_to_tty(42)
            assert tty == "s003"
            mock_run.assert_called_once()

    def test_returns_none_for_no_tty(self):
        mock_result = MagicMock()
        mock_result.stdout = "??\n"
        with patch("membridge.focus.subprocess.run", return_value=mock_result):
            assert focus.pid_to_tty(42) is None

    def test_returns_none_for_empty(self):
        mock_result = MagicMock()
        mock_result.stdout = "   \n"
        with patch("membridge.focus.subprocess.run", return_value=mock_result):
            assert focus.pid_to_tty(42) is None

    def test_returns_none_on_exception(self):
        with patch("membridge.focus.subprocess.run", side_effect=subprocess.TimeoutExpired("ps", 3)):
            assert focus.pid_to_tty(42) is None


# ── _run (osascript wrapper) ──────────────────────────────────────────────────

class TestRun:
    def test_returns_stripped_stdout(self):
        mock_result = MagicMock()
        mock_result.stdout = "  focused  \n"
        with patch("membridge.focus.subprocess.run", return_value=mock_result):
            assert focus._run("some script") == "focused"


# ── focus_session ─────────────────────────────────────────────────────────────

class TestFocusSession:
    def test_focuses_by_uuid(self):
        with patch("membridge.focus._run", return_value="focused") as mock_run:
            result = focus.focus_session(
                session_id="abc123",
                iterm_uuid="SOME-UUID",
                cwd="/tmp/proj",
            )
            assert result == "focused"
            assert mock_run.call_count == 1

    def test_falls_through_to_tty_when_uuid_fails(self):
        calls = []
        def side_effect(script, timeout=5):
            calls.append(script)
            if "targetUUID" in script:
                return "not_found"
            if "targetTty" in script:
                return "focused"
            return "opened"

        mock_tty = MagicMock(return_value="s003")
        with patch("membridge.focus._run", side_effect=side_effect), \
             patch("membridge.focus.pid_to_tty", mock_tty):
            result = focus.focus_session(
                session_id="abc123",
                iterm_uuid="SOME-UUID",
                pid=42,
                cwd="/tmp/proj",
            )
        assert result == "focused"

    def test_opens_new_tab_when_focus_fails(self):
        with patch("membridge.focus._run", return_value="opened"):
            result = focus.focus_session(
                session_id="abc123",
                cwd="/tmp/proj",
            )
        assert result == "opened"

    def test_unsafe_cwd_falls_back_to_home(self):
        with patch("membridge.focus._run", return_value="opened") as mock_run:
            result = focus.focus_session(
                session_id="abc123",
                cwd="/tmp/evil; rm -rf /",
            )
        assert result == "opened"
        # The script that was run should not contain the injection
        called_script = mock_run.call_args[0][0]
        assert "evil; rm -rf" not in called_script

    def test_unsafe_session_id_gets_truncated_fallback(self):
        with patch("membridge.focus._run", return_value="opened") as mock_run:
            result = focus.focus_session(
                session_id="abc123!!bad",
                cwd="/tmp/proj",
            )
        assert result == "opened"
        called_script = mock_run.call_args[0][0]
        assert "!!bad" not in called_script


# ── rename_tab ────────────────────────────────────────────────────────────────

class TestRenameTab:
    def test_returns_run_result(self):
        with patch("membridge.focus._run", return_value="renamed") as mock_run:
            result = focus.rename_tab("old tab", "new tab")
            assert result == "renamed"
            script = mock_run.call_args[0][0]
            assert "old tab" in script
            assert "new tab" in script

    def test_escapes_quotes_in_names(self):
        with patch("membridge.focus._run", return_value="renamed") as mock_run:
            focus.rename_tab('tab "quoted"', 'new "name"')
            script = mock_run.call_args[0][0]
            assert '\\"quoted\\"' in script
            assert '\\"name\\"' in script


# ── list_sessions ─────────────────────────────────────────────────────────────

class TestListSessions:
    def test_parses_comma_separated(self):
        with patch("membridge.focus._run", return_value="tab1, tab2, tab3"):
            result = focus.list_sessions()
            assert result == ["tab1", "tab2", "tab3"]

    def test_returns_empty_list_for_empty_output(self):
        with patch("membridge.focus._run", return_value=""):
            result = focus.list_sessions()
            assert result == []


# ── is_session_frontmost ──────────────────────────────────────────────────────

class TestIsSessionFrontmost:
    def test_returns_true_when_frontmost(self):
        with patch("membridge.focus._run", return_value="true"):
            assert focus.is_session_frontmost("SOME-UUID") is True

    def test_returns_false_when_not_frontmost(self):
        with patch("membridge.focus._run", return_value="false"):
            assert focus.is_session_frontmost("SOME-UUID") is False

    def test_returns_false_on_exception(self):
        with patch("membridge.focus._run", side_effect=subprocess.TimeoutExpired("osascript", 5)):
            assert focus.is_session_frontmost("SOME-UUID") is False
