---
description: Load context for this session (or any session by ID prefix) from MemBridge
allowed-tools:
  - Bash
argument-hint: "[session-id-prefix]"
---

Fetch session context from MemBridge and use it as working context for this conversation.

- **No argument** — loads this session's own metadata: tickets, notes, description, branch.
- **With a session ID prefix** — loads that session's metadata plus full summary history. Use this to pull context from a different session into the current conversation.

```bash
SESSION_ARG="${1:-}"
BASE_URL="http://localhost:7842"

if [ -z "$SESSION_ARG" ]; then
  # Self-lookup: use this session's ID
  if [ -z "$CLAUDE_CODE_SESSION_ID" ]; then
    echo "No CLAUDE_CODE_SESSION_ID — cannot fetch context"
    exit 0
  fi
  TARGET="$CLAUDE_CODE_SESSION_ID"
else
  # Find session matching the prefix
  TARGET=$(curl -s "$BASE_URL/api/sessions" | python3 -c "
import sys, json
sessions = json.load(sys.stdin)
arg = '$SESSION_ARG'
for s in sessions:
    if s['session_id'].startswith(arg):
        print(s['session_id'])
        break
" 2>/dev/null)
  if [ -z "$TARGET" ]; then
    echo "No session found matching: $SESSION_ARG"
    exit 1
  fi
fi

SESSION_DATA=$(curl -sf "$BASE_URL/api/sessions/$TARGET" 2>/dev/null)
if [ -z "$SESSION_DATA" ]; then
  echo "MemBridge not running or session not found ($BASE_URL)"
  exit 0
fi

python3 - "$TARGET" "$SESSION_ARG" <<'PYEOF'
import json, sys, os, urllib.request

target = sys.argv[1]
is_other = sys.argv[2] != ""
base = "http://localhost:7842"

data = json.loads(urllib.request.urlopen(f"{base}/api/sessions/{target}").read())

print("## MemBridge Session Context\n")
if is_other:
    print(f"Session:     {data['session_id']}")
tickets = data.get("tickets") or ""
if tickets:
    refs = ", ".join(f"#{t.strip()}" for t in tickets.split(",") if t.strip())
    print(f"Tickets:     {refs}")
print(f"Project:     {data.get('project_name', '—')}")
print(f"Branch:      {data.get('git_branch', '—')}")
print(f"Directory:   {data.get('cwd', '—')}")
desc = (data.get("description") or "").strip()
if desc:
    print(f"Description: {desc}")
notes = (data.get("notes") or "").strip()
if notes:
    print(f"\nNotes:\n{notes}")

# For cross-session lookups, also show summary history
if is_other:
    entries = json.loads(urllib.request.urlopen(f"{base}/api/sessions/{target}/summaries").read())
    if entries:
        print("\n## Summary history")
        for e in reversed(entries):
            print(f"\n--- [{e['source']}] {e['created_at'][:16]} ---")
            print(e['text'])
PYEOF
```

After running, acknowledge the context. If tickets are set, call them out by number. If this is a cross-session lookup, summarise what that session was working on.
