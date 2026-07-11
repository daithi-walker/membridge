# ADR 003: Delta-Aware /membridge-summarize Command

**Date:** 2026-06-23  
**Status:** Accepted

## Context

The `/membridge-summarize` slash command writes a structured summary file to `~/.membridge/summaries/<session-id>/`, which the server polls every 30 seconds and ingests as a `skill` source entry.

When run multiple times in a long session, the original implementation summarized the full conversation each time, resulting in near-duplicate history entries that added noise without new information.

## Decision

Before generating the summary, the command fetches existing summaries for the session:

```bash
curl -s "http://localhost:7842/api/sessions/$SESSION_ID/summaries"
```

The model is then instructed:

- **If prior summaries exist**: only cover what happened *since the most recent entry* — treat it as a delta/update
- **If no prior summaries exist**: summarize the full session

The file format is unchanged:

```
## Summary
## Where we got to
## Next steps
```

## Alternatives considered

**Summarize from last known timestamp** — would require the command to parse `created_at` from the JSON response and filter the conversation. More brittle than letting the model reason about "what's new".

**Single summary per session, always overwrite** — loses the audit trail, which is a core value of the history log.

**No delta awareness** — original approach; produces duplicate content and pollutes the history view.

## Consequences

- Running `/membridge-summarize` mid-session produces a focused update rather than a repeat of prior summaries
- The model must read the prior summary content to determine what's new — adds a small amount of context usage on each invocation
- Very long sessions with many prior summaries could result in the context being dominated by history; acceptable for now given the 30-day scope of typical sessions
