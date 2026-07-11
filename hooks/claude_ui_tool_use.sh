#!/bin/bash
# Claude Code PreToolUse hook — keeps session last_seen fresh while Claude is working
# Fires before every tool call, so long-running responses don't slide into idle.
# Runs in background; never blocks Claude.

PAYLOAD=$(cat)
SESSION_ID=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
TOOL_NAME=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null)

[ -z "$SESSION_ID" ] && exit 0

if [ "$TOOL_NAME" = "AskUserQuestion" ]; then
  # Claude is presenting a choice — treat like awaiting input
  BODY=$(python3 -c "import json,sys; print(json.dumps({'session_id':sys.argv[1],'notif_type':'ask_user_question','message':''}))" "$SESSION_ID")
  curl -s -X POST http://localhost:7842/api/notification \
    -H "Content-Type: application/json" \
    -d "$BODY" \
    --max-time 2 \
    >/dev/null 2>&1 || echo "[$(date -u +%FT%TZ)] notification failed for $SESSION_ID" >> /tmp/membridge-hook.log &
else
  BODY="{\"session_id\":\"$SESSION_ID\"}"
  curl -s -X POST http://localhost:7842/api/touch \
    -H "Content-Type: application/json" \
    -d "$BODY" \
    --max-time 2 \
    >/dev/null 2>&1 || echo "[$(date -u +%FT%TZ)] touch failed for $SESSION_ID" >> /tmp/membridge-hook.log &
fi

exit 0
