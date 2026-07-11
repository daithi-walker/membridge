# Idea: Per-Session Claude Code Settings

## What
Surface per-session state in the dashboard: auto-accept mode, permission mode, model, fast mode, plan mode. Bonus: allow toggling settings remotely from the dashboard.

## Why it's interesting
When running multiple sessions, knowing which one has auto-accept on (vs requiring confirmation) would prevent surprises. Remote control would let you flip a session into auto-accept for a long-running task without switching tabs.

## What's possible today
- **Model name**: already in some hook payloads — surfaceable now
- **Plan mode**: inferrable if `ExitPlanMode` tool calls appear in PreToolUse stream
- **Accept-edits state**: inferrable indirectly — no `permission_prompt` notifications = likely auto-accept
- **Cwd / branch**: already tracked

## Blocker
Claude Code has no local IPC socket or REST endpoint. Settings live in `~/.claude/settings.json` (global, not per-session). Anthropic would need to expose a per-session socket (e.g. `~/.claude/sessions/<id>.sock`) for read/write.

## Revisit when
- Anthropic adds a local session API or plugin hook
- Claude Code exposes session metadata in hook payloads more fully
