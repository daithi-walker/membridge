#!/bin/bash
# Claude Code Notification hook — fires on permission_prompt and other notifications.
# Sets awaiting_input on the session and triggers a macOS notification.
# Runs in background; never blocks Claude.

set -euo pipefail

PAYLOAD=$(cat)
SESSION_ID=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
NOTIF_TYPE=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('notification_type',''))" 2>/dev/null)
MESSAGE=$(echo "$PAYLOAD"    | python3 -c "import sys,json; print(json.load(sys.stdin).get('message',''))" 2>/dev/null)

[ -z "$SESSION_ID" ] && exit 0

BODY=$(python3 -c "
import json, sys
print(json.dumps({
    'session_id':  sys.argv[1],
    'notif_type':  sys.argv[2],
    'message':     sys.argv[3],
}))" "$SESSION_ID" "${NOTIF_TYPE:-}" "${MESSAGE:-}" 2>/dev/null)

curl -s -X POST "${MEMBRIDGE_URL:-http://localhost:7842}/api/notification" \
  -H "Content-Type: application/json" \
  -d "$BODY" \
  --max-time 3 \
  >/dev/null 2>&1 &

exit 0
