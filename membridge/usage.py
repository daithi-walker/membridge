"""Ingest per-call token usage from Claude Code transcripts into `api_calls`.

Claude Code writes one JSONL row per assistant content block, and every row of a
call carries the same `usage` (sometimes a partial output count on the first
copy). Calls are therefore keyed by the API's (message id, request id) and merged,
never summed. Subagents write their own transcripts under
``<session-dir>/subagents/*.jsonl``; their rows carry the parent `sessionId` plus
an `agentId`, so they roll up into the parent session.

Each ingest re-parses the whole transcript and replaces its rows, so the result is
always the transcript's final state (~1s for a 200 MB transcript).
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from . import costs, db

logger = logging.getLogger(__name__)

# Session auth modes the heartbeat hook reports. Anything except "subscription" is
# billed per token.
AUTH_MODES = ("vertex", "bedrock", "foundry", "api", "subscription")

# Vertex AI message ids are prefixed `msg_vrtx_`, which identifies Vertex calls even
# in history recorded before auth_mode existed.
_VERTEX_ID_PREFIX = "msg_vrtx_"

_MODEL_SUFFIX_RE = re.compile(r"(\[1m\]|@.*|-\d{8})$")


def normalise_model(model: str | None) -> str | None:
    """`claude-opus-5-5[1m]`, `claude-sonnet-4-5@20250929` and
    `claude-haiku-4-5-20251001` all map to their pricing.toml key. Claude Code's
    `<synthetic>` placeholder messages are not API calls and map to None."""
    if not model or model.startswith("<"):
        return None
    return _MODEL_SUFFIX_RE.sub("", model)


def _utc_iso(ts: str | None) -> str:
    """Transcript timestamps end in `Z`; store them like db._now() (`+00:00`) so
    they compare correctly with activity_events timestamps."""
    try:
        return datetime.fromisoformat((ts or "").replace("Z", "+00:00")).astimezone(UTC).isoformat()
    except ValueError:
        return ""


def parse_rows(lines: Iterable[str], auth_mode: str | None = None) -> list[db.ApiCall]:
    """Turn transcript JSONL lines into merged, priced ApiCall records."""
    calls: dict[tuple[str, str], db.ApiCall] = {}
    for line in lines:
        if '"usage"' not in line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("Skipping unparseable transcript line: %.80s", line)
            continue
        msg = row.get("message") or {}
        usage = msg.get("usage")
        model = normalise_model(msg.get("model"))
        message_id = msg.get("id")
        session_id = row.get("sessionId") or row.get("session_id")
        ts = _utc_iso(row.get("timestamp"))
        if row.get("type") != "assistant" or not (usage and model and message_id and session_id and ts):
            continue
        write_1h = (usage.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0
        call: db.ApiCall = {
            "message_id": message_id,
            "request_id": row.get("requestId") or "",
            "session_id": session_id,
            "agent_id": row.get("agentId"),
            "ts": ts,
            "model": model,
            "auth_mode": "vertex" if message_id.startswith(_VERTEX_ID_PREFIX) else auth_mode,
            "speed": usage.get("speed") or None,
            "input_tokens": usage.get("input_tokens") or 0,
            "output_tokens": usage.get("output_tokens") or 0,
            "cache_read_tokens": usage.get("cache_read_input_tokens") or 0,
            "cache_write_5m_tokens": max((usage.get("cache_creation_input_tokens") or 0) - write_1h, 0),
            "cache_write_1h_tokens": write_1h,
            "web_search_requests": (usage.get("server_tool_use") or {}).get("web_search_requests") or 0,
            "cost_usd": None,
        }
        key = (message_id, call["request_id"])
        prev = calls.get(key)
        if prev:
            for col in db.API_CALL_TOKEN_COLS:
                prev[col] = max(prev[col], call[col])  # type: ignore[literal-required]
        else:
            calls[key] = call
    for call in calls.values():
        call["cost_usd"] = costs.price_call(call)
    return list(calls.values())


def ingest_session(session_id: str, transcript_path: str, auth_mode: str | None = None) -> int:
    """(Re)ingest a session's main transcript plus its subagent transcripts. Uses the
    session's recorded auth mode, falling back to `auth_mode`. Returns calls stored."""
    session = db.get_session(session_id)
    mode = (session or {}).get("auth_mode") or auth_mode
    main = Path(transcript_path)
    paths = [main, *sorted((main.parent / main.stem / "subagents").glob("*.jsonl"))]
    calls: list[db.ApiCall] = []
    for path in paths:
        try:
            with path.open(encoding="utf-8", errors="replace") as fh:
                calls += parse_rows(fh, mode)
        except OSError as e:
            logger.warning("Transcript unreadable, skipping usage ingest: %s (%s)", path, e)
    db.replace_api_calls(calls)
    return len(calls)
