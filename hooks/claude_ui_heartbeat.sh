#!/bin/bash
# Claude Code UserPromptSubmit hook — registers session heartbeat with claude-ui
# Runs in background; never blocks Claude.

set -euo pipefail

PAYLOAD=$(cat)
SESSION_ID=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
CWD=$(echo "$PAYLOAD"       | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null)

[ -z "$SESSION_ID" ] && exit 0
[ -z "$CWD" ]        && exit 0

BRANCH=$(git -C "$CWD" branch --show-current 2>/dev/null || true)

# Best-effort iTerm2 tab name — silently skipped if not running
ITERM_TAB=$(osascript -e \
  'tell application "iTerm2" to get name of current tab of current window' \
  2>/dev/null || true)

# Escape values for JSON
json_escape() { python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" <<< "$1"; }

BODY=$(python3 -c "
import json, sys
print(json.dumps({
    'session_id': sys.argv[1],
    'cwd':        sys.argv[2],
    'branch':     sys.argv[3],
    'iterm_tab':  sys.argv[4],
}))" "$SESSION_ID" "$CWD" "${BRANCH:-}" "${ITERM_TAB:-}" 2>/dev/null)

curl -s -X POST http://localhost:7842/api/heartbeat \
  -H "Content-Type: application/json" \
  -d "$BODY" \
  --max-time 3 \
  >/dev/null 2>&1 &

exit 0
