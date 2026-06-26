# TDD: Session Links

Cross-link related MemBridge sessions so related work is discoverable from either side.

---

## Goal

Allow sessions to be linked together bidirectionally. A link between session A and session B appears in both panels. Links persist across restarts. The `/membridge-context` command optionally surfaces linked session summaries.

---

## Data Model

### New table: `session_links`

```sql
CREATE TABLE IF NOT EXISTS session_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_a   TEXT NOT NULL,
    session_b   TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (session_a) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (session_b) REFERENCES sessions(session_id) ON DELETE CASCADE,
    UNIQUE (session_a, session_b)
);
```

- Each link is stored **once** (`session_a < session_b` alphabetically, enforced in `db.py`) to prevent duplicates.
- Queries for a given session ID match on either column.
- Cascade delete: removing a session removes its links.

No migration entry needed — `session_links` is a new `CREATE TABLE IF NOT EXISTS` block added to `init_db()`.

### `db.py` additions

| Function | Signature | Behaviour |
|----------|-----------|-----------|
| `add_link` | `(a: str, b: str) -> bool` | Inserts canonical pair (sorted). Returns `True` if inserted, `False` if already existed. |
| `remove_link` | `(a: str, b: str) -> bool` | Deletes the canonical pair. Returns `True` if deleted. |
| `get_links` | `(session_id: str) -> list[LinkedSession]` | Returns all sessions linked to `session_id`, each with `session_id`, `project_name`, `git_branch`, `description`, `last_seen`. |

`LinkedSession` TypedDict:
```python
class LinkedSession(TypedDict):
    session_id: str
    project_name: str
    git_branch: str | None
    description: str | None
    last_seen: str
```

---

## API

### `GET /api/sessions/{id}/links`

Returns linked sessions with enough metadata to render chips.

**Response `200`:**
```json
[
  {
    "session_id": "abc123...",
    "project_name": "membridge",
    "git_branch": "main",
    "description": "[membridge] working on session links",
    "last_seen": "2026-06-25T08:00:00+00:00"
  }
]
```

**Response `404`:** session not found.

---

### `POST /api/sessions/{id}/links`

Add a link. The other session is identified by full UUID or unique prefix (prefix resolved server-side).

**Request body:**
```json
{ "target_id": "abc123" }
```

**Response `200`:** `{"ok": true, "status": "added"}` or `{"ok": true, "status": "already_linked"}`  
**Response `400`:** missing/invalid `target_id`, or `target_id == id` (self-link).  
**Response `404`:** session or target not found.

---

### `DELETE /api/sessions/{id}/links/{target_id}`

Remove a link. `target_id` is the full UUID (returned by GET).

**Response `200`:** `{"ok": true}`  
**Response `404`:** link or session not found.

---

### `GET /api/sessions` — extended response

Each session row gains a `linked_session_ids: list[str]` field (full UUIDs). This lets the dashboard know quickly whether a session has links without a separate fetch.

---

## Dashboard UI

### Panel: "Linked sessions" section

Below the Tickets section in the right-hand panel, a new **Linked sessions** block:

```
Linked sessions
┌──────────────────────────────────┐
│ 🔗 membridge · main  [×]        │
│    [session-link] working on...  │
│ + link session…                  │
└──────────────────────────────────┘
```

- Each linked session renders as a chip showing: short ID (8 chars), project name, branch.
- Hovering the chip shows the description as a tooltip.
- Clicking the chip navigates to that session's panel (`openPanel()`).
- `[×]` removes the link immediately (DELETE then re-render).
- **Add input**: typing in the `+ link session…` field searches by project name, description, or ID prefix. A small inline dropdown shows up to 5 matches. Selecting one POSTs the link. Enter with a raw UUID or prefix also works.

### Session list: link indicator

Sessions with at least one link show a small `🔗` icon in the Status column (alongside `★`). Tooltip: "N linked session(s)".

---

## `/membridge-context` command

When doing a cross-session lookup (`/membridge-context <prefix>`), after the summary history block, append:

```
## Linked sessions
- [membridge · main] abc12345 — [membridge] working on session links feature
```

Self-lookup (no argument) also includes linked sessions if any exist.

---

## Tests

### `tests/test_db.py` additions (~8 tests)

- `test_add_link` — add A↔B, verify `get_links(A)` returns B and `get_links(B)` returns A
- `test_add_link_canonical` — adding B→A when A→B already exists returns `False` (no duplicate)
- `test_add_link_self` — `add_link(a, a)` raises or returns `False`
- `test_remove_link` — add then remove, verify `get_links` returns empty
- `test_remove_link_nonexistent` — removing a non-existent link returns `False` without error
- `test_get_links_empty` — returns `[]` for a session with no links
- `test_get_links_metadata` — returned `LinkedSession` dicts contain project_name, git_branch, description
- `test_cascade_delete` — deleting session A removes links where A appears on either side

### `tests/test_server.py` additions (~6 tests)

- `test_get_links_empty` — `GET /api/sessions/{id}/links` returns `[]` for unlinked session
- `test_get_links_populated` — returns linked session metadata after POST
- `test_get_links_404` — unknown session returns 404
- `test_post_link` — `POST /api/sessions/{id}/links` with valid `target_id` returns `added`
- `test_post_link_duplicate` — second POST returns `already_linked`
- `test_delete_link` — `DELETE /api/sessions/{id}/links/{target_id}` removes the link

---

## Files changed

| File | Change |
|------|--------|
| `membridge/db.py` | New `session_links` table, `add_link`, `remove_link`, `get_links`, `LinkedSession` TypedDict; `list_sessions` extended to include `linked_session_ids` |
| `membridge/server.py` | 3 new routes: GET/POST `/api/sessions/{id}/links`, DELETE `/api/sessions/{id}/links/{target_id}` |
| `membridge/static/app.js` | `initLinksSection()` in panel; chip render; add-link input with search; link indicator in table/card row |
| `membridge/static/index.html` | CSS for link chips and the linked-sessions panel section |
| `commands/membridge-context.md` | Append linked session block for both self and cross-session lookups |
| `tests/test_db.py` | 8 new tests |
| `tests/test_server.py` | 6 new tests |
| `docs/CHANGELOG.md` | Entry under 2026-06 |

No new ADR needed — straightforward relational extension with no architectural trade-offs beyond what's already documented.

---

## Out of scope (this iteration)

- Notifications when a linked session changes state (backlog)
- Link notes/labels (backlog)
- Bulk link import from git history or shared tickets (backlog)
