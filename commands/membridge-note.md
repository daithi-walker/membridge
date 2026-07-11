---
allowed-tools:
  - Bash
argument-hint: "[--session <prefix>] <note text>"
description: "Inject a freeform note into a session's history in MemBridge"
---

Inject a freeform note verbatim into a session's history with `source: user`. No summarization.

- No `--session`: injects into the current session.
- `--session <prefix>`: injects into another session matched by ID prefix.

Arguments: $ARGUMENTS

```bash
SESSION_ID="$CLAUDE_CODE_SESSION_ID"
ARGS="$ARGUMENTS"
NOTE=""

# Parse optional --session <prefix>
if echo "$ARGS" | grep -qE "^--session [^ ]+"; then
  PREFIX=$(echo "$ARGS" | awk '{print $2}')
  NOTE=$(echo "$ARGS" | sed 's/^--session [^ ]* //')

  RESOLVE=$(curl -s "http://localhost:7842/api/sessions" | python3 -c "
import json, sys
prefix = sys.argv[1]
sessions = json.load(sys.stdin)
matches = [s for s in sessions if s['session_id'].startswith(prefix)]
if len(matches) == 0:
    print('NO_MATCH')
elif len(matches) > 1:
    print('AMBIGUOUS')
    for s in matches:
        desc = s.get('description') or ''
        print(f'  {s[\"session_id\"][:8]}  {s.get(\"project_name\",\"\")}  {desc[:40]}')
else:
    print(matches[0]['session_id'])
" "$PREFIX")

  case "$RESOLVE" in
    NO_MATCH)
      echo "No session found matching prefix: $PREFIX"
      exit 1
      ;;
    AMBIGUOUS)
      echo "Ambiguous prefix '$PREFIX' — multiple matches:"
      echo "$RESOLVE" | tail -n +2
      exit 1
      ;;
    *)
      SESSION_ID="$RESOLVE"
      ;;
  esac
else
  NOTE="$ARGS"
fi

if [ -z "$NOTE" ]; then
  echo "Usage: /membridge-note [--session <prefix>] <note text>"
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

After pushing, confirm with a single line: `Note added: <text>` (and the target session ID if `--session` was used).
