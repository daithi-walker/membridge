---
description: Summarize this Claude Code session and push to MemBridge
allowed-tools: Write, Bash
---

Generate a concise summary of this session and write it to MemBridge so it appears in the dashboard.

**Instructions:**

1. Review the conversation so far — what was the goal, what was built or investigated, where did we get to, and what remains.

2. Write a summary file to `~/.membridge/summaries/$CLAUDE_CODE_SESSION_ID/` using today's date and time as the filename (format: `YYYY-MM-DD-HHMM.md`). Get the current datetime with Bash.

3. The file must follow this exact structure:

```
## Summary
<2–3 sentences: what the session worked on and why>

## Where we got to
<current state — what's done, what's in progress, any blockers>

## Next steps
- <specific actionable item>
- <specific actionable item>
- ...
```

4. Be specific — name files, functions, features, bugs, endpoints, or decisions. Avoid vague statements like "worked on the codebase".

5. After writing the file, confirm with the path written and a one-line recap of the summary.

**Notes:**
- MemBridge polls for new files every 30 seconds — the summary will appear in the dashboard automatically
- The session ID is available as `$CLAUDE_CODE_SESSION_ID` in Bash
- Do not call any MemBridge API directly — just write the file
