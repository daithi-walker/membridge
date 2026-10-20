#!/usr/bin/env python3
"""Claude Code status line: model, current context size, prompt-cache warmth, cost.

Reads the JSON Claude Code passes on stdin (https://code.claude.com/docs/en/statusline)
and prints one line, e.g.  Opus 5.5 · ctx 312k (31%) · cache warm · $7.26

Context is coloured amber over 200k and red over 500k tokens: every turn re-reads the
whole context, and once the cache goes cold (5 min idle by default) the next turn
rewrites all of it. That's the cue to /compact (or hand off) at a stopping point.
Needs no MemBridge connection, so it never waits on the server.
"""
import json
import sys

AMBER, RED, DIM, RESET = "\033[33m", "\033[31m", "\033[2m", "\033[0m"


def fmt_tokens(n: int) -> str:
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else str(n)


def main() -> None:
    data = json.load(sys.stdin)
    parts = [(data.get("model") or {}).get("display_name") or ""]

    window = data.get("context_window") or {}
    usage = window.get("current_usage") or {}
    ctx = sum(usage.get(k) or 0 for k in
              ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    if ctx:
        colour = RED if ctx > 500_000 else AMBER if ctx > 200_000 else ""
        pct = window.get("used_percentage")
        pct_txt = f" ({pct:.0f}%)" if isinstance(pct, (int, float)) else ""
        parts.append(f"{colour}ctx {fmt_tokens(ctx)}{pct_txt}{RESET if colour else ''}")

    cache = data.get("prompt_cache") or {}
    if "warm" in cache:
        parts.append("cache warm" if cache["warm"] else f"{DIM}cache cold{RESET}")

    cost = (data.get("cost") or {}).get("total_cost_usd")
    if isinstance(cost, (int, float)):
        parts.append(f"${cost:.2f}")

    print(" · ".join(p for p in parts if p))


if __name__ == "__main__":
    main()
