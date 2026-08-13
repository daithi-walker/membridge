---
description: Report real engaged-work time (from MemBridge's prompt/stop activity events) for a client, merged across overlapping sessions
allowed-tools:
  - Bash
argument-hint: "[client-or-path] [from-date] [to-date] [idle-minutes]"
---

Run MemBridge's activity report — the most reliable "was I actually here" signal for reconstructing billable hours, since it's driven by real prompt submissions and Claude's own turn-completion events rather than git commit timestamps (which can land from unattended/autonomous work).

Pairs each prompt with the next `stop` in the same session into an "active" interval, then merges active intervals across every session open for that client into one timeline — so having 2-3 sessions open for the same client at once doesn't create a false gap just because one of them was idle while another was active. A gap in the merged timeline under `--idle-minutes` counts as engaged (reading/thinking); longer gaps are flagged and excluded from the billable estimate, but still shown for a sanity check against memory.

- **No arguments** — reports ALL recorded activity, auto-grouped by client (top-level directory under `~/git/`).
- **`$1` given** — scopes to one client/project. A bare name (e.g. `client-a`, `client-b`) is expanded to `~/git/$1` and matched against any subdirectory (so `~/git/client-a/knowledge`, `~/git/client-a/internal-repo`, etc. all roll up). A value containing `/` is used as an explicit path prefix instead.
- **`$2`/`$3`** — optional `--from`/`--to` date range (`YYYY-MM-DD`, local time, inclusive).
- **`$4`** — optional idle-minutes threshold: gaps up to this long count as still-engaged reading/thinking time (default 15).

```bash
CLIENT_ARG="${1:-}"
FROM_ARG="${2:-}"
TO_ARG="${3:-}"
IDLE_ARG="${4:-}"

cd "$HOME/git/membridge"

ARGS=()
if [ -n "$CLIENT_ARG" ]; then
  case "$CLIENT_ARG" in
    */*) ARGS+=(--path-prefix "$CLIENT_ARG") ;;
    *)   ARGS+=(--path-prefix "$HOME/git/$CLIENT_ARG") ;;
  esac
fi
[ -n "$FROM_ARG" ] && ARGS+=(--from "$FROM_ARG")
[ -n "$TO_ARG" ]   && ARGS+=(--to "$TO_ARG")
[ -n "$IDLE_ARG" ] && ARGS+=(--idle-minutes "$IDLE_ARG")

uv run python scripts/heartbeat_report.py "${ARGS[@]}"
```

Summarise the output for the user: active hours per block/client, flagged gaps worth checking against memory, and the overall billable estimate. Note this data only covers activity from 2026-08-13 onward.
