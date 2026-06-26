---
allowed-tools:
  - Bash
argument-hint: "<session-id-prefix>"
description: "Link the current session to another session in MemBridge"
---

Link this session to another MemBridge session. Useful for tying related work together so both sessions surface in each other's panel and context output.

- **With a session ID prefix** — links current session to the matching session.
- **No argument** — lists sessions currently linked to this session.

The argument is: $ARGUMENTS

```bash
SESSION_ID="$CLAUDE_CODE_SESSION_ID"
SESSION_ARG="$ARGUMENTS"
BASE_URL="http://localhost:7842"

if [ -z "$SESSION_ARG" ]; then
  # List current links
  curl -s "$BASE_URL/api/sessions/$SESSION_ID/links" | python3 -c "
import json, sys
links = json.load(sys.stdin)
if not links:
    print('No linked sessions.')
else:
    print('Linked sessions:')
    for l in links:
        branch = f\" · {l['git_branch']}\" if l.get('git_branch') else ''
        desc = (l.get('description') or '').strip('[] \n').split('\n')[0][:80]
        suffix = f' — {desc}' if desc else ''
        print(f\"  {l['session_id'][:8]}  {l['project_name']}{branch}{suffix}\")
"
  exit 0
fi

# Resolve prefix to full session ID
TARGET=$(curl -s "$BASE_URL/api/sessions" | python3 -c "
import sys, json
sessions = json.load(sys.stdin)
arg = '$SESSION_ARG'
matches = [s for s in sessions if s['session_id'].startswith(arg)]
if len(matches) == 1:
    print(matches[0]['session_id'])
elif len(matches) == 0:
    print('NO_MATCH', end='')
else:
    print('AMBIGUOUS', end='')
" 2>/dev/null)

if [ "$TARGET" = "NO_MATCH" ]; then
  echo "No session found matching: $SESSION_ARG"
  exit 1
fi

if [ "$TARGET" = "AMBIGUOUS" ]; then
  echo "Ambiguous prefix '$SESSION_ARG' — be more specific"
  exit 1
fi

BODY=$(python3 -c "import json,sys; print(json.dumps({'target_id': sys.argv[1]}))" "$TARGET")

curl -s -X POST "$BASE_URL/api/sessions/$SESSION_ID/links" \
  -H "Content-Type: application/json" \
  -d "$BODY" | python3 -c "
import json, sys
r = json.load(sys.stdin)
if r.get('ok'):
    status = r.get('status', '')
    if status == 'already_linked':
        print('Already linked to $SESSION_ARG')
    else:
        print('Linked to $SESSION_ARG ($TARGET[:8]...)')
else:
    print('Error:', r)
"
```

After linking, confirm with one line naming both sessions. If listing links, summarise what each linked session is working on based on its description.
