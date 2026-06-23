---
description: Summarize this Claude Code session and push to MemBridge
allowed-tools: Bash
---

Generate a concise summary of this session and write it to MemBridge so it appears in the dashboard.

**Instructions:**

1. First, fetch any existing summaries for this session to determine what's already been recorded:

```bash
SESSION_ID="$CLAUDE_CODE_SESSION_ID"
curl -s "http://localhost:7842/api/sessions/$SESSION_ID/summaries" 2>/dev/null || echo "[]"
```

2. Review the conversation so far. If previous summaries exist, **only cover what happened since the most recent one** — treat it as a delta/update. If no summaries exist, summarize the full session.

3. Use Bash to write the file. Get the session ID and timestamp dynamically:

```bash
SESSION_ID="$CLAUDE_CODE_SESSION_ID"
TIMESTAMP=$(date +%Y-%m-%d-%H%M)
DIR="$HOME/.membridge/summaries/$SESSION_ID"
mkdir -p "$DIR"
cat > "$DIR/$TIMESTAMP.md" << 'SUMMARY_EOF'
<your summary content here>
SUMMARY_EOF
echo "Written: $DIR/$TIMESTAMP.md"
```

4. The file content must follow this exact structure:

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

6. After writing, confirm with the path and a one-line recap.

**Notes:**
- MemBridge polls for new files every 30 seconds — the summary will appear automatically
- `$CLAUDE_CODE_SESSION_ID` is the correct env var for the session ID
- Write the entire file in a single Bash heredoc — do not use the Write tool
- If a prior summary exists, the new entry is a delta — don't repeat what was already captured
