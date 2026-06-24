# Test Coverage Tracking

This file tracks test coverage baselines across releases. Claude evaluates the delta on each significant release and notes improvements or regressions.

Run coverage locally:
```bash
uv run pytest --cov --cov-report=term-missing
```

---

## Baseline — 2026-06-23 (quality review release)

First test suite. 35 tests across `test_db.py` (16) and `test_server.py` (19).

| Module | Stmts | Miss | Cover | Notes |
|--------|-------|------|-------|-------|
| `membridge/__init__.py` | 0 | 0 | 100% | — |
| `membridge/db.py` | 148 | 4 | **97%** | Lines 145-146 (update_notes), 291-292 (update_tickets) — trivially correct, low priority |
| `membridge/focus.py` | 77 | 53 | **31%** | All osascript/subprocess paths require mocking — see improvement targets below |
| `membridge/server.py` | 344 | 130 | **62%** | Focus/rename routes, SSE streaming, auto-summary task, notification dispatch uncovered |
| `membridge/summariser.py` | 73 | 57 | **22%** | Requires mocking Anthropic API client — see improvement targets below |
| **TOTAL** | **642** | **244** | **62%** | — |

---

## Coverage improvement targets

### `focus.py` (31% → target 70%+)
All uncovered paths require mocking `subprocess.run` to simulate osascript responses. Priority:
- `pid_to_tty()` — mock `ps` output
- `pid_alive()` — mock `os.kill`
- `focus_session()` — mock `_run()` to return "focused" / "not_found"
- `rename_tab()`, `list_sessions()`, `is_session_frontmost()` — mock `_run()`
- Injection validation paths — test that unsafe `cwd`/`session_id` values are rejected

### `summariser.py` (22% → target 60%+)
Requires mocking `anthropic.Anthropic()`. Priority:
- `summarise()` with a mock transcript file
- Empty/short transcript edge cases
- API error / None return handling
- Vertex AI branch (if `USE_VERTEX=1`)

### `server.py` (62% → target 80%+)
Already well-covered for CRUD and state machine. Remaining gaps:
- `/focus` and `/rename` routes — mock `_focus.focus_session()`
- `/sync-tabs` — mock `subprocess.run`
- `_generate_summary()` async task — mock `summarise()`
- `_notify_stop()` — mock `subprocess.Popen`
- SSE `/api/events` stream — requires async test client

---

## How to update this file

When a new release lands:
1. Run `uv run pytest --cov --cov-report=term-missing`
2. Copy the coverage table into a new dated section above the baseline
3. Note which targets improved and which new uncovered lines appeared
4. If total coverage drops more than 2%, add a note explaining why (e.g. new module added without tests)
