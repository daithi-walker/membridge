---
description: Fetch summaries for a specific MemBridge session to recall context from another session
allowed-tools:
  - Bash
argument-hint: "[session-id-prefix]"
---

Retrieve the summary history for a MemBridge session — useful for recalling what another session worked on without switching to it.

If a session ID (or prefix) is provided, fetch that session's summaries directly. If no argument is given, list all recent sessions so you can pick one.

```bash
SESSION_ARG="$1"

if [ -z "$SESSION_ARG" ]; then
  echo "=== Recent MemBridge sessions ===" 
  curl -s "http://localhost:7842/api/sessions" | python3 -c "
import sys, json
sessions = json.load(sys.stdin)
for s in sessions[:20]:
    desc = s.get('description') or ''
    desc = desc[:60] + '...' if len(desc) > 60 else desc
    print(f\"{s['session_id'][:12]}  {s['project_name']:<20}  {s.get('git_branch',''):<20}  {desc}\")
"
  echo ""
  echo "Run: /membridge-recall <session-id-prefix>"
else
  # Find matching session
  MATCH=$(curl -s "http://localhost:7842/api/sessions" | python3 -c "
import sys, json
sessions = json.load(sys.stdin)
arg = '$SESSION_ARG'
for s in sessions:
    if s['session_id'].startswith(arg):
        print(s['session_id'])
        break
" 2>/dev/null)

  if [ -z "$MATCH" ]; then
    echo "No session found matching: $SESSION_ARG" >&2
    exit 1
  fi

  # Fetch session metadata
  SESSION_DATA=$(curl -s "http://localhost:7842/api/sessions/$MATCH")
  PROJECT=$(echo "$SESSION_DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('project_name',''))")
  BRANCH=$(echo "$SESSION_DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('git_branch',''))")
  DESC=$(echo "$SESSION_DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description',''))")
  LAST=$(echo "$SESSION_DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('last_seen',''))")

  echo "=== Session: $MATCH ==="
  echo "Project:     $PROJECT"
  echo "Branch:      $BRANCH"
  echo "Last active: $LAST"
  echo "Description: $DESC"
  echo ""
  echo "=== Summary history ==="

  curl -s "http://localhost:7842/api/sessions/$MATCH/summaries" | python3 -c "
import sys, json
entries = json.load(sys.stdin)
if not entries:
    print('No summaries recorded for this session.')
else:
    for e in reversed(entries):
        print(f\"--- [{e['source']}] {e['created_at'][:16]} ---\")
        print(e['text'])
        print()
"
fi
```
