#!/bin/bash
# Claude Code PreToolUse hook — keeps session last_seen fresh while Claude is working
# Fires before every tool call, so long-running responses don't slide into idle.
# Runs in background; never blocks Claude.

PAYLOAD=$(cat)
SESSION_ID=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)

[ -z "$SESSION_ID" ] && exit 0

BODY="{\"session_id\":\"$SESSION_ID\"}"

curl -s -X POST http://localhost:7842/api/touch \
  -H "Content-Type: application/json" \
  -d "$BODY" \
  --max-time 2 \
  >/dev/null 2>&1 &

exit 0
