"""
Human vs AI Moot Court API
===========================
REST + WebSocket API for interactive moot court sessions where law students
participate as Prosecutor or Defense against an AI opponent.

Endpoints:
  POST /api/human/session/start       - Start new human vs AI session
  POST /api/human/session/{id}/argument - Submit student argument
  POST /api/human/session/{id}/ready   - Signal ready for next round
  GET  /api/human/session/{id}         - Get session state
  WS   /ws/human/{session_id}          - WebSocket for real-time updates

WebSocket Events (server → client):
  { "type": "role_selected", "student_role": "prosecutor|defense", "ai_role": "..." }
  { "type": "phase_change", "phase": "evidence|lexigraph|courtroom|done" }
  { "type": "round_start", "round": N, "instruction": "...", "awaiting": "student|ai" }
  { "type": "argument_submitted", "by": "student|ai", "content": "...", "citations": [...] }
  { "type": "validation_feedback", "valid": bool, "feedback": "...", "errors": [...], "warnings": [...] }
  { "type": "ai_thinking", "role": "prosecutor|defense" }
  { "type": "judge_evaluation", "student_scores": {...}, "ai_scores": {...}, "feedback": "..." }
  { "type": "judge_question", "question": "...", "awaiting_response": true }
  { "type": "verdict", "result": "granted|denied", "reasoning": "..." }
  { "type": "error", "message": "...", "recoverable": bool }
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

# ── Path setup ────────────────────────────────────────────────────────────────
_backend_dir = Path(__file__).resolve().parent
_agents_dir  = _backend_dir / "agents"
for _p in [str(_backend_dir), str(_agents_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dotenv import load_dotenv
load_dotenv(_backend_dir / ".env")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="MootCourt Human vs AI API",
    description="Interactive moot court sessions with human participants",
    version="1.0.0",
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

# ── In-memory session storage ─────────────────────────────────────────────────
# In production, use Redis or database
_sessions: Dict[str, Dict[str, Any]] = {}
_active_ws: Dict[str, WebSocket] = {}

# ── Request/Response Models ───────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    case_document: str  # Path to PDF or raw case text
    student_role: str   # "prosecutor" or "defense"
    max_rounds: int = 3
    student_name: Optional[str] = None

class SubmitArgumentRequest(BaseModel):
    argument_text: str

class ReadyForNextRoundRequest(BaseModel):
    pass

# ── Helper Functions ──────────────────────────────────────────────────────────

def emit_to_session(session_id: str, event: dict):
    """Send event to WebSocket if connected"""
    ws = _active_ws.get(session_id)
    if ws:
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(ws.send_text(json.dumps(event)))
        except Exception as e:
            print(f"[WS Error] Failed to send to {session_id}: {e}")

async def run_evidence_and_lexigraph_phase(session_id: str, case_document: str):
    """
    Run evidence analyzer and lexigraph phases in background.
    Updates session state and emits events.
    """
    from agents.evidence.evidence_analyzer import EvidenceAnalyzerAgent
    from agents.lexigraph import lexigraph_node as lexigraph_retrieve
    
    session = _sessions.get(session_id)
    if not session:
        return
    
    try:
        # Phase 1: Evidence Analysis
        emit_to_session(session_id, {"type": "phase_change", "phase": "evidence", "status": "running"})
        
        evidence_agent = EvidenceAnalyzerAgent()
        evidence_result = await asyncio.to_thread(
            evidence_agent.analyze,
            document_text=case_document,
        )
        
        session["case_facts"] = evidence_result.get("facts", [])
        session["evidence_inventory"] = evidence_result.get("evidence_inventory", [])
        
        emit_to_session(session_id, {
            "type": "phase_change",
            "phase": "evidence",
            "status": "completed",
            "facts_count": len(session["case_facts"]),
            "evidence_count": len(session["evidence_inventory"]),
        })
        
        # Phase 2: Lexigraph (Legal Research)
        emit_to_session(session_id, {"type": "phase_change", "phase": "lexigraph", "status": "running"})
        
        lexigraph_result = await asyncio.to_thread(
            lexigraph_retrieve,
            case_facts=session["case_facts"],
            evidence_inventory=session["evidence_inventory"],
        )
        
        session["lexigraph_output"] = lexigraph_result
        
        emit_to_session(session_id, {
            "type": "phase_change",
            "phase": "lexigraph",
            "status": "completed",
            "sections_retrieved": len(lexigraph_result.get("ipc_sections", [])),
            "holdings_retrieved": len(lexigraph_result.get("holdings", [])),
        })
        
        # Phase 3: Initialize courtroom
        emit_to_session(session_id, {"type": "phase_change", "phase": "courtroom", "status": "ready"})
        
        # Initialize human orchestrator
        from agents.orchestrator.human_mode import HumanMootCourtOrchestrator
        
        orchestrator = HumanMootCourtOrchestrator(
            student_role=session["student_role"],
            case_facts=session["case_facts"],
            evidence_inventory=session["evidence_inventory"],
            lexigraph_output=session["lexigraph_output"],
            max_rounds=session["max_rounds"],
            on_event=lambda evt: emit_to_session(session_id, evt)
        )
        
        session["orchestrator"] = orchestrator
        session["phase"] = "courtroom_ready"
        
        # Start round 1
        round_info = orchestrator.start_round(round_no=1)
        
        emit_to_session(session_id, {
            "type": "round_ready",
            "round": 1,
            "instruction": round_info["instruction"],
            "student_role": session["student_role"],
            "ai_role": session["ai_role"],
        })
        
    except Exception as e:
        print(f"[Error] Evidence/Lexigraph phase failed for {session_id}: {e}")
        emit_to_session(session_id, {
            "type": "error",
            "message": f"Failed to analyze case: {str(e)}",
            "recoverable": False,
        })
        session["phase"] = "failed"

# ── REST Endpoints ────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "online",
        "service": "human-vs-ai-moot-court",
        "active_sessions": len(_sessions),
        "version": "1.0.0",
    }

@app.post("/api/human/session/start")
async def start_session(req: StartSessionRequest):
    """
    Start a new human vs AI moot court session.
    
    Returns session_id. Client should connect to WS endpoint for real-time updates.
    Evidence and lexigraph phases run in background.
    """
    session_id = str(uuid.uuid4())
    
    # Validate role
    if req.student_role.lower() not in ["prosecutor", "defense"]:
        raise HTTPException(status_code=400, detail="student_role must be 'prosecutor' or 'defense'")
    
    ai_role = "defense" if req.student_role.lower() == "prosecutor" else "prosecutor"
    
    # Initialize session
    _sessions[session_id] = {
        "id": session_id,
        "student_role": req.student_role.lower(),
        "ai_role": ai_role,
        "student_name": req.student_name or "Student",
        "max_rounds": req.max_rounds,
        "current_round": 0,
        "phase": "initializing",
        "case_document": req.case_document,
        "case_facts": [],
        "evidence_inventory": [],
        "lexigraph_output": {},
        "transcript": [],
        "orchestrator": None,
    }
    
    # Start background processing
    asyncio.create_task(run_evidence_and_lexigraph_phase(session_id, req.case_document))
    
    return {
        "session_id": session_id,
        "student_role": req.student_role.lower(),
        "ai_role": ai_role,
        "max_rounds": req.max_rounds,
        "status": "initialized",
        "message": "Connect to WebSocket for real-time updates. Evidence analysis starting...",
    }

@app.post("/api/human/session/{session_id}/argument")
async def submit_argument(session_id: str, req: SubmitArgumentRequest):
    """
    Submit student's argument for current round.
    Returns validation result. If valid, triggers AI response.
    """
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session["phase"] != "courtroom_ready" and not session["phase"].startswith("round_"):
        raise HTTPException(status_code=400, detail=f"Cannot submit argument in phase: {session['phase']}")
    
    orchestrator = session.get("orchestrator")
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    
    # Submit and validate argument
    result = orchestrator.submit_student_argument(req.argument_text)
    
    if result["status"] == "accepted":
        session["phase"] = "ai_generating"
        
        # Generate AI response in background
        async def generate_ai():
            ai_result = orchestrator.generate_ai_response()
            if ai_result["status"] == "success":
                session["phase"] = "judge_evaluating"
                
                # Get judge evaluation
                evaluation = orchestrator.get_judge_evaluation()
                
                # Check if need more rounds
                if orchestrator.current_round < orchestrator.max_rounds:
                    session["phase"] = "awaiting_next_round"
                else:
                    session["phase"] = "getting_verdict"
                    # TODO: Trigger final verdict
        
        asyncio.create_task(generate_ai())
    
    return result

@app.post("/api/human/session/{session_id}/next_round")
async def start_next_round(session_id: str):
    """
    Start the next round of arguments.
    """
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    orchestrator = session.get("orchestrator")
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    
    next_round = orchestrator.current_round + 1
    
    if next_round > session["max_rounds"]:
        raise HTTPException(status_code=400, detail="Maximum rounds reached")
    
    round_info = orchestrator.start_round(round_no=next_round)
    session["phase"] = f"round_{next_round}_awaiting_student"
    
    return {
        "round": next_round,
        "instruction": round_info["instruction"],
        "phase": session["phase"],
    }

@app.get("/api/human/session/{session_id}")
async def get_session(session_id: str):
    """
    Get current session state.
    """
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Return serializable subset
    return {
        "id": session["id"],
        "student_role": session["student_role"],
        "ai_role": session["ai_role"],
        "student_name": session["student_name"],
        "max_rounds": session["max_rounds"],
        "current_round": session.get("orchestrator").current_round if session.get("orchestrator") else 0,
        "phase": session["phase"],
        "facts_count": len(session.get("case_facts", [])),
        "evidence_count": len(session.get("evidence_inventory", [])),
        "sections_count": len(session.get("lexigraph_output", {}).get("ipc_sections", [])),
        "holdings_count": len(session.get("lexigraph_output", {}).get("holdings", [])),
    }

@app.get("/api/human/session/{session_id}/transcript")
async def get_transcript(session_id: str):
    """
    Get full argument transcript.
    """
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    orchestrator = session.get("orchestrator")
    if not orchestrator:
        return {"transcript": []}
    
    return {
        "session_id": session_id,
        "transcript": orchestrator.transcript,
    }

@app.websocket("/ws/human/{session_id}")
async def ws_human_session(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time session updates.
    """
    session = _sessions.get(session_id)
    if not session:
        await websocket.close(code=404, reason="Session not found")
        return
    
    await websocket.accept()
    _active_ws[session_id] = websocket
    print(f"[WS] Human session connected: {session_id[:16]}...")
    
    # Send initial state
    await websocket.send_text(json.dumps({
        "type": "connected",
        "session_id": session_id,
        "student_role": session["student_role"],
        "ai_role": session["ai_role"],
        "phase": session["phase"],
    }))
    
    try:
        while True:
            # Keep connection alive, accept client messages if needed
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=300)
            
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")
                
                if msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                
                elif msg_type == "get_state":
                    await websocket.send_text(json.dumps({
                        "type": "state",
                        "phase": session["phase"],
                        "current_round": session.get("orchestrator").current_round if session.get("orchestrator") else 0,
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
                    "message": "Invalid JSON",
                    "recoverable": True,
                }))
    
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    
    finally:
        _active_ws.pop(session_id, None)
        print(f"[WS] Human session disconnected: {session_id[:16]}...")

# ── Dev Runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_human_moot:app", host="0.0.0.0", port=8002, reload=True)
