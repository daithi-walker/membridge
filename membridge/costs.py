"""Price API calls from pricing.toml and roll them up per turn and session.

Cost is computed per call at ingest because the rate can vary per call (fast mode,
Haiku 5.5's long-prompt tier). After editing pricing.toml, restart the server and
re-run scripts/backfill_usage.py to reprice stored calls.

Every cost here is the list-price cost of the tokens. Whether it was actually billed
is a separate `billing` class (see db.BILLING_SQL): subscription sessions show an
API-equivalent figure, not spend.
"""
from __future__ import annotations

import bisect
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any

from . import db

PRICING: dict[str, Any] = tomllib.loads((Path(__file__).parent / "pricing.toml").read_text())

_RATE_KEYS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")


def price_call(call: db.ApiCall, pricing: dict[str, Any] = PRICING) -> float | None:
    """USD list-price cost of one call, or None if its model has no price."""
    model = pricing["models"].get(call["model"])
    if model is None:
        return None
    rates = {k: float(model[k]) for k in _RATE_KEYS}
    threshold = model.get("long_context_threshold")
    prompt = (call["input_tokens"] + call["cache_read_tokens"]
              + call["cache_write_5m_tokens"] + call["cache_write_1h_tokens"])
    if threshold and prompt > threshold:
        rates = {k: float(model["long_context"][k]) for k in _RATE_KEYS}
    if call["speed"] == "fast" and "fast_input" in model:
        # Caching multipliers stack on fast mode, so cache rates scale with input.
        factor = float(model["fast_input"]) / rates["input"]
        rates = {k: v * factor for k, v in rates.items()}
        rates["output"] = float(model["fast_output"])
    return (call["input_tokens"] * rates["input"]
            + call["output_tokens"] * rates["output"]
            + call["cache_read_tokens"] * rates["cache_read"]
            + call["cache_write_5m_tokens"] * rates["cache_write_5m"]
            + call["cache_write_1h_tokens"] * rates["cache_write_1h"]) / 1_000_000 \
        + call["web_search_requests"] * float(pricing["web_search_per_request"])


def _empty_totals() -> dict[str, Any]:
    return {
        "calls": 0, "cost_usd": 0.0, "billed_usd": 0.0, "unpriced_calls": 0,
        "by_billing": {}, "by_model": {},
        "tokens": {c: 0 for c in db.API_CALL_TOKEN_COLS},
    }


def _add(totals: dict[str, Any], call: dict) -> None:
    totals["calls"] += 1
    for col in db.API_CALL_TOKEN_COLS:
        totals["tokens"][col] += call[col]
    cost = call["cost_usd"]
    if cost is None:
        totals["unpriced_calls"] += 1
        return
    totals["cost_usd"] += cost
    if call["billing"] == "billed":
        totals["billed_usd"] += cost
    totals["by_billing"][call["billing"]] = totals["by_billing"].get(call["billing"], 0.0) + cost
    totals["by_model"][call["model"]] = totals["by_model"].get(call["model"], 0.0) + cost


def session_usage(session_id: str) -> dict[str, Any]:
    """Session totals plus a per-turn breakdown. A turn runs from one prompt event
    to the next; calls before the first recorded prompt (history that predates
    MemBridge tracking the session) land in a turn with `ts` None."""
    prompts = db.get_activity_events(session_id=session_id, kind="prompt")
    starts = [p["ts"] for p in prompts]
    totals = _empty_totals()
    turns: dict[int, dict[str, Any]] = {}
    for call in db.get_api_calls(session_id):
        _add(totals, call)
        idx = bisect.bisect_right(starts, call["ts"]) - 1
        turn = turns.setdefault(idx, {
            "ts": starts[idx] if idx >= 0 else None,
            "prompt": (prompts[idx]["text"] or "")[:200] if idx >= 0 else None,
            **_empty_totals(),
        })
        _add(turn, call)
    totals["turns"] = [turns[i] for i in sorted(turns)]
    return totals


# Claude Code writes the prompt cache with the default 5-minute TTL; a session idle
# longer than this rewrites its whole context on the next turn.
CACHE_TTL_SECS = 300


def context_meter(usage: dict, now: datetime, pricing: dict[str, Any] = PRICING) -> dict[str, Any]:
    """Current-context view of a get_usage_by_session row: idle time, whether the
    prompt cache is still warm, and what the next turn costs just to re-read the
    context (cache read if warm, full cache write if cold). Empty if the session
    has no main-thread call yet."""
    if usage.get("context_tokens") is None:
        return {}
    idle = (now - datetime.fromisoformat(usage["last_call_ts"])).total_seconds()
    rates = pricing["models"].get(usage["context_model"])
    ctx = usage["context_tokens"]
    return {
        "context_tokens": ctx,
        "idle_secs": idle,
        "cache_warm": idle < CACHE_TTL_SECS,
        "next_turn_warm_usd": ctx * float(rates["cache_read"]) / 1e6 if rates else None,
        "next_turn_cold_usd": ctx * float(rates["cache_write_5m"]) / 1e6 if rates else None,
    }
