Fetch this session's context from MemBridge and use it as working context for this conversation.

**Instructions:**

Run the following in a Bash block:

```bash
if [ -z "$CLAUDE_CODE_SESSION_ID" ]; then
  echo "No CLAUDE_CODE_SESSION_ID — cannot fetch context"
  exit 0
fi

RESULT=$(curl -sf "http://localhost:7842/api/sessions/$CLAUDE_CODE_SESSION_ID" 2>/dev/null)
if [ -z "$RESULT" ]; then
  echo "MemBridge not running or session not found (http://localhost:7842)"
  exit 0
fi

python3 - <<'PYEOF'
import json, sys, os

data = json.loads(os.popen('curl -sf "http://localhost:7842/api/sessions/$CLAUDE_CODE_SESSION_ID"').read())
print("## MemBridge Session Context\n")
tickets = data.get("tickets") or ""
if tickets:
    refs = ", ".join(f"#{t.strip()}" for t in tickets.split(",") if t.strip())
    print(f"Tickets:     {refs}")
print(f"Project:     {data.get('project_name', '—')}")
print(f"Branch:      {data.get('git_branch', '—')}")
print(f"Directory:   {data.get('cwd', '—')}")
print(f"Status:      {data.get('status', '—')}")
desc = (data.get("description") or "").strip()
if desc:
    print(f"Description: {desc}")
notes = (data.get("notes") or "").strip()
if notes:
    print(f"\nNotes:\n{notes}")
PYEOF
```

After running, acknowledge the context and confirm what tickets and notes you've loaded (if any). If tickets are set, mention them by number so the user can confirm you've picked them up correctly.
