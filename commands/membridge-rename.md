---
allowed-tools:
  - Bash
argument-hint: "<description>"
description: "Rename (set description for) the current session in MemBridge"
---

Set the description for the current MemBridge session. Use this at the start of a session to label what you're working on, or at any point to update it.

The description is: $ARGUMENTS

```bash
SESSION_ID="$CLAUDE_CODE_SESSION_ID"
DESC="$ARGUMENTS"

if [ -z "$DESC" ]; then
  echo "Usage: /membridge-rename <description>"
  exit 1
fi

BODY=$(python3 -c "import json,sys; print(json.dumps({'description': sys.argv[1]}))" "$DESC")

RESULT=$(curl -s -X PATCH "http://localhost:7842/api/sessions/$SESSION_ID" \
  -H "Content-Type: application/json" \
  -d "$BODY")

echo "$RESULT" | python3 -c "
import json, sys
r = json.load(sys.stdin)
if r.get('ok'):
    print('Renamed session: $DESC')
else:
    print('Error:', r)
"
```

After renaming, confirm with a single line: `Renamed: <description>`.
