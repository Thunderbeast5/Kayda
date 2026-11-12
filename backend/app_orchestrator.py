"""
MootCourt WebSocket + REST API
================================
Exposes the orchestrator over:

  WS  /ws/simulate/{session_id}   — real-time simulation stream
  POST /api/simulate               — trigger a simulation (returns session_id)
  GET  /api/session/{session_id}   — get full session state from Redis
  GET  /api/session/{session_id}/transcript — get full transcript
  GET  /api/health                 — health check

WebSocket event types (server → client):
  { "type": "phase_change",   "phase": "..." }
  { "type": "agent_message",  "agent": "...", "round": N, "content": "...", "citations": [...] }
  { "type": "judge_question", "to": "accused", "question": "..." }
  { "type": "judge_scores",   "legal_validity": N, "evidence_linkage": N, "logic_coherence": N }
  { "type": "verdict",        "result": "...", "confidence": N, "explanation": "..." }
  { "type": "error",          "message": "...", "recoverable": true/false }

Client → server messages:
  { "type": "pause" }
  { "type": "resume" }
  { "type": "upload_document", "content": "..." }
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

# ── Path setup ────────────────────────────────────────────────────────────────
_backend_dir = Path(__file__).resolve().parent
_agents_dir  = _backend_dir / "agents"
for _p in [str(_backend_dir), str(_agents_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dotenv import load_dotenv
load_dotenv(_backend_dir / ".env")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agents.orchestrator.orchestrator_graph import run_orchestrator
from agents.orchestrator.session_input import session_input_manager, normalize_role, normalize_mode, get_ai_role

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="MootCourt Orchestrator API",
    description="Real-time moot court simulation via WebSocket + REST",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
        "http://localhost:3000", "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── In-memory session registry (maps session_id → WebSocket) ─────────────────
_active_ws: dict[str, WebSocket] = {}


# ── Redis helper ──────────────────────────────────────────────────────────────

def _redis():
    try:
        import redis
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            r = redis.from_url(redis_url, decode_responses=True)
        else:
            r = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                decode_responses=True,
            )
        r.ping()
        return r
    except Exception:
        return None


def _redis_get(key: str):
    r = _redis()
    if r:
        try:
            raw = r.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            pass
    return None


def _redis_lrange(key: str):
    r = _redis()
    if r:
        try:
            items = r.lrange(key, 0, -1)
            return [json.loads(i) for i in items]
        except Exception:
            pass
    return []


# ── REST models ───────────────────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    case_id: str                      # path to PDF/TXT or raw text
    session_id: Optional[str] = None
    max_rounds: int = 2
    role: Optional[str] = "prosecutor"  # 'prosecutor' | 'defense'
    mode: Optional[str] = "ai_vs_human" # 'ai_vs_human' | 'ai_vs_ai'
    human_argument: Optional[str] = None


class SubmitArgumentRequest(BaseModel):
    session_id: str
    argument: str
    role: Optional[str] = None
    round_no: Optional[int] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    r = _redis()
    return {
        "status": "online",
        "redis": "connected" if r else "unavailable",
        "version": "2.0.0",
        "supported_roles": ["prosecutor", "defense"],
        "supported_modes": ["ai_vs_human", "ai_vs_ai"],
    }


@app.get("/api/roles")
async def list_roles():
    """Returns available modes and roles for frontend selection."""
    return {
        "modes": [
            {
                "id": "ai_vs_human",
                "name": "AI vs Human",
                "description": "Interactive courtroom debate: You play one role, AI plays the opposing counsel, AI Judge adjudicates.",
            },
            {
                "id": "ai_vs_ai",
                "name": "AI vs AI Simulation",
                "description": "Fully automated simulation: Public Prosecutor (AI) vs Defense Counsel (AI), evaluated by AI Judge.",
            },
        ],
        "roles": [
            {
                "id": "prosecutor",
                "name": "Public Prosecutor",
                "description": "Represent the State: Establish statutory ingredients, prima facie guilt, and oppose bail/discharge.",
                "ai_opponent": "Defense Counsel",
            },
            {
                "id": "defense",
                "name": "Defense Counsel",
                "description": "Represent the Accused: Challenge evidence, establish procedural compliance, argue for bail/discharge.",
                "ai_opponent": "Public Prosecutor",
            },
        ],
    }


@app.post("/api/simulate")
async def start_simulation(req: SimulateRequest, background_tasks: BackgroundTasks):
    """
    Start a simulation. Returns session_id immediately.
    Connect to /ws/simulate/{session_id} to receive real-time events.
    """
    sid = req.session_id or str(uuid.uuid4())[:8]
    norm_role = normalize_role(req.role)
    norm_mode = normalize_mode(req.mode, norm_role)

    async def _run():
        """Run orchestrator in background, forwarding events to the WebSocket."""
        def emit(event: dict):
            ws = _active_ws.get(sid)
            if ws:
                # Schedule coroutine on the event loop
                try:
                    loop = asyncio.get_event_loop()
                    loop.call_soon_threadsafe(
                        loop.create_task,
                        ws.send_text(json.dumps(event))
                    )
                except Exception:
                    pass

        await asyncio.to_thread(
            run_orchestrator,
            case_id=req.case_id,
            session_id=sid,
            max_rounds=req.max_rounds,
            on_event=emit,
            user_role=norm_role,
            mode=norm_mode,
            human_argument=req.human_argument,
        )

    background_tasks.add_task(_run)
    return {
        "session_id": sid,
        "status": "started",
        "user_role": norm_role,
        "mode": norm_mode,
        "ai_role": get_ai_role(norm_role, norm_mode),
    }


@app.post("/api/simulate/argument")
@app.post("/api/session/{session_id}/argument")
async def submit_argument_endpoint(req: SubmitArgumentRequest, session_id: Optional[str] = None):
    """
    REST endpoint for frontend to submit human argument when it's the user's turn.
    """
    sid = session_id or req.session_id
    text = (req.argument or "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"success": False, "message": "Argument cannot be empty."})

    accepted = session_input_manager.submit_argument(
        session_id=sid,
        argument=text,
        role=req.role,
        round_no=req.round_no,
    )
    return {
        "success": True,
        "session_id": sid,
        "accepted": accepted,
        "message": "Argument submitted to orchestrator pipeline.",
    }


@app.websocket("/ws/simulate/{session_id}")
async def ws_simulate(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint. Client connects here to receive real-time events.
    Also accepts control messages: pause, resume, submit_argument, upload_document.
    """
    await websocket.accept()
    _active_ws[session_id] = websocket
    print(f"[WS] Client connected — session {session_id[:16]}…")

    try:
        while True:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=300)
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "pause":
                    print(f"[WS] Pause requested for session {session_id[:16]}…")

                elif msg_type == "resume":
                    print(f"[WS] Resume requested for session {session_id[:16]}…")

                elif msg_type in ("submit_argument", "argument", "human_argument"):
                    # Human user submitted an argument turn from frontend
                    arg_text = msg.get("content", "") or msg.get("argument", "") or msg.get("text", "")
                    role = msg.get("role")
                    round_no = msg.get("round") or msg.get("round_no")
                    accepted = session_input_manager.submit_argument(
                        session_id=session_id,
                        argument=arg_text,
                        role=role,
                        round_no=round_no,
                    )
                    await websocket.send_text(json.dumps({
                        "type": "ack",
                        "action": "argument_received",
                        "accepted": accepted,
                        "message": "Argument submitted to active courtroom session.",
                    }))

                elif msg_type == "upload_document":
                    content = msg.get("content", "")
                    if content:
                        await websocket.send_text(json.dumps({
                            "type": "ack",
                            "message": "Document received. Will be considered in next round.",
                        }))

                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                        "recoverable": True,
                    }))

            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON message.",
                    "recoverable": True,
                }))

    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        _active_ws.pop(session_id, None)
        print(f"[WS] Client disconnected — session {session_id[:16]}…")


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Get full session state snapshot from Redis."""
    state = _redis_get(f"session:{session_id}:state")
    if state is None:
        return JSONResponse(status_code=404, content={"error": "Session not found."})
    return {"session_id": session_id, "state": state}


@app.get("/api/session/{session_id}/transcript")
async def get_transcript(session_id: str):
    """Get the full ordered transcript from Redis."""
    transcript = _redis_lrange(f"session:{session_id}:transcript")
    return {"session_id": session_id, "turns": transcript, "count": len(transcript)}


@app.get("/api/session/{session_id}/testimony")
async def get_testimony(session_id: str):
    """Get only the accepted accused testimony from Redis."""
    testimony = _redis_lrange(f"session:{session_id}:testimony")
    return {"session_id": session_id, "testimony": testimony}


# ── Dev runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_orchestrator:app", host="0.0.0.0", port=8001, reload=True)
