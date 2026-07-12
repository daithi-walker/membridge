#!/bin/bash
# Claude Code PostToolBatch hook — clears thinking indicator after a tool batch completes.
# Fires after all parallel tool calls in a batch resolve, before the next model call.

PAYLOAD=$(cat)
SESSION_ID=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)

[ -z "$SESSION_ID" ] && exit 0

BODY="{\"session_id\":\"$SESSION_ID\",\"thinking\":false}"
curl -s -X POST http://localhost:7842/api/touch \
  -H "Content-Type: application/json" \
  -d "$BODY" \
  --max-time 2 \
  >/dev/null 2>&1 || echo "[$(date -u +%FT%TZ)] tool_batch touch failed for $SESSION_ID" >> /tmp/membridge-hook.log &

exit 0
