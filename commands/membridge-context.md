---
description: Load context for this session, another session by ID prefix, or search all sessions
allowed-tools:
  - Bash
argument-hint: "[session-id-prefix | search terms]"
---

Fetch session context from MemBridge and use it as working context for this conversation.

- **No argument** — loads this session's own metadata: tickets, notes, description, branch.
- **With a session ID prefix** — loads that session's metadata plus full summary history. Use this to pull context from a different session into the current conversation.
- **With search terms** (anything that isn't a session ID prefix) — full-text search across every session's summaries, descriptions, and notes; lists the best-matching sessions with the matched snippet.

```bash
SESSION_ARG="$ARGUMENTS"
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
arg = sys.argv[1]
for s in sessions:
    if s['session_id'].startswith(arg):
        print(s['session_id'])
        break
" "$SESSION_ARG" 2>/dev/null)
  if [ -z "$TARGET" ]; then
    # Not an ID prefix: treat the argument as a search query
    python3 - "$SESSION_ARG" <<'PYEOF'
import json, sys, urllib.error, urllib.parse, urllib.request

q = sys.argv[1]
url = "http://localhost:7842/api/search?" + urllib.parse.urlencode({"q": q, "limit": 10})
try:
    hits = json.loads(urllib.request.urlopen(url).read())
except urllib.error.URLError as e:
    print(f"MemBridge search failed: {e}")
    sys.exit(0)
if not hits:
    print(f"No session or search match for: {q}")
    sys.exit(0)
print(f"## MemBridge search: {q}\n")
for h in hits:
    branch = f" · {h['git_branch']}" if h.get("git_branch") else ""
    snippet = " ".join(h["snippet"].replace("\x02", "**").replace("\x03", "**").split())
    print(f"- {h['session_id'][:8]} [{h['project_name']}{branch}] {h['last_seen'][:10]}"
          f" ({h['hits']} match{'es' if h['hits'] != 1 else ''}, best in {h['kind']})")
    print(f"    {snippet}")
print("\nRun /membridge-context <id-prefix> to load a session's full history.")
PYEOF
    exit 0
  fi
fi

ALL_SESSIONS=$(curl -sf "$BASE_URL/api/sessions" 2>/dev/null)
if [ -z "$ALL_SESSIONS" ]; then
  echo "MemBridge not running or session not found ($BASE_URL)"
  exit 0
fi

python3 - "$TARGET" "$SESSION_ARG" <<'PYEOF'
import json, sys, os, urllib.request

target = sys.argv[1]
is_other = sys.argv[2] != ""
base = "http://localhost:7842"

all_sessions = json.loads(urllib.request.urlopen(f"{base}/api/sessions").read())
data = next((s for s in all_sessions if s["session_id"] == target), None)
if not data:
    print(f"Session {target} not found in MemBridge")
    sys.exit(0)

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

# Linked sessions — always shown if any exist
try:
    links = json.loads(urllib.request.urlopen(f"{base}/api/sessions/{target}/links").read())
    if links:
        print("\n## Linked sessions")
        for l in links:
            short = l['session_id'][:8]
            branch = f" · {l['git_branch']}" if l.get('git_branch') else ""
            desc = l.get('description') or ""
            desc_short = desc.strip("[] \n").split("\n")[0][:80] if desc else ""
            suffix = f" — {desc_short}" if desc_short else ""
            print(f"- [{l['project_name']}{branch}] {short}{suffix}")
except Exception:
    pass
PYEOF
```

After running, acknowledge the context. If tickets are set, call them out by number. If this is a cross-session lookup, summarise what that session was working on. If it was a search, summarise what the matching sessions cover and offer to load the most relevant one.
