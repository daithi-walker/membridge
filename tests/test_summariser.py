"""Unit tests for membridge/summariser.py.

Anthropic API calls are mocked — no real network required.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from membridge import summariser


def _write_transcript(path: Path, turns: list[dict]) -> None:
    """Write a JSONL transcript file in Claude Code format."""
    with path.open("w") as f:
        for turn in turns:
            f.write(json.dumps(turn) + "\n")


def _make_user_turn(text: str) -> dict:
    return {
        "type": "user",
        "message": {"content": [{"type": "text", "text": text}]},
    }


def _make_assistant_turn(text: str) -> dict:
    return {
        "role": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
    }


# ── _read_transcript ──────────────────────────────────────────────────────────

class TestReadTranscript:
    def test_returns_none_for_missing_file(self, tmp_path):
        result = summariser._read_transcript(str(tmp_path / "nope.jsonl"))
        assert result is None

    def test_parses_user_and_assistant_turns(self, tmp_path):
        p = tmp_path / "session.jsonl"
        _write_transcript(p, [
            _make_user_turn("Hello"),
            _make_assistant_turn("Hi there"),
        ])
        turns = summariser._read_transcript(str(p))
        assert turns is not None
        assert len(turns) == 2
        assert turns[0] == {"role": "user", "content": "Hello"}
        assert turns[1] == {"role": "assistant", "content": "Hi there"}

    def test_skips_blank_lines_and_bad_json(self, tmp_path):
        p = tmp_path / "session.jsonl"
        p.write_text(
            json.dumps(_make_user_turn("Hello")) + "\n"
            + "\n"
            + "not json\n"
            + json.dumps(_make_assistant_turn("Ok")) + "\n"
        )
        turns = summariser._read_transcript(str(p))
        assert turns is not None
        assert len(turns) == 2

    def test_returns_none_for_empty_transcript(self, tmp_path):
        p = tmp_path / "session.jsonl"
        p.write_text("")
        result = summariser._read_transcript(str(p))
        assert result is None

    def test_returns_none_for_turns_with_only_whitespace(self, tmp_path):
        p = tmp_path / "session.jsonl"
        _write_transcript(p, [_make_user_turn("   ")])
        result = summariser._read_transcript(str(p))
        assert result is None

    def test_limits_to_max_turns(self, tmp_path):
        p = tmp_path / "session.jsonl"
        many_turns = [_make_user_turn(f"msg {i}") for i in range(100)]
        _write_transcript(p, many_turns)
        turns = summariser._read_transcript(str(p))
        assert turns is not None
        assert len(turns) == summariser.MAX_TURNS


# ── _format_turns ─────────────────────────────────────────────────────────────

class TestFormatTurns:
    def test_prefixes_user_and_assistant(self):
        turns = [
            {"role": "user", "content": "Fix the bug"},
            {"role": "assistant", "content": "Done"},
        ]
        result = summariser._format_turns(turns)
        assert "USER: Fix the bug" in result
        assert "CLAUDE: Done" in result

    def test_truncates_long_content(self):
        long_text = "x" * 600
        turns = [{"role": "user", "content": long_text}]
        result = summariser._format_turns(turns)
        assert len(result) < 600
        assert "…" in result


# ── summarise ─────────────────────────────────────────────────────────────────

class TestSummarise:
    def _mock_client(self, response_text: str) -> MagicMock:
        msg = MagicMock()
        msg.content = [MagicMock(text=response_text)]
        client = MagicMock()
        client.messages.create.return_value = msg
        return client

    def test_returns_summary_text(self, tmp_path):
        p = tmp_path / "session.jsonl"
        _write_transcript(p, [
            _make_user_turn("Fix the auth bug"),
            _make_assistant_turn("Sure, let me look at it"),
        ])
        client = self._mock_client("[Fix auth bug in login.py]")
        with patch("membridge.summariser._get_client", return_value=client):
            result = summariser.summarise(str(p))
        assert result == "[Fix auth bug in login.py]"
        client.messages.create.assert_called_once()

    def test_returns_none_for_missing_transcript(self, tmp_path):
        result = summariser.summarise(str(tmp_path / "nope.jsonl"))
        assert result is None

    def test_returns_none_for_empty_transcript(self, tmp_path):
        p = tmp_path / "session.jsonl"
        p.write_text("")
        result = summariser.summarise(str(p))
        assert result is None

    def test_returns_none_on_api_error(self, tmp_path):
        p = tmp_path / "session.jsonl"
        _write_transcript(p, [_make_user_turn("Do something")])
        client = MagicMock()
        client.messages.create.side_effect = Exception("API unavailable")
        with patch("membridge.summariser._get_client", return_value=client):
            result = summariser.summarise(str(p))
        assert result is None

    def test_passes_model_and_system_prompt(self, tmp_path):
        p = tmp_path / "session.jsonl"
        _write_transcript(p, [_make_user_turn("Hello")])
        client = self._mock_client("[Something]")
        with patch("membridge.summariser._get_client", return_value=client):
            summariser.summarise(str(p))
        call_kwargs = client.messages.create.call_args[1]
        assert call_kwargs["model"] == summariser.MODEL
        assert call_kwargs["system"] == summariser.SYSTEM_PROMPT
        assert call_kwargs["max_tokens"] == 256
