# MemBridge Coding Standards

Derived from the quality review of 2026-06-23. These standards apply to all code in this repository.

---

## Security

### AppleScript / osascript
- **Never** interpolate user-controlled strings directly into AppleScript templates that contain shell `write text` commands. The `.replace('"', '\\"')` pattern is insufficient against semicolons, backticks, and `&&`.
- Validate path inputs against `_SAFE_PATH_RE` and session IDs against `_SAFE_ID_RE` (see `focus.py`) before passing to any AppleScript template.
- When in doubt, prefer structured arguments over string interpolation.

### Markdown rendering
- All `marked.parse()` output **must** be passed through `DOMPurify.sanitize()` before being assigned to `innerHTML`.
- CDN script tags **must** carry `integrity=` (SRI) hashes. Regenerate hashes when bumping CDN versions: `curl -s <url> | openssl dgst -sha384 -binary | openssl base64 -A`.

### Network binding
- The server binds to `127.0.0.1` by default. LAN exposure (`0.0.0.0`) requires explicitly setting `MEMBRIDGE_HOST=0.0.0.0`.
- Document this trade-off whenever changing the default.

### Secrets
- `.env` is gitignored. **Never** commit a populated `.env` file.
- All credentials must come from environment variables. No hardcoded API keys, tokens, or passwords.

### Disclosure protection (public repo)

MemBridge is open source, so tracked files must never leak secrets or **client/confidential information** (session summaries, notes, and ADRs are the usual risk). Two guards enforce this via pre-commit:

- **gitleaks** — scans for API keys/tokens (incl. a custom `sk-ant-` rule in `.gitleaks.toml`).
- **`scripts/disclosure_scan.py`** — flags client/project names, absolute home paths (`/Users/<name>`), internal emails, and blocks committing `.env` / `*.db`.

Client names live in a denylist kept **out of the repo** (committing it would disclose the very names it protects):

- Local: copy `.disclosure-denylist.example.txt` → `.disclosure-denylist.txt` (gitignored) and fill in real terms.
- CI: set a `DISCLOSURE_DENYLIST` secret (newline/comma separated) instead — the scanner prefers the env var.

One-time setup:

```bash
uv run --extra dev pre-commit install     # run scans on every commit
cp .disclosure-denylist.example.txt .disclosure-denylist.txt   # then edit
```

Run against everything on demand: `uv run --extra dev pre-commit run --all-files`. If a finding is a false positive, use a placeholder owner (e.g. `/Users/you`) or extend the allowlists in `scripts/disclosure_scan.py`. Hooks are bypassable with `--no-verify` and don't run on forked-PR checkouts, so for external contributions the same scans should also run in CI.

---

## Error handling

### Backend (Python)
- **Never** use bare `except: pass`. At minimum log at DEBUG with the failing statement and the exception.
- `asyncio.create_task()` calls **must** attach a `done_callback` that logs exceptions. Use `_log_task_exception` from `server.py` as the pattern.
- Migration failures in `db.py` are expected for already-applied migrations — log at DEBUG, not WARNING, so they don't pollute normal startup output.

### Frontend (JavaScript)
- All `fetch()` calls that mutate server state (PATCH, POST, DELETE) **must** check `res.ok` and call `showToast('Failed to …')` on failure.
- Do not use `catch(_ => {})` silently. At minimum log to console; for user-visible actions, show a toast.
- The exception: fire-and-forget background fetches (heartbeats, sync-tabs) may be silent — but this should be a conscious choice, documented with a comment.

### Hooks (bash)
- All `curl` calls in hooks must append a failure log line to `/tmp/membridge-hook.log` using `|| echo "[$(date -u +%FT%TZ)] <hook> failed ..." >> /tmp/membridge-hook.log`.
- Hooks run in background (`&`) and must not block Claude Code.

---

## Database

### Parameterised queries only
- All SQL that touches user-supplied values **must** use `?` placeholders. Never use f-strings or `.format()` in SQL.
- Migration statements are the only exception — they are fixed strings with no user data.

### TypedDict for row types
- Functions that return DB rows return `SessionRow | None` or `list[SessionRow]`. Do not return raw `dict`.
- If new columns are added to the schema, add the corresponding field to `SessionRow` in `db.py`.

### Migrations
- Append new migrations to `_MIGRATIONS` in `db.py`. Migrations are idempotent — the `except` clause handles "column already exists" from SQLite.
- When adding a migration, also update `SessionRow` and `_CREATE_SQL` if it adds a new column.

---

## Dependencies

### Version bounds
- All production dependencies in `pyproject.toml` use `>=x.y,<MAJOR+1` bounds (e.g., `>=0.115,<1.0`).
- `uv.lock` is committed and must be regenerated (`uv lock`) after any change to `pyproject.toml` dependencies.
- Dev dependencies live in `[project.optional-dependencies] dev`.

### CDN assets
- Pin to an exact version (e.g., `marked@12.0.0`, not `marked@12`).
- Always include SRI integrity hash and `crossorigin="anonymous"`.

---

## Testing

### Backend
- Tests live in `tests/` and use pytest with in-memory or temp-file SQLite (via `monkeypatch.setattr(db, "DB_PATH", ...)`) — **never** the production DB.
- Every documented feature in `docs/CHANGELOG.md` that has DB-layer behaviour should have at least one test.
- Tests are run with `uv run pytest`.
- Coverage is tracked in `docs/COVERAGE.md`. Update it on each significant release. Do not let total coverage drop more than 2% without documenting why.

### Frontend
- Playwright-based tests live in `tests/frontend/` (to be added — see BACKLOG).
- Test the documented hard-won features: status computation, focus button state, inline editing, summary dedup, SSE refresh.

### CI
- Ruff lint runs on every push/PR via `.github/workflows/lint.yml`.
- `uv run pytest` is expected to pass on every branch before merge.

---

## Style

### Python
- `ruff check` must pass with zero errors. Run `uv run ruff check --fix .` before committing.
- Line length cap: 100 characters (enforced by ruff, formatter-friendly).
- Imports: standard library → third-party → local, each group separated by a blank line (ruff I001 enforces this).
- Prefer `datetime.UTC` over `timezone.utc` (Python 3.11+).
- Prefer `collections.abc.Generator` over `typing.Generator` (Python 3.9+).

### JavaScript
- Vanilla JS only — no build step, no bundler.
- `esc()` for all user-controlled strings that land in `innerHTML` (outside of `renderMarkdown`, which uses DOMPurify).
- `showToast()` for all user-visible save failures.

### Shell
- All hook scripts use `set -euo pipefail`.
- JSON payloads are built via python3 inline (not manual string concatenation) to avoid injection.

---

## Release conventions

See `CLAUDE.md` for the full release checklist. In summary:
1. Add a line to `docs/CHANGELOG.md` (newest first).
2. Add to `docs/RELEASES.md` only when there are breaking changes or migration steps.
3. Add `docs/adr/NNN-title.md` for non-obvious architectural decisions.
