#!/bin/bash
# Claude Code UserPromptSubmit hook — registers session heartbeat with membridge
# Runs in background; never blocks Claude.

set -euo pipefail

PAYLOAD=$(cat)
SESSION_ID=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
CWD=$(echo "$PAYLOAD"       | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null)

[ -z "$SESSION_ID" ] && exit 0
[ -z "$CWD" ]        && exit 0

BRANCH=$(git -C "$CWD" branch --show-current 2>/dev/null || true)

# Parent PID = the Claude process that fired this hook
CLAUDE_PID=$PPID

# Best-effort iTerm2 session name — silently skipped if not running in iTerm2
ITERM_TAB=$(osascript -e \
  'tell application "iTerm2" to tell current window to tell current tab to tell current session to return name' \
  2>/dev/null || true)

# $ITERM_SESSION_ID format: w<n>t<n>p<n>:<UUID> — extract the UUID after the colon
ITERM_UUID=""
if [ -n "${ITERM_SESSION_ID:-}" ]; then
  ITERM_UUID=$(echo "$ITERM_SESSION_ID" | cut -d: -f2)
fi

BODY=$(python3 -c "
import json, sys
print(json.dumps({
    'session_id':          sys.argv[1],
    'cwd':                 sys.argv[2],
    'branch':              sys.argv[3],
    'iterm_tab':           sys.argv[4],
    'pid':                 int(sys.argv[5]) if sys.argv[5] else None,
    'iterm_session_uuid':  sys.argv[6] or None,
}))" "$SESSION_ID" "$CWD" "${BRANCH:-}" "${ITERM_TAB:-}" "${CLAUDE_PID:-}" "${ITERM_UUID:-}" 2>/dev/null)

curl -s -X POST http://localhost:7842/api/heartbeat \
  -H "Content-Type: application/json" \
  -d "$BODY" \
  --max-time 3 \
  >/dev/null 2>&1 &

exit 0
