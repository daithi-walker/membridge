# ADR 001 — Session Summarization Strategy

**Status:** Accepted (current approach) — decision point open  
**Date:** 2026-06-23

---

## Context

MemBridge needs a per-session summary to display in the dashboard and help users recall what each Claude Code session was working on. Sessions can be long-lived (hours, many compaction cycles), span multiple days, and end abruptly. We also want to capture "next steps" so work can be resumed without re-reading the full transcript.

Three components interact here:

1. **The source of truth** — Claude's JSONL transcript (`~/.claude/projects/.../<session_id>.jsonl`)
2. **The summarizer** — whatever reads that source and produces human-readable text
3. **The consumer** — MemBridge dashboard, and potentially other tools

### Constraints

- Claude Code sessions can hit compaction mid-session; the raw JSONL reflects pre-compaction turns but the live context is the post-compaction view
- The JSONL format is Claude Code's internal format — MemBridge should not take a hard dependency on it staying stable
- Summarization must work for historical sessions (stopped hours/days ago) as well as active ones
- Ideally works without burning tokens on every heartbeat or stop event

---

## Current approach (Option A — haiku-from-log)

On session stop, the `Stop` hook fires and MemBridge calls Claude Haiku (via Vertex AI or Anthropic API) with the last 20 turns from the JSONL transcript. The result is written to the `sessions.summary` column. Users can manually re-trigger via the "↻ Summarise" button in the dashboard, or edit the summary directly.

**Strengths:**
- Works automatically with no user action
- Works for historical sessions
- No Claude Code skill required

**Weaknesses:**
- 20-turn window misses early context on long sessions
- Single `summary` column — each re-summarization overwrites; no history
- Summary quality degrades as session ages (JSONL tail doesn't capture the arc)
- Near compaction, haiku is reconstructing what Claude already knows — lower fidelity than asking Claude directly
- MemBridge takes a dependency on JSONL format

---

## Alternative (Option B — Claude-from-context via `/summarize` skill)

A Claude Code skill (`/summarize`) that runs inside the active session. Claude writes a structured summary file to a known location (`~/.claude-ui/summaries/<session_id>/YYYY-MM-DD.md`) and POSTs it to the MemBridge API. MemBridge reads from the summaries directory rather than parsing JSONL.

```
## Summary
<2–3 sentences of what the session worked on>

## Where we got to
<current state — what's done, what's in progress>

## Next steps
<bulleted list — items Claude believes are remaining>
```

**Strengths:**
- Claude summarizes from its live context — highest fidelity, especially near compaction where the context is already a synthesized view
- Summary history is natural — one file per invocation, nothing overwritten
- Next steps are structured and persistent
- MemBridge decoupled from JSONL format
- Multiple files per session = full audit trail of how the session evolved
- Cheap: only fires when user explicitly asks

**Weaknesses:**
- Requires user to remember to run `/summarize` — no automatic coverage
- Doesn't work for sessions that have already stopped
- Session ID must be accessible to the skill (`$CLAUDE_SESSION_ID` env var)

---

## Hybrid (Option C — both, with skill as primary)

- `/summarize` skill for active sessions (Claude-from-context, writes to file + POSTs to API)
- Stop hook haiku fallback for sessions that end without a skill invocation (writes same file format, same directory)
- MemBridge reads summaries directory as primary source; `sessions.summary` column becomes a display cache

This gives automatic coverage (Option A) plus high-fidelity on-demand summaries (Option B) with a unified output format. The dashboard shows the latest file per session regardless of who generated it.

---

## Decision

**Currently using Option A.** It provides automatic coverage with no user friction and was sufficient to get the dashboard working.

Option C is the target state. The key open questions before moving are:

1. **`$CLAUDE_SESSION_ID`** — is this reliably available to skills, or does it need to be passed via the hook payload?
2. **File format** — do we want markdown or JSON? JSON makes the `## Next steps` section machine-readable for future features (task tracking, Jira sync).
3. **MemBridge API contract** — does the API accept a full summary payload (text + next_steps array) or just raw markdown?
4. **Stop hook quality threshold** — should the haiku fallback be suppressed if a skill-generated summary already exists for the session?

---

## Consequences

- Option A remains in place until Option C is designed and the skill is built
- New `~/.claude-ui/summaries/` directory layout should be designed before implementing Option C to avoid a migration later
- The `summary_source` column (`auto` / `user`) should be extended to include `skill` when Option C is added
- "Next steps" as a concept is deliberately deferred — free-text notes field in the dashboard is the interim solution
