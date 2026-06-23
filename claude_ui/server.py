import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db
from .summariser import summarise

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MemBridge")

_STATIC_DIR = Path(__file__).parent / "static"


@app.on_event("startup")
async def startup() -> None:
    db.init_db()
    asyncio.create_task(_poll_summary_files())


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


class SettingsPatch(BaseModel):
    active_threshold_secs: int | None = None
    idle_threshold_secs: int | None = None
    refresh_interval_secs: int | None = None


# ── Routes ────────────────────────────────────────────────────────────────────


@app.post("/api/heartbeat")
def heartbeat(payload: HeartbeatPayload) -> dict:
    is_new = db.upsert_heartbeat(
        session_id=payload.session_id,
        cwd=payload.cwd,
        branch=payload.branch or None,
        iterm_tab=payload.iterm_tab or None,
        pid=payload.pid,
        iterm_session_uuid=payload.iterm_session_uuid or None,
    )
    if is_new and payload.iterm_tab:
        project = payload.cwd.split("/")[-1] if payload.cwd else "claude"
        new_name = f"{project}" + (f" · {payload.branch}" if payload.branch else "")
        _rename_iterm_tab(payload.iterm_tab, new_name)
    return {"ok": True}


def _rename_iterm_tab(old_name: str, new_name: str) -> None:
    import urllib.request
    import json as _json
    try:
        body = _json.dumps({"old_name": old_name, "new_name": new_name}).encode()
        req = urllib.request.Request(
            "http://host.docker.internal:7843/rename",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception as e:
        logger.debug("Tab rename skipped: %s", e)


@app.post("/api/touch")
def touch(payload: TouchPayload) -> dict:
    db.touch_session(payload.session_id)
    return {"ok": True}


@app.post("/api/stop")
async def stop(payload: StopPayload) -> dict:
    db.record_stop(payload.session_id, payload.stop_reason)
    if payload.transcript_path:
        asyncio.create_task(_generate_summary(payload.session_id, payload.transcript_path))
    return {"ok": True}


_SUMMARIES_ROOT = Path(os.getenv("MEMBRIDGE_DB", "/data/sessions.db")).parent / "summaries"

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
    import os
    # CLAUDE_PROJECTS_ROOT must be set to the host path that was volume-mounted.
    # Path.home() inside Docker is /root, not the Mac user home.
    projects_root = os.getenv("CLAUDE_PROJECTS_ROOT")
    if not projects_root:
        return None
    for path in Path(projects_root).rglob(f"{session_id}.jsonl"):
        return str(path)
    return None


async def _generate_summary(session_id: str, transcript_path: str) -> None:
    try:
        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(None, summarise, transcript_path)
        if summary:
            db.add_summary(session_id, summary, source="auto")
            logger.info("Summary added for session %s", session_id)
    except Exception as e:
        logger.warning("Summary task failed for %s: %s", session_id, e)


@app.get("/api/sessions")
def sessions() -> list[dict]:
    rows = db.list_sessions()
    now = datetime.now(timezone.utc)
    settings = db.get_settings()
    for row in rows:
        status = _compute_status(
            row["last_seen"], now,
            settings["active_threshold_secs"],
            settings["idle_threshold_secs"],
        )
        # If timestamp says stale but PID is still alive, floor to idle
        if status == "stale" and row.get("pid"):
            if _pid_alive(row["pid"]):
                status = "idle"
        row["status"] = status
    return rows


def _pid_alive(pid: int) -> bool:
    import urllib.request
    try:
        resp = urllib.request.urlopen(
            f"http://host.docker.internal:7843/pid/{pid}", timeout=1
        )
        data = json.loads(resp.read())
        return bool(data.get("alive"))
    except Exception:
        return False


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
    return {"ok": True}


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
            last = last.replace(tzinfo=timezone.utc)
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
    uvicorn.run("claude_ui.server:app", host="127.0.0.1", port=7842, reload=False)


if __name__ == "__main__":
    main()
