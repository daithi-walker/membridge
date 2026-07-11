# Test Coverage Tracking

This file tracks test coverage baselines across releases. Claude evaluates the delta on each significant release and notes improvements or regressions.

Run coverage locally:
```bash
uv run pytest --cov --cov-report=term-missing
```

---

## 2026-06-24 (focus, summariser, and server route coverage)

90 tests across `test_db.py` (16), `test_server.py` (33), `test_focus.py` (27), `test_summariser.py` (14).

| Module | Stmts | Miss | Cover | Notes |
|--------|-------|------|-------|-------|
| `membridge/__init__.py` | 0 | 0 | 100% | — |
| `membridge/db.py` | 148 | 4 | **97%** | Lines 145-146 (update_notes), 291-292 (update_tickets) — unchanged |
| `membridge/focus.py` | 77 | 0 | **100%** | All paths covered via mocked subprocess/os.kill |
| `membridge/server.py` | 348 | 115 | **67%** | Lifespan/SSE stream/notify/_generate_summary still uncovered |
| `membridge/summariser.py` | 73 | 10 | **86%** | Vertex AI branch and a few edge paths remain |
| **TOTAL** | **646** | **129** | **80%** | +18pp from baseline |

**Improvements vs baseline:**
- `focus.py`: 31% → 100% (+69pp) — injection validators, pid_alive, pid_to_tty, all AppleScript path variants
- `summariser.py`: 22% → 86% (+64pp) — transcript parsing, mocked Anthropic client, error paths
- `server.py`: 62% → 67% (+5pp) — /focus, /rename, /sessions, /pid, /api/notification, /summaries routes added
- Total: 62% → 80% (+18pp) — hit the 80%+ target

**Remaining gaps in `server.py` (67%):**
- SSE `/api/events` stream — requires async generator testing
- `_generate_summary()` async task — requires mocking `summarise()` + asyncio task creation
- `_notify_stop()` — requires mocking `subprocess.Popen`
- `/sync-tabs` thread — requires mocking `subprocess.run`

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

### `focus.py` — **100%** ✓ (achieved 2026-06-24)

### `summariser.py` — **86%** ✓ (target was 60%+)
Remaining 14%:
- Vertex AI branch (`USE_VERTEX=1`) — untested; low priority unless Vertex is in active use
- A few exception paths in `_read_transcript` (line 58/69 alternate content formats)

### `server.py` (67% → target 80%+)
CRUD and state machine are well-covered. Remaining gaps:
- `_generate_summary()` async task — mock `summarise()` + asyncio task
- `_notify_stop()` — mock `subprocess.Popen`; test sound/no-sound and frontmost-session skip
- SSE `/api/events` stream — requires async generator test client
- `/sync-tabs` — mock `threading.Thread` / `subprocess.run`

---

## How to update this file

When a new release lands:
1. Run `uv run pytest --cov --cov-report=term-missing`
2. Copy the coverage table into a new dated section above the baseline
3. Note which targets improved and which new uncovered lines appeared
4. If total coverage drops more than 2%, add a note explaining why (e.g. new module added without tests)
