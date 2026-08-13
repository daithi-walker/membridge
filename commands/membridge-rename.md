---
allowed-tools:
  - Bash
argument-hint: "[description]"
description: "Rename (set description for) the current session in MemBridge"
---

Set the description for the current MemBridge session. Use this at the start of a session to label what you're working on, or at any point to update it.

**Arguments:** $ARGUMENTS

## Steps

1. If `$ARGUMENTS` is non-empty, use it verbatim as the description.
2. If `$ARGUMENTS` is empty, write your own description by summarizing what this session has actually done or is currently doing, based on the conversation so far. Be specific and concrete (e.g. "Ported /slides command to private GitHub repo for cross-laptop sync"), not generic ("Updated session" or "Working on task"). Keep it under ~12 words.
3. Run the following, substituting the description from step 1 or 2 in place of `<description>`:

```bash
SESSION_ID="$CLAUDE_CODE_SESSION_ID"
DESC="<description>"

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

4. Confirm with a single line: `Renamed: <description>`.
