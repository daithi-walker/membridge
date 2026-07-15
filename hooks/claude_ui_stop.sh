#!/bin/bash
# Claude Code Stop hook — records stop reason and triggers auto-summary
# Runs in background; never blocks Claude.

set -euo pipefail

PAYLOAD=$(cat)
SESSION_ID=$(echo "$PAYLOAD"     | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
STOP_REASON=$(echo "$PAYLOAD"   | python3 -c "import sys,json; print(json.load(sys.stdin).get('stop_reason',''))" 2>/dev/null)
TRANSCRIPT=$(echo "$PAYLOAD"    | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)

[ -z "$SESSION_ID" ] && exit 0

BODY=$(python3 -c "
import json, sys
print(json.dumps({
    'session_id':      sys.argv[1],
    'stop_reason':     sys.argv[2],
    'transcript_path': sys.argv[3],
}))" "$SESSION_ID" "${STOP_REASON:-}" "${TRANSCRIPT:-}" 2>/dev/null)

curl -s -X POST "${MEMBRIDGE_URL:-http://localhost:7842}/api/stop" \
  -H "Content-Type: application/json" \
  -d "$BODY" \
  --max-time 3 \
  >/dev/null 2>&1 || echo "[$(date -u +%FT%TZ)] stop failed for $SESSION_ID" >> /tmp/membridge-hook.log &

exit 0
