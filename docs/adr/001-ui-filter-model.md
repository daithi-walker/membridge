# ADR 001: UI Filter Model

**Date:** 2026-06-23  
**Status:** Accepted

## Context

The dashboard needs to filter sessions by two independent dimensions:

1. **Session type** — computed status (active/idle/stale) plus the archived flag
2. **Project** — which working directories to show

Early versions used simple boolean checkboxes: "Show stale" and "Show archived". This made it impossible to view *only* archived sessions — you could only add them to the existing view.

## Decision

Use two multi-select dropdowns, both backed by inclusion `Set` objects:

**Show ▾** — controls which session types are visible:
- Options: `active`, `idle`, `stale`, `archived`
- Default: `{active, idle}` — stale and archived hidden unless opted in
- Persisted to `localStorage` as `mb-show-filter`

**Projects ▾** — controls which projects are visible:
- Empty set = all projects (no filter)
- Non-empty set = inclusion list (only listed projects shown)
- `__none__` sentinel = show nothing (all checkboxes unchecked)
- Persisted to `localStorage` as `mb-project-filter`

### Filter logic in `render()`

Archived sessions are filtered on the `archived` flag first, then status for non-archived rows:

```js
let visible = all.filter(s => {
  if (s.archived) return showFilter.has('archived');
  return showFilter.has(s.status);
});
```

This means a session that is both `active` and `archived` only appears when "Archived" is checked — the archived flag takes precedence.

## Alternatives considered

**Single status field including "archived"** — rejected. `archived` is a deliberate user action stored in the DB; `status` is computed from heartbeat timestamps. Conflating them would lose the recency signal on archived sessions and complicate the data model.

**Boolean checkboxes** — rejected. Can't express "show only archived" — you could only toggle stale or archived on top of the base view.

## Consequences

- Users can view only archived sessions by unchecking active/idle/stale and checking archived
- The `__none__` sentinel is an implementation detail; it should never appear in the UI
- Adding a new status value (e.g. `thinking`) only requires adding a checkbox to the Show dropdown
