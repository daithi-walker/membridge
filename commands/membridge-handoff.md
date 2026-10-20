---
description: Write a handoff summary to MemBridge so you can /clear and continue in a small fresh context
allowed-tools: Bash
---

Hand this session off to a fresh context. A long session re-reads its whole history on
every turn (and rewrites all of it after 5 minutes idle); a cleared session that loads
a few-thousand-token handoff does the same work far more cheaply.

**Instructions:**

1. Write a handoff for a fresh Claude with no memory of this conversation. Unlike
   `/membridge-summarize` (a progress log), it must be enough to continue the work
   without re-reading anything. Use this structure, and be specific (paths, function
   names, commands, IDs, numbers):

```
## Goal
<what we're trying to achieve and why>

## Current state
<what's done and verified, what's in progress, what's broken>

## Key decisions and constraints
<choices made and the reasons, user preferences stated, things ruled out>

## Where things are
<files, branches, worktrees, endpoints, tickets, data locations>

## Next steps
- <specific actionable item, in order>
```

2. Write it to a temp file and POST it with source `handoff`:

```bash
SESSION_ID="$CLAUDE_CODE_SESSION_ID"
TMPFILE=$(mktemp /tmp/mb-handoff-XXXXXX.md)
cat > "$TMPFILE" << 'HANDOFF_EOF'
<your handoff here>
HANDOFF_EOF
python3 -c "
import json, sys
print(json.dumps({'source': 'handoff', 'text': open(sys.argv[1]).read()}))
" "$TMPFILE" | curl -s -X POST "${MEMBRIDGE_URL:-http://localhost:7842}/api/sessions/$SESSION_ID/push-summary" \
  -H "Content-Type: application/json" \
  --data-binary @-
rm -f "$TMPFILE"
```

3. If the response is `{"ok":true,...}`, tell the user exactly this (with the real
   8-character prefix of `$CLAUDE_CODE_SESSION_ID`):

> Handoff saved. Run `/clear`, then `/membridge-context <prefix>` to continue from it.

Only the user can run `/clear`; don't attempt it.
