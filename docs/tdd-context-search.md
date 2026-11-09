# TDD: Context Search

Make past session context findable. Today summaries, notes, and descriptions are
opaque text and `/membridge-context` can only look a session up by ID prefix -
there is no way to ask "which sessions touched X, and what did they decide?"

---

## Decision: SQLite only

A graph database (Omnigraph: typed property graph on Lance with branches,
three-way merge, and hybrid vector/BM25/graph queries) was evaluated as the
context store. Rejected for now:

- Its distinctive value is **branch-and-merge of agent-written context**
  (agents propose, a human merges). MemBridge does not want an approval step.
- Without that, the remaining benefits are reproducible in SQLite for a
  single-user localhost tool: CHECK constraints / partial unique indexes for
  typed rules, FTS5 for BM25, sqlite-vec or BLOB embeddings for vectors, joins
  for traversal, and the append-only `session_summaries` log for history.
- It would add a second always-on server, Lance maintenance (`optimize`,
  `cleanup`), a pre-1.0 storage format, and no Python SDK.
- The heartbeat / touch write path (one write per prompt and per tool call) is a
  poor fit for a commit-per-write versioned store regardless.

The valuable part - turning summaries into structure - is storage-agnostic and
lands in phase 3 below.

---

## Phases

Each phase ships independently. Only phase 3 adds an LLM call.

### Phase 1 - Full-text search

- `search_index` FTS5 table (`porter unicode61` tokenizer) over summary text,
  session descriptions, and notes. Columns: `session_id`, `kind`
  (`summary` | `description` | `notes`), `ref_id` (summary row id), `text`.
- Kept in sync by triggers on `session_summaries` (insert/delete) and
  `sessions` (insert, update of description/notes, delete). Cascade deletes fire
  the delete triggers, so removing a session removes its index rows.
- Rebuilt from source rows on every server startup (cheap at this size, self-healing).
- `db.search(query, limit)` - user text is tokenised and each term quoted, so
  FTS5 operators and punctuation in input can never raise a syntax error. Terms
  are ANDed; the last term is a prefix match. Hits are ranked by `bm25()` and
  collapsed to one result per session (best hit + snippet + hit count).
- `GET /api/search?q=&limit=` returns the collapsed hits.
- Dashboard: search box in the controls bar. While a query is active the table
  shows matching sessions in rank order (status filter ignored so stale and
  archived sessions are found; project filter still applies), with the matched
  snippet under the description.
- `/membridge-context <query>`: if the argument is not a session ID prefix it
  is treated as a search, printing the top matching sessions with snippets.

Complements, does not replace, `sesh find` (opt-in full transcript search).

### Phase 2 - Typed links (covers BACKLOG "Ticket relationship links")

- `session_tickets(session_id, ticket_key, rel CHECK (rel IN ('working_on','relates_to')))`
  with a partial unique index enforcing one `working_on` per session. Migrate the
  comma-separated `sessions.tickets` column (all existing values become
  `relates_to`).
- `session_links.rel` (`continues` | `related`), existing rows default to
  `related`.

### Phase 3 - Entity extraction

- `entities(id, kind CHECK (kind IN ('decision','topic','file','repo','next_step')), key, text, status)`
  and `session_entities(session_id, entity_id, rel)`.
- Extracted with Haiku when a summary is stored (alongside the existing
  summariser call) plus a one-off backfill script over existing summaries.
- Next steps carry `status`; a later session that completes one closes it.
  Enables "open next steps across all sessions" and "decisions about X".
- Entities are added to `search_index` so phase 1 search covers them.

### Phase 4 - Semantic search (optional)

- Embed each summary (sqlite-vec or a BLOB column), fuse vector and BM25
  rankings with reciprocal-rank fusion.

### Phase 5 - Expose to agents (optional)

- MCP tool or skill so any session can query past context directly.

---

## Open questions

- Phase 3: extract on every summary automatically, or backfill-script first and
  turn on live extraction once quality is confirmed?
- Phase 4: embedding provider (must work with the configured Vertex / API auth).
