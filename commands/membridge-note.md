---
allowed-tools:
  - Bash
argument-hint: "<note text>"
description: "Inject a freeform note into the current session's history in MemBridge"
---

Inject a freeform note into this session's history without summarization. The note is stored verbatim with `source: user`.

The note is: $ARGUMENTS

```bash
SESSION_ID="$CLAUDE_CODE_SESSION_ID"
NOTE="$ARGUMENTS"

if [ -z "$NOTE" ]; then
  echo "Usage: /membridge-note <text>"
  exit 1
fi

BODY=$(python3 -c "import json,sys; print(json.dumps({'source': 'user', 'text': sys.argv[1]}))" "$NOTE")

RESULT=$(curl -s -X POST "http://localhost:7842/api/sessions/$SESSION_ID/push-summary" \
  -H "Content-Type: application/json" \
  -d "$BODY")

echo "$RESULT" | python3 -c "
import json, sys
r = json.load(sys.stdin)
if r.get('ok'):
    status = r.get('status', '')
    if status == 'unchanged':
        print('Note unchanged (identical text already in history)')
    else:
        print('Note added to session history')
else:
    print('Error:', r)
"
```

After pushing, confirm with a single line: `Note added: <text>`.
