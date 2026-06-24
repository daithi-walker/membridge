---
allowed-tools:
  - Bash
argument-hint: "<tag text>"
description: "Tag the current session with a short description"
---

Set a description tag on the current MemBridge session. Use this at the start of a session to label what you're working on, or at any point to update it.

The tag argument is: $ARGUMENTS

Run this to set it:

```bash
SESSION_ID="$CLAUDE_CODE_SESSION_ID"
TAG="$ARGUMENTS"

if [ -z "$TAG" ]; then
  echo "Usage: /membridge-tag <description>"
  exit 1
fi

BODY=$(python3 -c "import json,sys; print(json.dumps({'description': sys.argv[1]}))" "$TAG")

RESULT=$(curl -s -X PATCH "http://localhost:7842/api/sessions/$SESSION_ID" \
  -H "Content-Type: application/json" \
  -d "$BODY")

echo "$RESULT" | python3 -c "
import json, sys
r = json.load(sys.stdin)
if r.get('ok'):
    print('Tagged session: $TAG')
else:
    print('Error:', r)
"
```

After tagging, confirm with a single line: `Tagged: <tag text>`.
