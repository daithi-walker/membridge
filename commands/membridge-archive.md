---
description: Toggle archive status for the current session in MemBridge
allowed-tools:
  - Bash
---

Archive (or unarchive) this session in the MemBridge dashboard so it stays out of the default view.

```bash
SESSION_ID="$CLAUDE_CODE_SESSION_ID"
if [ -z "$SESSION_ID" ]; then
  echo "Error: CLAUDE_CODE_SESSION_ID is not set" >&2
  exit 1
fi

# Check current archived state
RESPONSE=$(curl -s "http://localhost:7842/api/sessions/$SESSION_ID")
if [ $? -ne 0 ] || [ -z "$RESPONSE" ]; then
  echo "Error: Could not reach MemBridge at http://localhost:7842" >&2
  exit 1
fi

ARCHIVED=$(echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('archived', 0))" 2>/dev/null)
if [ "$ARCHIVED" = "1" ]; then
  NEW_STATE="false"
  ACTION="Unarchived"
else
  NEW_STATE="true"
  ACTION="Archived"
fi

curl -s -X PATCH "http://localhost:7842/api/sessions/$SESSION_ID" \
  -H "Content-Type: application/json" \
  -d "{\"archived\": $NEW_STATE}" > /dev/null

echo "$ACTION session $SESSION_ID"
```
