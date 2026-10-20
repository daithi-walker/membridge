"""Tests for per-call usage ingest (membridge.usage) and cost rollups (membridge.costs).

CHANGELOG: "Session cost estimates from transcript token usage"
"""
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

os.environ["MEMBRIDGE_DB"] = ":memory:"

from membridge import costs, db, usage  # noqa: E402
from membridge.server import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    yield


def _row(msg_id, *, session="s1", ts="2026-10-20T10:00:00.000Z", model="claude-opus-5-5",
         req=None, agent=None, inp=0, out=0, read=0, write=0, write_1h=0, searches=0,
         speed="standard"):
    row = {
        "type": "assistant", "sessionId": session, "timestamp": ts,
        "requestId": req or msg_id.replace("msg", "req"),
        "message": {"id": msg_id, "model": model, "usage": {
            "input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": read,
            "cache_creation_input_tokens": write + write_1h,
            "cache_creation": {"ephemeral_5m_input_tokens": write, "ephemeral_1h_input_tokens": write_1h},
            "server_tool_use": {"web_search_requests": searches},
            "speed": speed,
        }},
    }
    if agent:
        row["agentId"] = agent
        row["isSidechain"] = True
    return json.dumps(row)


def _write(path, rows, newline=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write("\n".join(rows) + ("\n" if newline else ""))


def _call(**kw):
    base = {"model": "claude-opus-5-5", "speed": None,
            "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
            "cache_write_5m_tokens": 0, "cache_write_1h_tokens": 0, "web_search_requests": 0}
    return {**base, **kw}


def _session(sid, auth_mode=None):
    db.upsert_heartbeat(session_id=sid, cwd="/tmp/proj", branch=None, iterm_tab=None,
                        auth_mode=auth_mode)


# ── parsing ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("claude-opus-5-5", "claude-opus-5-5"),
    ("claude-opus-5-5[1m]", "claude-opus-5-5"),
    ("claude-sonnet-4-5@20250929", "claude-sonnet-4-5"),
    ("claude-haiku-4-5-20251001", "claude-haiku-4-5"),
    ("<synthetic>", None),
    (None, None),
])
def test_normalise_model(raw, expected):
    assert usage.normalise_model(raw) == expected


def test_duplicate_rows_merge_to_one_call_keeping_largest_counts():
    rows = [_row("msg_vrtx_1", out=2, read=100), _row("msg_vrtx_1", out=1105, read=100),
            _row("msg_vrtx_1", out=1105, read=100)]
    calls = usage.parse_rows(rows)
    assert len(calls) == 1
    assert calls[0]["output_tokens"] == 1105
    assert calls[0]["cache_read_tokens"] == 100


def test_parse_detects_vertex_from_id_and_falls_back_to_session_auth_mode():
    calls = {c["message_id"]: c for c in usage.parse_rows(
        [_row("msg_vrtx_1"), _row("msg_01abc")], auth_mode="subscription")}
    assert calls["msg_vrtx_1"]["auth_mode"] == "vertex"
    assert calls["msg_01abc"]["auth_mode"] == "subscription"
    assert usage.parse_rows([_row("msg_01abc")])[0]["auth_mode"] is None


def test_parse_splits_cache_writes_by_ttl_and_skips_synthetic():
    calls = usage.parse_rows([_row("msg_vrtx_1", write=300, write_1h=50),
                              _row("msg_vrtx_2", model="<synthetic>")])
    assert len(calls) == 1
    assert calls[0]["cache_write_5m_tokens"] == 300
    assert calls[0]["cache_write_1h_tokens"] == 50
    assert calls[0]["ts"] == "2026-10-20T10:00:00+00:00"


# ── ingest ───────────────────────────────────────────────────────────────────

def test_ingest_session_includes_subagents_and_prices(tmp_path):
    _session("s1", auth_mode="vertex")
    main = tmp_path / "proj" / "s1.jsonl"
    _write(main, [_row("msg_vrtx_1", out=1_000_000)])
    _write(tmp_path / "proj" / "s1" / "subagents" / "agent-a1.jsonl",
           [_row("msg_vrtx_2", agent="a1", out=1_000_000)])
    assert usage.ingest_session("s1", str(main)) == 2
    calls = db.get_api_calls("s1")
    assert {c["agent_id"] for c in calls} == {None, "a1"}
    assert [c["cost_usd"] for c in calls] == [20.0, 20.0]


def test_reingest_replaces_partial_copy_with_final_counts(tmp_path):
    path = tmp_path / "proj" / "s1.jsonl"
    _write(path, [_row("msg_vrtx_1", out=2)])
    usage.ingest_session("s1", str(path))
    _write(path, [_row("msg_vrtx_1", out=1_000_000)])
    usage.ingest_session("s1", str(path))
    [call] = db.get_api_calls("s1")
    assert call["output_tokens"] == 1_000_000
    assert call["cost_usd"] == pytest.approx(20.0)


# ── pricing ──────────────────────────────────────────────────────────────────

def test_price_call_sums_each_token_class():
    call = _call(input_tokens=1_000_000, output_tokens=1_000_000, cache_read_tokens=1_000_000,
                 cache_write_5m_tokens=1_000_000, cache_write_1h_tokens=1_000_000,
                 web_search_requests=3)
    assert costs.price_call(call) == pytest.approx(4 + 20 + 0.2 + 5 + 8 + 0.03)


def test_price_call_fast_mode_scales_input_and_cache():
    call = _call(speed="fast", input_tokens=1_000_000,
                 output_tokens=1_000_000, cache_read_tokens=1_000_000)
    assert costs.price_call(call) == pytest.approx(8 + 40 + 0.4)


def test_price_call_haiku_long_prompt_tier():
    short = _call(model="claude-haiku-5-5", input_tokens=1000, cache_read_tokens=99_000)
    long = _call(model="claude-haiku-5-5", input_tokens=1000, cache_read_tokens=100_000)
    assert costs.price_call(short) == pytest.approx((1000 * 0.10 + 99_000 * 0.01) / 1e6)
    assert costs.price_call(long) == pytest.approx((1000 * 0.50 + 100_000 * 0.05) / 1e6)


def test_price_call_unknown_model_is_none():
    assert costs.price_call(_call(model="claude-opus-9-9")) is None


# ── billing classification + rollups ─────────────────────────────────────────

def _ingest(tmp_path, sid, rows):
    path = tmp_path / "proj" / f"{sid}.jsonl"
    _write(path, rows)
    usage.ingest_session(sid, str(path))


def test_billing_vertex_billed_subscription_not_unknown_unclassified(tmp_path):
    _session("vtx", "vertex")
    _session("sub", "subscription")
    _ingest(tmp_path, "vtx", [_row("msg_vrtx_1", session="vtx", out=1_000_000)])
    _ingest(tmp_path, "sub", [_row("msg_01a", session="sub", out=1_000_000)])
    _ingest(tmp_path, "old", [_row("msg_01b", session="old", out=1_000_000)])  # no sessions row
    by = db.get_usage_by_session()
    assert by["vtx"]["billed_usd"] == pytest.approx(20.0)
    assert by["sub"]["billed_usd"] == 0 and by["sub"]["cost_usd"] == pytest.approx(20.0)
    assert by["old"]["billed_usd"] == 0
    assert {c["billing"] for c in db.get_api_calls("old")} == {"unknown"}


def test_session_usage_groups_calls_into_turns(tmp_path):
    with db._conn() as conn:
        conn.execute("""INSERT INTO sessions (session_id, cwd, project_name, first_seen, last_seen)
                        VALUES ('s1', '/tmp/proj', 'proj', '2026-10-20T09:00:00+00:00',
                                '2026-10-20T09:00:00+00:00')""")
        for ts, text in (("2026-10-20T10:00:00+00:00", "first"), ("2026-10-20T11:00:00+00:00", "second")):
            conn.execute("""INSERT INTO activity_events (session_id, project_name, cwd, kind, text, ts)
                            VALUES ('s1', 'proj', '/tmp/proj', 'prompt', ?, ?)""", (text, ts))
    _ingest(tmp_path, "s1", [
        _row("msg_vrtx_0", ts="2026-10-20T09:30:00Z", out=1_000_000),
        _row("msg_vrtx_1", ts="2026-10-20T10:01:00Z", out=1_000_000),
        _row("msg_vrtx_2", ts="2026-10-20T10:59:00Z", out=1_000_000),
        _row("msg_vrtx_3", ts="2026-10-20T11:05:00Z", out=1_000_000),
    ])
    result = costs.session_usage("s1")
    assert result["calls"] == 4
    assert result["cost_usd"] == pytest.approx(80.0)
    assert [(t["prompt"], t["calls"]) for t in result["turns"]] == [(None, 1), ("first", 2), ("second", 1)]


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_heartbeat_records_known_auth_mode_only(client):
    client.post("/api/heartbeat", json={"session_id": "a", "cwd": "/tmp/p", "auth_mode": "vertex"})
    client.post("/api/heartbeat", json={"session_id": "b", "cwd": "/tmp/p", "auth_mode": "nonsense"})
    assert db.get_session("a")["auth_mode"] == "vertex"
    assert db.get_session("b")["auth_mode"] is None


def test_stop_ingests_usage_and_endpoints_report_it(client, tmp_path):
    client.post("/api/heartbeat", json={"session_id": "s1", "cwd": "/tmp/p", "auth_mode": "vertex"})
    path = tmp_path / "proj" / "s1.jsonl"
    _write(path, [_row("msg_vrtx_1", out=1_000_000)])
    client.post("/api/stop", json={"session_id": "s1", "transcript_path": str(path)})
    for _ in range(50):  # ingest runs as a background task
        if db.get_api_calls("s1"):
            break
        time.sleep(0.05)
    row = next(s for s in client.get("/api/sessions").json() if s["session_id"] == "s1")
    assert row["usage"]["billed_usd"] == pytest.approx(20.0)
    detail = client.get("/api/sessions/s1/usage").json()
    assert detail["calls"] == 1 and len(detail["turns"]) == 1

