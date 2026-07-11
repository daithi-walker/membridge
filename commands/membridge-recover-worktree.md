---
allowed-tools:
  - Bash
argument-hint: "[worktree-path-or-name]"
description: "Recover worktree tracking after Claude drifts back to the main checkout"
---

Recover the session's worktree tracking. This addresses a known failure mode: if a worktree was created manually (`git worktree add`) instead of via the `EnterWorktree` tool, or tracking desyncs after `/compact`, Claude can silently start operating (and committing) against the main checkout again.

Arguments: $ARGUMENTS (optional — a specific worktree path or name to recover into; if omitted, auto-detect)

```bash
echo "Current directory: $(pwd)"
echo "Current git toplevel: $(git rev-parse --show-toplevel 2>/dev/null)"
echo ""
echo "Registered worktrees:"
git worktree list
```

Using the output above:

- If `$ARGUMENTS` names a specific worktree path or matches one from `git worktree list`, call the `EnterWorktree` tool with `path` set to that worktree.
- Otherwise, compare the current directory/toplevel against the worktree list:
  - If the current directory is not one of the listed worktrees and exactly one worktree exists besides the main checkout, that's almost certainly where the session drifted from — call `EnterWorktree` with `path` set to it.
  - If more than one other worktree exists, list them for the user and ask which to reattach to before calling `EnterWorktree`.
  - If the current directory already matches a worktree, tracking looks fine — say so and don't call `EnterWorktree` (calling it while already correctly tracked will error).
- After calling `EnterWorktree`, run `git status` and `git branch --show-current` to confirm, and report the recovered branch + worktree path back to the user in one line.
