import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db
from . import focus as _focus
from .summariser import summarise

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# SSE broadcast — set of queues, one per connected dashboard tab
_sse_clients: set[asyncio.Queue] = set()
_sse_lock = asyncio.Lock()


def _broadcast(event: str) -> None:
    """Push an event name to all connected SSE clients."""
    dead = set()
    # Snapshot the set before iterating to avoid mutation during iteration
    for q in list(_sse_clients):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.add(q)
    _sse_clients.difference_update(dead)


_STATIC_DIR = Path(__file__).parent / "static"


def _log_task_exception(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception():
        logger.error("Background task %s failed: %s", task.get_name(), task.exception())


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    db.init_db()
    task = asyncio.create_task(_poll_summary_files(), name="poll_summary_files")
    task.add_done_callback(_log_task_exception)
    yield
    task.cancel()


app = FastAPI(title="MemBridge", lifespan=_lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ── Models ────────────────────────────────────────────────────────────────────


class HeartbeatPayload(BaseModel):
    session_id: str
    cwd: str
    branch: str = ""
    iterm_tab: str = ""
    pid: int | None = None
    iterm_session_uuid: str | None = None


class TouchPayload(BaseModel):
    session_id: str


class StopPayload(BaseModel):
    session_id: str
    stop_reason: str = ""
    transcript_path: str = ""


class SessionPatch(BaseModel):
    description: str | None = None
    notes: str | None = None
    archived: bool | None = None
    starred: bool | None = None
    tickets: str | None = None


class SettingsPatch(BaseModel):
    active_threshold_secs: int | None = None
    idle_threshold_secs: int | None = None
    refresh_interval_secs: int | None = None
    notif_popup: int | None = None
    notif_sound: int | None = None


class FocusPayload(BaseModel):
    session_id: str
    pid: int | None = None
    cwd: str | None = None
    iterm_session_uuid: str | None = None
    tab_name: str | None = None


class RenamePayload(BaseModel):
    old_name: str
    new_name: str


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/api/events")
async def sse_events(request: Request) -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue(maxsize=20)
    _sse_clients.add(queue)

    async def generate():
        try:
            yield "data: connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"data: {event}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            _sse_clients.discard(queue)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@app.post("/api/heartbeat")
def heartbeat(payload: HeartbeatPayload) -> dict:
    result = db.upsert_heartbeat(
        session_id=payload.session_id,
        cwd=payload.cwd,
        branch=payload.branch or None,
        iterm_tab=payload.iterm_tab or None,
        pid=payload.pid,
        iterm_session_uuid=payload.iterm_session_uuid or None,
    )
    if result.is_new and payload.iterm_tab:
        # New session — rename the new tab to project · branch
        project = payload.cwd.split("/")[-1] if payload.cwd else "claude"
        new_name = f"{project}" + (f" · {payload.branch}" if payload.branch else "")
        _rename_iterm_tab(payload.iterm_tab, new_name)
    _broadcast("refresh")
    return {"ok": True}


def _rename_iterm_tab(old_name: str, new_name: str) -> None:
    try:
        _focus.rename_tab(old_name, new_name)
    except Exception as e:
        logger.debug("Tab rename skipped: %s", e)


@app.post("/api/touch")
def touch(payload: TouchPayload) -> dict:
    db.touch_session(payload.session_id)
    _broadcast("refresh")
    return {"ok": True}


@app.post("/api/stop")
async def stop(payload: StopPayload) -> dict:
    was_awaiting = db.record_stop(payload.session_id, payload.stop_reason)
    if payload.transcript_path:
        asyncio.create_task(_generate_summary(payload.session_id, payload.transcript_path))
    _notify_stop(payload.session_id, was_awaiting)
    _broadcast("refresh")
    return {"ok": True}


def _notify_stop(session_id: str, was_already_awaiting: bool) -> None:
    try:
        if was_already_awaiting:
            return
        session = db.get_session(session_id)
        if not session:
            return
        settings = db.get_settings()
        if not settings.get("notif_popup", 1):
            return
        uuid = session.get("iterm_session_uuid")
        if uuid and _focus.is_session_frontmost(uuid):
            return
        project = session.get("project_name") or "Claude"
        description = session.get("description") or ""
        subtitle = description.strip("[] \n").split("\n")[0][:80] if description else "Awaiting input"
        use_sound = settings.get("notif_sound", 0)
        sound_clause = 'sound name "Ping"' if use_sound else ""
        script = (
            f'display notification "{subtitle}" '
            f'with title "MemBridge — {project}" '
            + sound_clause
        ).strip()
        import subprocess
        subprocess.Popen(["osascript", "-e", script], close_fds=True)
    except Exception as e:
        logger.debug("Notification skipped: %s", e)


_SUMMARIES_ROOT = Path(os.getenv("MEMBRIDGE_DB", str(Path.home() / ".membridge" / "sessions.db"))).parent / "summaries"

_POLL_INTERVAL = 30  # seconds


async def _poll_summary_files() -> None:
    """Periodically ingest any new summary files written to ~/.membridge/summaries/<session_id>/."""
    import asyncio as _asyncio
    while True:
        await _asyncio.sleep(_POLL_INTERVAL)
        try:
            _ingest_summary_files()
        except Exception as e:
            logger.warning("Summary file poll error: %s", e)


def _ingest_summary_files() -> None:
    if not _SUMMARIES_ROOT.exists():
        return
    for session_dir in _SUMMARIES_ROOT.iterdir():
        if not session_dir.is_dir():
            continue
        session_id = session_dir.name
        if not db.get_session(session_id):
            continue
        for f in sorted(session_dir.glob("*.md")):
            file_path = str(f)
            if db.summary_file_already_ingested(file_path):
                continue
            try:
                text = f.read_text().strip()
                if text:
                    db.add_summary(session_id, text, source="skill", file_path=file_path)
                    logger.info("Ingested summary file %s", file_path)
            except Exception as e:
                logger.warning("Failed to ingest %s: %s", file_path, e)


def _find_transcript(session_id: str) -> str | None:
    projects_root = os.getenv("CLAUDE_PROJECTS_ROOT") or str(Path.home() / ".claude" / "projects")
    for path in Path(projects_root).rglob(f"{session_id}.jsonl"):
        return str(path)
    return None


async def _generate_summary(session_id: str, transcript_path: str) -> None:
    try:
        size = Path(transcript_path).stat().st_size
    except OSError:
        logger.warning("Transcript not found: %s", transcript_path)
        return
    # Dedup key: path + size — skip if we already summarised this exact snapshot
    dedup_key = f"{transcript_path}:{size}"
    if db.summary_file_already_ingested(dedup_key):
        logger.info("Auto-summary already ingested for %s @ %d bytes, skipping", transcript_path, size)
        return
    try:
        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(None, summarise, transcript_path)
        if summary:
            if summary == db.last_auto_summary_text(session_id):
                logger.info("Auto-summary text unchanged for session %s, skipping insert", session_id)
            else:
                db.add_summary(session_id, summary, source="auto", file_path=dedup_key)
                logger.info("Auto-summary added for session %s (%d bytes)", session_id, size)
    except Exception as e:
        logger.warning("Summary task failed for %s: %s", session_id, e)


@app.get("/api/sessions")
def sessions() -> list[dict]:
    rows = db.list_sessions()
    now = datetime.now(UTC)
    settings = db.get_settings()
    result: list[dict] = []
    for row in rows:
        d = dict(row)
        status = _compute_status(
            str(d["last_seen"]), now,
            settings["active_threshold_secs"],
            settings["idle_threshold_secs"],
        )
        # If timestamp says stale but PID is still alive, floor to idle
        pid = d.get("pid")
        if status == "stale" and isinstance(pid, int):
            if _pid_alive(pid):
                status = "idle"
        d["status"] = status
        result.append(d)
    return result


def _pid_alive(pid: int) -> bool:
    try:
        return _focus.pid_alive(pid)
    except Exception:
        return False


@app.post("/focus")
def focus(payload: FocusPayload) -> dict:
    if not payload.session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    action = _focus.focus_session(
        session_id=payload.session_id,
        iterm_uuid=payload.iterm_session_uuid,
        pid=payload.pid,
        cwd=payload.cwd,
        tab_name=payload.tab_name,
    )
    return {"ok": True, "action": action}


@app.post("/rename")
def rename(payload: RenamePayload) -> dict:
    if not payload.old_name or not payload.new_name:
        raise HTTPException(status_code=400, detail="old_name and new_name required")
    action = _focus.rename_tab(payload.old_name, payload.new_name)
    return {"ok": True, "action": action}


@app.get("/sessions")
def list_iterm_sessions() -> dict:
    names = _focus.list_sessions()
    return {"sessions": names, "count": len(names)}


@app.get("/pid/{pid}")
def check_pid(pid: int) -> dict:
    return {"alive": _focus.pid_alive(pid)}


@app.post("/sync-tabs")
def sync_tabs() -> dict:
    import subprocess as _sp
    import sys
    import threading
    _sync = os.path.join(os.path.dirname(__file__), "..", "scripts", "sync_iterm_tabs.py")

    def _run():
        _sp.run([sys.executable, _sync], capture_output=True, timeout=60)

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "status": "started", "eta_secs": 35}


@app.get("/api/sessions/{session_id}/summaries")
def get_summaries(session_id: str) -> list[dict]:
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return db.get_summaries(session_id)


@app.patch("/api/sessions/{session_id}")
def patch_session(session_id: str, patch: SessionPatch) -> dict:
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if patch.description is not None:
        db.update_description(session_id, patch.description)
    if patch.notes is not None:
        db.update_notes(session_id, patch.notes)
    if patch.archived is not None:
        db.set_archived(session_id, patch.archived)
    if patch.starred is not None:
        db.set_starred(session_id, patch.starred)
    if patch.tickets is not None:
        db.update_tickets(session_id, patch.tickets)
    return {"ok": True}


class NotificationPayload(BaseModel):
    session_id: str
    notif_type: str = ""
    message: str = ""


@app.post("/api/notification")
def notification(payload: NotificationPayload) -> dict:
    was_awaiting = db.record_stop(payload.session_id, f"notification:{payload.notif_type}")
    _broadcast("refresh")
    _notify_stop(payload.session_id, was_awaiting)
    logger.info("Notification hook: session=%s type=%s", payload.session_id, payload.notif_type)
    return {"ok": True}


class PushSummaryPayload(BaseModel):
    text: str
    source: str = "skill"


@app.post("/api/sessions/{session_id}/push-summary")
def push_summary(session_id: str, payload: PushSummaryPayload) -> dict:
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    if payload.text.strip() == db.last_auto_summary_text(session_id):
        return {"ok": True, "status": "unchanged"}
    db.add_summary(session_id, payload.text.strip(), source=payload.source, file_path=None)
    logger.info("Summary pushed for session %s (source=%s)", session_id, payload.source)
    return {"ok": True, "status": "added"}


@app.post("/api/sessions/{session_id}/summarise")
async def trigger_summarise(session_id: str) -> dict:
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    transcript_path = _find_transcript(session_id)
    if not transcript_path:
        raise HTTPException(status_code=404, detail="Transcript not found")
    asyncio.create_task(_generate_summary(session_id, transcript_path))
    return {"ok": True, "status": "queued"}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete_session(session_id)
    return {"ok": True}


@app.get("/api/settings")
def get_settings() -> dict:
    return db.get_settings()


@app.patch("/api/settings")
def patch_settings(patch: SettingsPatch) -> dict:
    updates = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields provided")
    return db.update_settings(updates)


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    html_path = _STATIC_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text())


# Serve static files — must be after explicit routes
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _compute_status(
    last_seen_iso: str,
    now: datetime,
    active_secs: int = 300,
    idle_secs: int = 7200,
) -> str:
    try:
        last = datetime.fromisoformat(last_seen_iso)
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        delta = (now - last).total_seconds()
        if delta < active_secs:
            return "active"
        if delta < idle_secs:
            return "idle"
        return "stale"
    except Exception:
        return "stale"


def main() -> None:
    import uvicorn
    uvicorn.run("membridge.server:app", host="127.0.0.1", port=7842, reload=False)


if __name__ == "__main__":
    main()
