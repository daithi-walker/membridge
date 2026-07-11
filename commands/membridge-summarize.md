---
description: Summarize this Claude Code session and push to MemBridge
allowed-tools: Bash
---

Generate a concise summary of this session and push it directly to MemBridge.

**Instructions:**

1. First, fetch any existing summaries to determine what's already been recorded:

```bash
SESSION_ID="$CLAUDE_CODE_SESSION_ID"
curl -s "http://localhost:7842/api/sessions/$SESSION_ID/summaries" 2>/dev/null || echo "[]"
```

2. Review the conversation so far. If previous summaries exist, **only cover what happened since the most recent one** — treat it as a delta/update. If no summaries exist, summarize the full session.

3. Write the summary to a temp file then POST it. This preserves real newlines:

```bash
SESSION_ID="$CLAUDE_CODE_SESSION_ID"
TMPFILE=$(mktemp /tmp/mb-summary-XXXXXX.md)
cat > "$TMPFILE" << 'SUMMARY_EOF'
<your full summary content here>
SUMMARY_EOF
python3 -c "
import json, sys
text = open(sys.argv[1]).read()
print(json.dumps({'source': 'skill', 'text': text}))
" "$TMPFILE" | curl -s -X POST "http://localhost:7842/api/sessions/$SESSION_ID/push-summary" \
  -H "Content-Type: application/json" \
  --data-binary @-
rm -f "$TMPFILE"
```

4. The summary must follow this structure:

```
## Summary
<2–3 sentences: what the session worked on and why — delta only if prior summaries exist>

## Where we got to
<current state — what's done, what's in progress, any blockers>

## Next steps
- <specific actionable item>
- <specific actionable item>
- ...
```

5. Be specific — name files, functions, features, bugs, endpoints, or decisions. Avoid vague statements like "worked on the codebase".

6. After the curl succeeds, confirm with a one-line recap. The response `{"ok":true,"status":"added"}` means it landed immediately in the DB. `{"ok":true,"status":"unchanged"}` means the text matched the last entry and was skipped.

**Notes:**
- No file is written to disk — the summary goes straight to the DB via HTTP POST
- `$CLAUDE_CODE_SESSION_ID` is the correct env var for the session ID
- If a prior summary exists, the new entry is a delta — don't repeat what was already captured
- The server deduplicates by text — same content won't create a duplicate entry
