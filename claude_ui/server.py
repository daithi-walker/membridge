import asyncio
import logging
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

app = FastAPI(title="Claude UI")

_STATIC_DIR = Path(__file__).parent / "static"


@app.on_event("startup")
def startup() -> None:
    db.init_db()


# ── Models ────────────────────────────────────────────────────────────────────


class HeartbeatPayload(BaseModel):
    session_id: str
    cwd: str
    branch: str = ""
    iterm_tab: str = ""


class StopPayload(BaseModel):
    session_id: str
    stop_reason: str = ""
    transcript_path: str = ""


class SessionPatch(BaseModel):
    summary: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────


@app.post("/api/heartbeat")
def heartbeat(payload: HeartbeatPayload) -> dict:
    db.upsert_heartbeat(
        session_id=payload.session_id,
        cwd=payload.cwd,
        branch=payload.branch or None,
        iterm_tab=payload.iterm_tab or None,
    )
    return {"ok": True}


@app.post("/api/stop")
async def stop(payload: StopPayload) -> dict:
    db.record_stop(payload.session_id, payload.stop_reason)
    # Fire-and-forget summary generation so the hook response is instant
    if payload.transcript_path:
        asyncio.create_task(_generate_summary(payload.session_id, payload.transcript_path))
    return {"ok": True}


async def _generate_summary(session_id: str, transcript_path: str) -> None:
    try:
        session = db.get_session(session_id)
        # Don't overwrite a user-edited summary
        if session and session.get("summary_source") == "user":
            return
        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(None, summarise, transcript_path)
        if summary:
            db.update_summary(session_id, summary, source="auto")
            logger.info("Summary updated for session %s", session_id)
    except Exception as e:
        logger.warning("Summary task failed for %s: %s", session_id, e)


@app.get("/api/sessions")
def sessions() -> list[dict]:
    rows = db.list_sessions()
    now = datetime.now(timezone.utc)
    for row in rows:
        row["status"] = _compute_status(row["last_seen"], now)
    return rows


@app.patch("/api/sessions/{session_id}")
def patch_session(session_id: str, patch: SessionPatch) -> dict:
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if patch.summary is not None:
        db.update_summary(session_id, patch.summary, source="user")
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    html_path = _STATIC_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text())


# Serve static files (JS, CSS) — must be after explicit routes
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _compute_status(last_seen_iso: str, now: datetime) -> str:
    try:
        last = datetime.fromisoformat(last_seen_iso)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        delta = (now - last).total_seconds()
        if delta < 300:
            return "active"
        if delta < 3600:
            return "idle"
        return "stale"
    except Exception:
        return "stale"


def main() -> None:
    import uvicorn
    uvicorn.run("claude_ui.server:app", host="127.0.0.1", port=7842, reload=False)


if __name__ == "__main__":
    main()
