# import os
# import sys
# import shutil
# import uuid
# import asyncio
# from pathlib import Path
# from fastapi import FastAPI, UploadFile, File
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import JSONResponse
# from pydantic import BaseModel

# # Add agents directory and MootCourt root to system path so that internal imports work
# backend_dir = Path(__file__).resolve().parent
# mootcourt_root = backend_dir.parent
# agents_dir = backend_dir / "agents"

# if str(agents_dir) not in sys.path:
#     sys.path.insert(0, str(agents_dir))
# if str(backend_dir) not in sys.path:
#     sys.path.insert(0, str(backend_dir))
# if str(mootcourt_root) not in sys.path:
#     sys.path.insert(0, str(mootcourt_root))

# from evidence.evidence_analyzer import (
#     build_session_id,
#     extract_text,
#     extract_facts,
#     store_to_firestore,
#     store_to_pinecone,
#     _get_firestore_client,
#     IMAGE_EXTENSIONS,
# )
# from backend.agents.lexigraph.cypher.legal_text2cypher.agents.pipeline import run_pipeline
# from backend.agents.lexigraph.cypher.legal_text2cypher.config.settings import get_settings
# from backend.agents.lexigraph.lexigraph_agent import LexiGraphAgent

# lexigraph_agent_instance = None


# def get_lexigraph_agent():
#     global lexigraph_agent_instance
#     if lexigraph_agent_instance is None:
#         from backend.agents.lexigraph.lexigraph_agent import LexiGraphAgent
#         lexigraph_agent_instance = LexiGraphAgent()
#     return lexigraph_agent_instance

# from fastapi.responses import StreamingResponse
# from backend.observer.case_service import list_cases, get_case, normalize_case_data, build_events, _turn_delay

# app = FastAPI(title="MootCourt Legal Intelligence & Evidence API")

# # Enable CORS for localhost and 127.0.0.1 on various ports
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         "http://localhost:5173",
#         "http://127.0.0.1:5173",
#         "http://localhost:5174",
#         "http://127.0.0.1:5174",
#         "http://localhost:5175",
#         "http://127.0.0.1:5175",
#     ],
#     allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# # ── Observer Mode Case Bank Endpoints ─────────────────────────────────────
# @app.get("/api/cases")
# async def api_list_cases():
#     cases = await asyncio.to_thread(list_cases)
#     return cases


# @app.get("/api/cases/{case_id}")
# async def api_get_case(case_id: str):
#     case = await asyncio.to_thread(get_case, case_id)
#     if case is None:
#         return JSONResponse(status_code=404, content={"error": "Case not found"})

#     return {
#         "caseData": normalize_case_data(case, case_id),
#         "metadata": case.get("case_metadata", {}),
#         "participants": case.get("participants", {}),
#         "legal_principles": case.get("legal_principles_established", []),
#     }


# @app.get("/api/simulate/{case_id}")
# async def api_simulate(case_id: str):
#     events = await asyncio.to_thread(build_events, case_id)
#     if events is None:
#         return JSONResponse(status_code=404, content={"error": "Case not found"})

#     async def event_generator():
#         for evt in events:
#             delay = _turn_delay(evt["full_text"])
#             await asyncio.sleep(delay)
#             yield f"data: {json.dumps(evt)}\n\n"
#         yield f"data: {json.dumps({'type': 'verdict', 'message': 'Court stands adjourned.'})}\n\n"

#     return StreamingResponse(
#         event_generator(),
#         media_type="text/event-stream",
#         headers={
#             "Cache-Control": "no-cache",
#             "X-Accel-Buffering": "no",
#         },
#     )


# TEMP_DIR = backend_dir / "temp_uploads"
# TEMP_DIR.mkdir(exist_ok=True)

# # Initialize LexiGraph Agent
# lexigraph_agent = LexiGraphAgent()


# class CypherQueryRequest(BaseModel):
#     query: str


# class LexiGraphAgentQueryRequest(BaseModel):
#     query: str
#     debug: bool = False


# @app.get("/api/cypher/health")
# async def cypher_health():
#     try:
#         cfg = get_settings()
#         return {
#             "status": "online",
#             "neo4j_uri": cfg.neo4j_uri,
#             "model": cfg.groq_model,
#         }
#     except Exception as e:
#         return {"status": "degraded", "error": str(e)}


# @app.post("/api/cypher/query")
# @app.post("/api/query")
# async def cypher_query_endpoint(req: CypherQueryRequest):
#     if not req.query or not req.query.strip():
#         return JSONResponse(
#             status_code=400,
#             content={"success": False, "message": "Query string cannot be empty."}
#         )
    
#     try:
#         # Run synchronous Text2Cypher multi-stage pipeline in threadpool
#         result = await asyncio.to_thread(run_pipeline, req.query.strip())
        
#         # Dump model to json-serializable dict
#         data = result.model_dump(mode="json")
        
#         intent_val = result.intent.value if hasattr(result.intent, "value") else str(result.intent)
        
#         return {
#             "success": True,
#             "data": data,
#             "intent": intent_val,
#             "answer": result.answer,
#             "response": result.answer,
#             "agent": "LexiGraph Cypher",
#         }
#     except Exception as e:
#         print(f"Error executing Text2Cypher pipeline: {str(e)}", file=sys.stderr)
#         return JSONResponse(
#             status_code=500,
#             content={
#                 "success": False,
#                 "message": f"Legal Text2Cypher pipeline error: {str(e)}"
#             }
#         )


# import json
# from datetime import datetime, timezone

# HISTORY_FILE = TEMP_DIR / "lexigraph_history.json"


# def _get_firestore_db():
#     try:
#         return _get_firestore_client()
#     except Exception as e:
#         print(f"[Firebase] Firestore client unavailable from evidence_analyzer: {e}", file=sys.stderr)
#         return None


# def save_lexigraph_query_session(query_id: str, query: str, result: dict) -> dict:
#     created_at = datetime.now(timezone.utc).isoformat()
#     session_data = {
#         "query_id": query_id,
#         "query": query,
#         "created_at": created_at,
#         "pipeline_confidence": result.get("pipeline_confidence", 0.0),
#         "primary_intent": result.get("community", {}).get("primary_intent") if isinstance(result.get("community"), dict) else "general_offences",
#         "recommended_count": len(result.get("recommended_sections") or []),
#         "precedents_count": len(result.get("supporting_cases") or []) + len(result.get("similar_cases") or []),
#         "result": result,
#     }

#     # 1. Save to Firebase Firestore if client available
#     firestore_saved = False
#     try:
#         db = _get_firestore_db()
#         if db:
#             db.collection("lexigraph_queries").document(query_id).set(session_data)
#             firestore_saved = True
#             print(f"[Firebase] Saved LexiGraph query '{query_id}' to Firestore collection 'lexigraph_queries'")
#     except Exception as e:
#         print(f"[Firebase] Firestore set error: {e}", file=sys.stderr)

#     # 2. Local JSON fallback file persistence (always updated)
#     try:
#         history = []
#         if HISTORY_FILE.exists():
#             with open(HISTORY_FILE, "r", encoding="utf-8") as f:
#                 try:
#                     history = json.load(f)
#                 except Exception:
#                     history = []
#         # Prepend latest
#         history.insert(0, session_data)
#         # Cap local storage at 100 entries
#         history = history[:100]
#         with open(HISTORY_FILE, "w", encoding="utf-8") as f:
#             json.dump(history, f, indent=2)
#     except Exception as local_err:
#         print(f"[Firebase] Local history file write error: {local_err}", file=sys.stderr)

#     session_data["saved_to_firestore"] = firestore_saved
#     return session_data


# def list_lexigraph_history(limit: int = 50) -> list:
#     sessions = []
    
#     # Try Firestore first
#     try:
#         db = _get_firestore_db()
#         if db:
#             docs = db.collection("lexigraph_queries").order_by("created_at", direction="DESCENDING").limit(limit).stream()
#             for doc in docs:
#                 data = doc.to_dict()
#                 sessions.append({
#                     "query_id": data.get("query_id") or doc.id,
#                     "query": data.get("query", ""),
#                     "created_at": data.get("created_at", ""),
#                     "pipeline_confidence": data.get("pipeline_confidence", 0.0),
#                     "primary_intent": data.get("primary_intent", "general_offences"),
#                     "recommended_count": data.get("recommended_count", 0),
#                     "precedents_count": data.get("precedents_count", 0),
#                     "source": "firestore"
#                 })
#             if sessions:
#                 return sessions
#     except Exception as e:
#         print(f"[Firebase] Could not fetch history from Firestore: {e}", file=sys.stderr)

#     # Fallback to local JSON store
#     if HISTORY_FILE.exists():
#         try:
#             with open(HISTORY_FILE, "r", encoding="utf-8") as f:
#                 history = json.load(f)
#                 for item in history[:limit]:
#                     sessions.append({
#                         "query_id": item.get("query_id", ""),
#                         "query": item.get("query", ""),
#                         "created_at": item.get("created_at", ""),
#                         "pipeline_confidence": item.get("pipeline_confidence", 0.0),
#                         "primary_intent": item.get("primary_intent", "general_offences"),
#                         "recommended_count": item.get("recommended_count", 0),
#                         "precedents_count": item.get("precedents_count", 0),
#                         "source": "local"
#                     })
#         except Exception as local_err:
#             print(f"[Firebase] Error reading local history: {local_err}", file=sys.stderr)

#     return sessions


# def get_lexigraph_session_by_id(query_id: str) -> dict:
#     # Try Firestore
#     try:
#         db = _get_firestore_db()
#         if db:
#             doc = db.collection("lexigraph_queries").document(query_id).get()
#             if doc.exists:
#                 return doc.to_dict()
#     except Exception as e:
#         print(f"[Firebase] Could not fetch doc '{query_id}' from Firestore: {e}", file=sys.stderr)

#     # Fallback to local JSON
#     if HISTORY_FILE.exists():
#         try:
#             with open(HISTORY_FILE, "r", encoding="utf-8") as f:
#                 history = json.load(f)
#                 for item in history:
#                     if item.get("query_id") == query_id:
#                         return item
#         except Exception as local_err:
#             print(f"[Firebase] Local history lookup error: {local_err}", file=sys.stderr)

#     return None


# @app.post("/api/lexigraph-agent/query")
# @app.post("/api/lexigraph/agent/query")
# @app.post("/api/lexigraph/query")
# async def lexigraph_agent_query_endpoint(req: LexiGraphAgentQueryRequest):
#     if not req.query or not req.query.strip():
#         return JSONResponse(
#             status_code=400,
#             content={"success": False, "message": "Query string cannot be empty."}
#         )
#     try:
#         agent = get_lexigraph_agent()
#         result = await asyncio.to_thread(agent.process_query, req.query.strip(), req.debug)
        
#         query_id = f"lexi_{uuid.uuid4().hex[:12]}"
#         saved_session = await asyncio.to_thread(save_lexigraph_query_session, query_id, req.query.strip(), result)

#         return {
#             "success": True,
#             "query_id": query_id,
#             "prediction_id": result.get("prediction_id"),
#             "created_at": saved_session.get("created_at"),
#             "saved_to_firestore": saved_session.get("saved_to_firestore", False),
#             "data": result,
#             "agent": "LexiGraph Agent",
#         }
#     except Exception as e:
#         print(f"Error executing LexiGraph Agent pipeline: {str(e)}", file=sys.stderr)
#         return JSONResponse(
#             status_code=500,
#             content={
#                 "success": False,
#                 "message": f"LexiGraph Agent error: {str(e)}"
#             }
#         )


# # ── Feedback Loop Endpoints ────────────────────────────────────────────────
# class FeedbackRequest(BaseModel):
#     prediction_id: str
#     correct: bool
#     corrected_section: str | None = None
#     notes: str = ""


# def _get_feedback_service():
#     """Returns the FeedbackService from the singleton LexiGraphAgent."""
#     return get_lexigraph_agent().feedback_service


# @app.post("/api/feedback")
# async def submit_feedback_endpoint(req: FeedbackRequest):
#     """Human feedback intake — attaches a label to a logged prediction."""
#     try:
#         svc = _get_feedback_service()
#         record = await asyncio.to_thread(
#             svc.submit_feedback,
#             prediction_id=req.prediction_id,
#             correct=req.correct,
#             corrected_section=req.corrected_section,
#             notes=req.notes,
#         )
#         return {"success": True, "status": "ok", "data": record}
#     except Exception as e:
#         print(f"Error submitting feedback: {e}", file=sys.stderr)
#         return JSONResponse(
#             status_code=500,
#             content={"success": False, "message": f"Feedback submission failed: {str(e)}"}
#         )


# @app.get("/api/feedback/pending")
# async def list_pending_predictions(limit: int = 50):
#     """Lists predictions awaiting human review or LLM-judge resolution."""
#     try:
#         svc = _get_feedback_service()
#         pending = await asyncio.to_thread(svc.logger.list_pending, limit)
#         return {
#             "success": True,
#             "count": len(pending),
#             "data": pending,
#         }
#     except Exception as e:
#         return JSONResponse(
#             status_code=500,
#             content={"success": False, "message": f"Failed to list pending: {str(e)}"}
#         )


# @app.post("/api/feedback/resolve")
# async def resolve_pending_endpoint(limit: int = 100):
#     """Batch-resolves all pending predictions via LLM judge (or human labels if available)."""
#     try:
#         svc = _get_feedback_service()
#         resolved = await asyncio.to_thread(svc.resolve_all_pending, limit)
#         return {
#             "success": True,
#             "resolved_count": len(resolved),
#             "data": resolved,
#         }
#     except Exception as e:
#         return JSONResponse(
#             status_code=500,
#             content={"success": False, "message": f"Resolution failed: {str(e)}"}
#         )


# @app.get("/api/feedback/breakdown")
# async def failure_breakdown_endpoint(min_trust: str = "soft"):
#     """Returns failure-stage breakdown from resolved incorrect/partial predictions."""
#     try:
#         svc = _get_feedback_service()
#         breakdown = await asyncio.to_thread(svc.get_failure_breakdown, min_trust)
#         return {"success": True, "data": breakdown}
#     except Exception as e:
#         return JSONResponse(
#             status_code=500,
#             content={"success": False, "message": f"Breakdown failed: {str(e)}"}
#         )


# @app.get("/api/lexigraph-agent/history")
# @app.get("/api/lexigraph/history")
# async def get_lexigraph_history_endpoint(limit: int = 50):
#     try:
#         history = await asyncio.to_thread(list_lexigraph_history, limit)
#         return {
#             "success": True,
#             "count": len(history),
#             "data": history
#         }
#     except Exception as e:
#         return JSONResponse(
#             status_code=500,
#             content={"success": False, "message": f"Failed to fetch history: {str(e)}"}
#         )


# @app.get("/api/lexigraph-agent/history/{query_id}")
# @app.get("/api/lexigraph/history/{query_id}")
# async def get_lexigraph_session_endpoint(query_id: str):
#     try:
#         session = await asyncio.to_thread(get_lexigraph_session_by_id, query_id)
#         if not session:
#             return JSONResponse(
#                 status_code=404,
#                 content={"success": False, "message": f"Query record '{query_id}' not found."}
#             )
#         return {
#             "success": True,
#             "data": session
#         }
#     except Exception as e:
#         return JSONResponse(
#             status_code=500,
#             content={"success": False, "message": f"Failed to fetch query session: {str(e)}"}
#         )


# @app.post("/api/evidence/analyze")
# async def analyze_evidence_endpoint(file: UploadFile = File(...)):
#     filename = file.filename or "uploaded_file.pdf"
#     suffix = Path(filename).suffix.lower()
    
#     # Validation
#     if suffix != ".pdf" and suffix not in IMAGE_EXTENSIONS:
#         return JSONResponse(
#             status_code=400,
#             content={
#                 "success": False,
#                 "message": f"Unsupported file type '{suffix}'. Supported formats: PDF, PNG, JPG, JPEG, TIFF, BMP."
#             }
#         )
    
#     # Save the file temporarily
#     temp_file_name = f"{uuid.uuid4().hex}_{filename}"
#     temp_file_path = TEMP_DIR / temp_file_name
    
#     try:
#         with open(temp_file_path, "wb") as buffer:
#             shutil.copyfileobj(file.file, buffer)
            
#         # Generate session_id
#         session_id = build_session_id(str(temp_file_path))
        
#         # Run extraction pipeline
#         raw_text = extract_text(str(temp_file_path))
#         facts = extract_facts(raw_text)
        
#         # Save to Firestore & Pinecone
#         store_to_firestore(session_id, raw_text, facts)
#         store_to_pinecone(session_id, facts)
        
#         return {
#             "success": True,
#             "data": {
#                 "rawText": raw_text,
#                 "facts": facts
#             }
#         }
        
#     except Exception as e:
#         # Log the error details internally
#         print(f"Error during evidence analysis: {str(e)}", file=sys.stderr)
#         return JSONResponse(
#             status_code=500,
#             content={
#                 "success": False,
#                 "message": f"Analysis failed: {str(e)}"
#             }
#         )
        
#     finally:
#         # Clean up temp file
#         if temp_file_path.exists():
#             try:
#                 os.remove(temp_file_path)
#             except Exception as cleanup_err:
#                 print(f"Error cleaning up temp file {temp_file_path}: {cleanup_err}", file=sys.stderr)


# @app.post("/api/lexigraph/analyze")
# async def lexigraph_analyze_endpoint(req: LexiGraphAgentQueryRequest):
#     """
#     LexiGraph Explorer endpoint that processes legal queries using the full
#     hierarchical GraphRAG pipeline (lexigraph_agent.py).
    
#     Expected JSON:
#     {
#         "query": "legal scenario description"
#     }
    
#     Returns:
#     {
#         "success": true/false,
#         "data": {
#             "pipeline_confidence": 0.85,
#             "recommended_sections": [...],
#             "supporting_cases": [...],
#             "supporting_evidence": [...],
#             "supporting_articles": [...],
#             "supporting_principles": [...],
#             "rejected_sections": [...]
#         }
#     }
#     """
#     if not req.query or not req.query.strip():
#         return JSONResponse(
#             status_code=400,
#             content={"success": False, "message": "Query string cannot be empty."}
#         )
    
#     try:
#         # Run the LexiGraph hierarchical retrieval pipeline in threadpool
#         result = await asyncio.to_thread(lexigraph_agent.process_query, req.query.strip(), debug=False)
        
#         return {
#             "success": True,
#             "data": result,
#             "agent": "LexiGraph Explorer"
#         }
#     except Exception as e:
#         print(f"Error executing LexiGraph pipeline: {str(e)}", file=sys.stderr)
#         import traceback
#         traceback.print_exc()
#         return JSONResponse(
#             status_code=500,
#             content={
#                 "success": False,
#                 "message": f"LexiGraph pipeline error: {str(e)}"
#             }
#         )


# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("app:app", host="0.0.0.0", port=5001, reload=True)


import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import shutil
import uuid
import asyncio
from pathlib import Path
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Add agents directory and MootCourt root to system path so that internal imports work
backend_dir = Path(__file__).resolve().parent
mootcourt_root = backend_dir.parent
agents_dir = backend_dir / "agents"

if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(mootcourt_root) not in sys.path:
    sys.path.insert(0, str(mootcourt_root))

from evidence.evidence import (
    build_session_id,
    analyze_evidence_with_context,
    _get_firestore_client,
    IMAGE_EXTENSIONS,
)
lexigraph_agent_instance = None


def get_lexigraph_agent():
    global lexigraph_agent_instance
    if lexigraph_agent_instance is None:
        from backend.agents.lexigraph.lexigraph_agent import LexiGraphAgent
        lexigraph_agent_instance = LexiGraphAgent()
    return lexigraph_agent_instance

from fastapi.responses import StreamingResponse
from backend.observer.case_service import list_cases, get_case, normalize_case_data, build_events, _turn_delay

from matchmaking.api import router as matchmaking_router
from matchmaking.worker import start_matchmaking_worker
from backend.game.api import game_router, ws_router

app = FastAPI(title="MootCourt Legal Intelligence & Evidence API")

@app.on_event("startup")
async def startup_event():
    start_matchmaking_worker()


# Enable CORS for frontend clients (local, Render, Vercel, Netlify)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://kayda.onrender.com",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app|https://.*\.onrender\.com|https://.*\.netlify\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount LexiGraph 7-stage pipeline router
from lexigraph_router import router as lexigraph_pipeline_router
app.include_router(lexigraph_pipeline_router)
app.include_router(matchmaking_router)
app.include_router(game_router)
app.include_router(ws_router)


# ── Health Check Endpoints ───────────────────────────────────────────────
@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "Kayda Legal Intelligence API"}


# ── Observer Mode Case Bank Endpoints ─────────────────────────────────────
@app.get("/api/cases")
async def api_list_cases():
    cases = await asyncio.to_thread(list_cases)
    return cases


@app.get("/api/cases/{case_id}")
async def api_get_case(case_id: str):
    case = await asyncio.to_thread(get_case, case_id)
    if case is None:
        return JSONResponse(status_code=404, content={"error": "Case not found"})

    return {
        "caseData": normalize_case_data(case, case_id),
        "metadata": case.get("case_metadata", {}),
        "participants": case.get("participants", {}),
        "legal_principles": case.get("legal_principles_established", []),
    }


@app.get("/api/simulate/{case_id}/events")
async def api_simulate_events(case_id: str):
    """
    Button-driven observer mode: return the full turn list up front instead
    of pacing it out over SSE. The frontend steps through it on click.
    """
    events = await asyncio.to_thread(build_events, case_id)
    if events is None:
        return JSONResponse(status_code=404, content={"error": "Case not found"})
    return {"case_id": case_id, "events": events}


@app.get("/api/simulate/{case_id}")
async def api_simulate(case_id: str):
    events = await asyncio.to_thread(build_events, case_id)
    if events is None:
        return JSONResponse(status_code=404, content={"error": "Case not found"})

    async def event_generator():
        for evt in events:
            delay = _turn_delay(evt["full_text"])
            await asyncio.sleep(delay)
            yield f"data: {json.dumps(evt)}\n\n"
        yield f"data: {json.dumps({'type': 'verdict', 'message': 'Court stands adjourned.'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


TEMP_DIR = backend_dir / "temp_uploads"
TEMP_DIR.mkdir(exist_ok=True)

from typing import Optional, List, Dict, Any

class LexiGraphAgentQueryRequest(BaseModel):
    query: Optional[str] = None
    text: Optional[str] = None
    debug: bool = False
    court_type: Optional[str] = None
    legal_regime_override: Optional[str] = None
    stage: Optional[int] = None


import json
from datetime import datetime, timezone

from lexigraph_history import (
    save_lexigraph_query_session,
    list_lexigraph_history,
    get_lexigraph_session_by_id,
    build_lexigraph_summary,
)


EVIDENCE_HISTORY_FILE = Path(__file__).resolve().parent / "temp_uploads" / "evidence_history.json"


def _parse_evidence_doc(data: dict, doc_id: str = "") -> dict:
    facts = data.get("facts")
    incident_summary = ""
    incident_date = ""
    incident_time = ""
    incident_place = ""
    vehicles = []

    if isinstance(facts, dict):
        incident = facts.get("incident")
        if isinstance(incident, dict):
            incident_summary = incident.get("summary") or ""
            incident_date = incident.get("date") or ""
            incident_time = incident.get("time") or ""
            incident_place = incident.get("place") or ""
        elif isinstance(incident, str):
            incident_summary = incident

        prop = facts.get("property")
        if isinstance(prop, dict):
            vehicles = prop.get("vehicles") or []
    elif isinstance(facts, list):
        for f in facts:
            if isinstance(f, dict) and f.get("text"):
                incident_summary = f.get("text")[:180]
                break
            elif isinstance(f, str) and f.strip():
                incident_summary = f.strip()[:180]
                break
    elif isinstance(data.get("description"), str):
        incident_summary = data.get("description")

    if not incident_summary and data.get("raw_text"):
        incident_summary = str(data["raw_text"])[:160] + "..."

    def _format_vehicle(vehicle: dict) -> str:
        if not isinstance(vehicle, dict):
            return ""
        parts = [
            vehicle.get("type") or "",
            vehicle.get("make_model") or "",
            f"Reg. {vehicle['registration_no']}" if vehicle.get("registration_no") else "",
        ]
        return " - ".join(part for part in parts if part)

    if not isinstance(vehicles, list):
        vehicles = []

    vehicle_summaries = [
        _format_vehicle(v)
        for v in vehicles
        if isinstance(v, dict)
    ]
    vehicle_summaries = [s for s in vehicle_summaries if s]

    timeline = data.get("timeline") or []
    graph = data.get("graph") or {}

    return {
        "session_id": data.get("session_id") or doc_id,
        "created_at": str(data.get("created_at") or ""),
        "schema_version": str(data.get("schema_version") or ""),
        "context_schema_version": str(data.get("context_schema_version") or ""),
        "filename": data.get("filename") or data.get("source_filename") or "",
        "incident_summary": incident_summary,
        "incident_date": incident_date,
        "incident_time": incident_time,
        "incident_place": incident_place,
        "vehicle_count": len(vehicles),
        "vehicle_summary": ", ".join(vehicle_summaries[:3]),
        "timeline_count": len(timeline) if isinstance(timeline, list) else 0,
        "node_count": len(graph.get("nodes") or []) if isinstance(graph, dict) else (len(graph) if isinstance(graph, list) else 0),
        "edge_count": len(graph.get("edges") or []) if isinstance(graph, dict) else 0,
    }


def list_evidence_history(limit: int = 25) -> list:
    sessions = []
    seen_ids = set()

    # 1. Query Firestore (check primary "document_store" and fallback collections)
    try:
        db = _get_firestore_client()
        if db is not None:
            candidate_collections = ["document_store", "evidence", "evidence_history", "ocr_history", "documents"]
            for col_name in candidate_collections:
                try:
                    col = db.collection(col_name)
                    docs = []
                    try:
                        docs = list(col.order_by("created_at", direction="DESCENDING").limit(limit).stream())
                    except Exception:
                        docs = []
                    if not docs:
                        docs = list(col.limit(limit).stream())

                    for doc in docs:
                        try:
                            d = doc.to_dict() or {}
                            sid = d.get("session_id") or doc.id
                            if sid not in seen_ids:
                                seen_ids.add(sid)
                                sessions.append(_parse_evidence_doc(d, doc.id))
                        except Exception as parse_err:
                            print(f"[Firebase] Error parsing {col_name} doc {doc.id}: {parse_err}", file=sys.stderr)
                    if sessions:
                        break
                except Exception as col_err:
                    print(f"[Firebase] Error reading collection {col_name}: {col_err}", file=sys.stderr)
    except Exception as e:
        print(f"[Firebase] Firestore list_evidence_history error: {e}", file=sys.stderr)

    # 2. Local fallback / augmentation: load from evidence_history.json
    if EVIDENCE_HISTORY_FILE.exists():
        try:
            with open(EVIDENCE_HISTORY_FILE, "r", encoding="utf-8") as f:
                local_data = json.load(f)
                if isinstance(local_data, list):
                    for item in local_data:
                        if isinstance(item, dict):
                            sid = item.get("session_id")
                            if sid and sid not in seen_ids:
                                seen_ids.add(sid)
                                sessions.append(_parse_evidence_doc(item, sid))
        except Exception as local_err:
            print(f"[Firebase] Local evidence history read error: {local_err}", file=sys.stderr)

    return sessions[:limit]


def get_evidence_session_by_id(session_id: str) -> dict:
    # 1. Try Firestore
    try:
        db = _get_firestore_client()
        if db is not None:
            for col_name in ["document_store", "evidence", "evidence_history", "ocr_history", "documents"]:
                try:
                    doc = db.collection(col_name).document(session_id).get()
                    if doc.exists:
                        return doc.to_dict()
                except Exception:
                    continue
    except Exception as e:
        print(f"[Firebase] Firestore get_evidence_session_by_id error: {e}", file=sys.stderr)

    # 2. Try local fallback file
    if EVIDENCE_HISTORY_FILE.exists():
        try:
            with open(EVIDENCE_HISTORY_FILE, "r", encoding="utf-8") as f:
                local_data = json.load(f)
                if isinstance(local_data, list):
                    for item in local_data:
                        if isinstance(item, dict) and item.get("session_id") == session_id:
                            return item
        except Exception as local_err:
            print(f"[Firebase] Local evidence session read error: {local_err}", file=sys.stderr)

    return None


@app.post("/api/lexigraph-agent/query")
@app.post("/api/lexigraph/agent/query")
@app.post("/api/lexigraph/query")
@app.post("/api/lexigraph/pipeline")
async def lexigraph_agent_query_endpoint(req: LexiGraphAgentQueryRequest):
    q = (req.query or req.text or "").strip()
    if not q:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Query string cannot be empty."}
        )
    try:
        agent = get_lexigraph_agent()
        result = await asyncio.to_thread(agent.process_query, q, req.debug)
        
        summary = build_lexigraph_summary(result)
        query_id = f"lexi_{uuid.uuid4().hex[:12]}"
        saved_session = await asyncio.to_thread(save_lexigraph_query_session, query_id, q, result, summary)

        return {
            "success": True,
            "query_id": query_id,
            "prediction_id": result.get("prediction_id"),
            "created_at": saved_session.get("created_at"),
            "saved_to_firestore": saved_session.get("saved_to_firestore", False),
            "data": result,
            "summary": summary,
            "agent": "LexiGraph Agent",
        }
    except Exception as e:
        print(f"Error executing LexiGraph Agent pipeline: {str(e)}", file=sys.stderr)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"LexiGraph Agent error: {str(e)}"
            }
        )


# ── Feedback Loop Endpoints ────────────────────────────────────────────────
class FeedbackRequest(BaseModel):
    prediction_id: str
    correct: bool
    corrected_section: str | None = None
    notes: str = ""


def _get_feedback_service():
    """Returns the FeedbackService from the singleton LexiGraphAgent."""
    return get_lexigraph_agent().feedback_service


@app.post("/api/feedback")
async def submit_feedback_endpoint(req: FeedbackRequest):
    """Human feedback intake — attaches a label to a logged prediction."""
    try:
        svc = _get_feedback_service()
        record = await asyncio.to_thread(
            svc.submit_feedback,
            prediction_id=req.prediction_id,
            correct=req.correct,
            corrected_section=req.corrected_section,
            notes=req.notes,
        )
        return {"success": True, "status": "ok", "data": record}
    except Exception as e:
        print(f"Error submitting feedback: {e}", file=sys.stderr)
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Feedback submission failed: {str(e)}"}
        )


@app.get("/api/feedback/pending")
async def list_pending_predictions(limit: int = 50):
    """Lists predictions awaiting human review or LLM-judge resolution."""
    try:
        svc = _get_feedback_service()
        pending = await asyncio.to_thread(svc.logger.list_pending, limit)
        return {
            "success": True,
            "count": len(pending),
            "data": pending,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to list pending: {str(e)}"}
        )


@app.post("/api/feedback/resolve")
async def resolve_pending_endpoint(limit: int = 100):
    """Batch-resolves all pending predictions via LLM judge (or human labels if available)."""
    try:
        svc = _get_feedback_service()
        resolved = await asyncio.to_thread(svc.resolve_all_pending, limit)
        return {
            "success": True,
            "resolved_count": len(resolved),
            "data": resolved,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Resolution failed: {str(e)}"}
        )


@app.get("/api/feedback/breakdown")
async def failure_breakdown_endpoint(min_trust: str = "soft"):
    """Returns failure-stage breakdown from resolved incorrect/partial predictions."""
    try:
        svc = _get_feedback_service()
        breakdown = await asyncio.to_thread(svc.get_failure_breakdown, min_trust)
        return {"success": True, "data": breakdown}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Breakdown failed: {str(e)}"}
        )


@app.get("/api/lexigraph-agent/history")
@app.get("/api/lexigraph/history")
async def get_lexigraph_history_endpoint(limit: int = 50):
    try:
        history = await asyncio.to_thread(list_lexigraph_history, limit)
        return {
            "success": True,
            "count": len(history),
            "data": history
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to fetch history: {str(e)}"}
        )


@app.get("/api/lexigraph-agent/history/{query_id}")
@app.get("/api/lexigraph/history/{query_id}")
async def get_lexigraph_session_endpoint(query_id: str):
    try:
        session = await asyncio.to_thread(get_lexigraph_session_by_id, query_id)
        if not session:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": f"Query record '{query_id}' not found."}
            )
        return {
            "success": True,
            "data": session
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to fetch query session: {str(e)}"}
        )


@app.post("/api/evidence/analyze")
async def analyze_evidence_endpoint(file: UploadFile = File(...)):
    filename = file.filename or "uploaded_file.pdf"
    suffix = Path(filename).suffix.lower()
    
    # Validation
    if suffix != ".pdf" and suffix not in IMAGE_EXTENSIONS:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": f"Unsupported file type '{suffix}'. Supported formats: PDF, PNG, JPG, JPEG, TIFF, BMP."
            }
        )
    
    # Save the file temporarily
    temp_file_name = f"{uuid.uuid4().hex}_{filename}"
    temp_file_path = TEMP_DIR / temp_file_name
    
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Generate session_id
        session_id = build_session_id(str(temp_file_path))

        # Run the context-aware evidence pipeline so the UI gets
        # raw text, structured facts, timeline, and graph together.
        result = await asyncio.to_thread(
            analyze_evidence_with_context,
            session_id,
            str(temp_file_path),
        )

        # Also persist to local evidence_history.json for reliable history recall
        try:
            history_record = {
                "session_id": session_id,
                "filename": filename,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "raw_text": result.get("rawText", ""),
                "facts": result.get("facts", {}),
                "timeline": result.get("timeline", []),
                "graph": result.get("graph", {}),
            }
            records = []
            if EVIDENCE_HISTORY_FILE.exists():
                try:
                    with open(EVIDENCE_HISTORY_FILE, "r", encoding="utf-8") as hf:
                        records = json.load(hf)
                        if not isinstance(records, list):
                            records = []
                except Exception:
                    records = []
            records = [r for r in records if r.get("session_id") != session_id]
            records.insert(0, history_record)
            with open(EVIDENCE_HISTORY_FILE, "w", encoding="utf-8") as hf:
                json.dump(records[:100], hf, indent=2, ensure_ascii=False)
        except Exception as save_err:
            print(f"[Firebase] Failed to write local evidence history backup: {save_err}", file=sys.stderr)

        return {
            "success": True,
            "data": {
                "sessionId": session_id,
                **result,
            },
        }

    except Exception as e:
        # Log the error details internally
        print(f"Error during evidence analysis: {str(e)}", file=sys.stderr)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Analysis failed: {str(e)}"
            }
        )
        
    finally:
        # Clean up temp file
        if temp_file_path.exists():
            try:
                os.remove(temp_file_path)
            except Exception as cleanup_err:
                print(f"Error cleaning up temp file {temp_file_path}: {cleanup_err}", file=sys.stderr)


@app.get("/api/evidence/history")
async def evidence_history_endpoint(limit: int = 25):
    try:
        history = await asyncio.to_thread(list_evidence_history, limit)
        return {
            "success": True,
            "count": len(history),
            "data": history,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to fetch evidence history: {str(e)}"}
        )


@app.get("/api/evidence/history/{session_id}")
async def evidence_session_endpoint(session_id: str):
    try:
        session = await asyncio.to_thread(get_evidence_session_by_id, session_id)
        if not session:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": f"Evidence session '{session_id}' not found."}
            )
        return {
            "success": True,
            "data": session,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to fetch evidence session: {str(e)}"}
        )


@app.post("/api/lexigraph/analyze")
async def lexigraph_analyze_endpoint(req: LexiGraphAgentQueryRequest):
    """
    LexiGraph Explorer endpoint that processes legal queries using the full
    hierarchical GraphRAG pipeline (lexigraph_agent.py).
    
    Expected JSON:
    {
        "query": "legal scenario description"
    }
    
    Returns:
    {
        "success": true/false,
        "data": {
            "pipeline_confidence": 0.85,
            "recommended_sections": [...],
            "supporting_cases": [...],
            "supporting_evidence": [...],
            "supporting_articles": [...],
            "supporting_principles": [...],
            "rejected_sections": [...]
        }
    }
    """
    if not req.query or not req.query.strip():
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Query string cannot be empty."}
        )
    
    try:
        # Run the LexiGraph hierarchical retrieval pipeline in threadpool
        result = await asyncio.to_thread(get_lexigraph_agent().process_query, req.query.strip(), debug=False)
        
        return {
            "success": True,
            "data": result,
            "agent": "LexiGraph Explorer"
        }
    except Exception as e:
        print(f"Error executing LexiGraph pipeline: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"LexiGraph pipeline error: {str(e)}"
            }
        )

# ── Orchestrator Endpoint ──────────────────────────────────────────────────────

# Lazy-init singleton for the compiled LangGraph graph.
# We do NOT build it at import time so the server can start even if optional
# services (Groq, Neo4j, Pinecone) are not yet reachable.
_orchestrator_graph = None


def _get_orchestrator_graph():
    """Return (and lazy-build) the compiled LangGraph orchestrator."""
    global _orchestrator_graph
    if _orchestrator_graph is None:
        from backend.agents.orchestrator.orchestrator_graph import build_graph
        _orchestrator_graph = build_graph()
    return _orchestrator_graph


class OrchestratorRunRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    role: Optional[str] = "prosecutor"
    mode: Optional[str] = "ai_vs_human"
    max_rounds: Optional[int] = 2
    human_argument: Optional[str] = None


class OrchestratorStreamRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    role: Optional[str] = "prosecutor"   # user's chosen role (prosecutor | defense)
    mode: Optional[str] = "ai_vs_human"  # ai_vs_human | ai_vs_ai
    max_rounds: Optional[int] = 2
    human_argument: Optional[str] = None


class OrchestratorSubmitArgumentRequest(BaseModel):
    session_id: str
    argument: str
    role: Optional[str] = None
    round_no: Optional[int] = None


# ── SSE Streaming Orchestrator Endpoint ────────────────────────────────────────
import queue as _queue_mod


@app.get("/api/orchestrator/roles", tags=["Orchestrator"])
async def orchestrator_roles():
    """Returns available modes and roles for frontend selection."""
    return {
        "modes": [
            {
                "id": "ai_vs_human",
                "name": "AI vs Human",
                "description": "Interactive moot court: You select a role (Prosecutor or Defense), AI takes opposing counsel, AI Judge presides.",
            },
            {
                "id": "ai_vs_ai",
                "name": "AI vs AI",
                "description": "Automated simulation between AI Public Prosecutor and AI Defense Counsel.",
            },
        ],
        "roles": [
            {
                "id": "prosecutor",
                "name": "Public Prosecutor",
                "description": "Represent the State: Establish statutory ingredients and prima facie guilt, oppose bail.",
                "ai_opponent": "Defense Counsel",
            },
            {
                "id": "defense",
                "name": "Defense Counsel",
                "description": "Represent the Accused: Challenge evidence, establish lack of ingredients, argue for bail/discharge.",
                "ai_opponent": "Public Prosecutor",
            },
        ],
    }


@app.post("/api/orchestrator/submit-argument", tags=["Orchestrator"])
async def orchestrator_submit_argument(req: OrchestratorSubmitArgumentRequest):
    """
    Submit a human legal argument from frontend to the active orchestrator pipeline.
    """
    sid = req.session_id.strip()
    text = (req.argument or "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"success": False, "message": "Argument cannot be empty."})

    from backend.agents.orchestrator.session_input import session_input_manager, normalize_role
    accepted = session_input_manager.submit_argument(
        session_id=sid,
        argument=text,
        role=normalize_role(req.role),
        round_no=req.round_no,
    )
    return {
        "success": True,
        "session_id": sid,
        "accepted": accepted,
        "message": "Argument submitted to orchestrator session.",
    }


@app.post("/api/orchestrator/stream", tags=["Orchestrator"])
async def orchestrator_stream(req: OrchestratorStreamRequest):
    """
    Stream the full orchestrator pipeline via Server-Sent Events (SSE).

    Supports AI vs Human role selection:
      - role="prosecutor": Human is Prosecutor, AI is Defense Counsel
      - role="defense": Human is Defense Counsel, AI is Public Prosecutor

    The pipeline runs in a background thread. Each on_event callback pushes
    to a thread-safe queue, and this async generator yields SSE frames.
    """
    query = (req.query or "").strip()
    from backend.agents.orchestrator.session_input import normalize_role, normalize_mode
    role = normalize_role(req.role) or "prosecutor"
    mode = normalize_mode(req.mode, role)
    sid = req.session_id or str(uuid.uuid4())[:8]

    if not query:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Field 'query' must not be empty."},
        )

    event_queue: _queue_mod.Queue = _queue_mod.Queue()

    def on_event(evt: dict):
        """Called synchronously from the orchestrator thread."""
        event_queue.put(evt)

    def _run():
        try:
            from backend.agents.orchestrator.orchestrator_graph import run_orchestrator
            run_orchestrator(
                case_id=query,
                session_id=sid,
                max_rounds=req.max_rounds or 2,
                on_event=on_event,
                user_role=role,
                mode=mode,
                human_argument=req.human_argument,
            )
        except Exception as exc:
            import traceback
            traceback.print_exc()
            event_queue.put({"type": "error", "message": str(exc), "recoverable": False})
        finally:
            event_queue.put(None)   # sentinel: stream is done

    # Fire the blocking orchestrator in a background thread
    import threading
    t = threading.Thread(target=_run, daemon=True)
    t.start()

    async def sse_generator():
        """Yield SSE frames until the sentinel (None) is received."""
        while True:
            try:
                evt = await asyncio.get_event_loop().run_in_executor(
                    None, event_queue.get, True, 180   # block up to 180s
                )
            except _queue_mod.Empty:
                # Heartbeat so the connection stays alive
                yield "event: heartbeat\ndata: {}\n\n"
                continue
            if evt is None:
                yield "event: done\ndata: {}\n\n"
                break
            yield f"data: {json.dumps(evt)}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/orchestrator/run", tags=["Orchestrator"])
async def orchestrator_run(req: OrchestratorRunRequest):
    """
    Run the full LangGraph Court Orchestrator for a given case query / FIR text synchronously.
    Supports AI vs Human role selection ('prosecutor' | 'defense').
    """
    query = (req.query or "").strip()
    if not query:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Field 'query' must not be empty."},
        )

    from backend.agents.orchestrator.session_input import normalize_role, normalize_mode
    role = normalize_role(req.role) or "prosecutor"
    mode = normalize_mode(req.mode, role)

    from backend.agents.evidence.evidence_analyzer import build_session_id
    session_id = req.session_id or build_session_id(query)

    try:
        from backend.agents.orchestrator.orchestrator_graph import run_orchestrator
        result: dict = await asyncio.to_thread(
            run_orchestrator,
            case_id=query,
            session_id=session_id,
            max_rounds=req.max_rounds or 2,
            user_role=role,
            mode=mode,
            human_argument=req.human_argument,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Orchestrator pipeline error: {str(e)}",
            },
        )

    verdict = result.get("judge_verdict") or {}

    return {
        "success":          True,
        "session_id":       result.get("session_id", session_id),
        "verdict":          verdict,
        "prosecution_args": result.get("prosecution_args", ""),
        "defense_args":     result.get("defense_args", ""),
        "judge_scores":     result.get("judge_scores", {}),
        "accused_history":  result.get("accused_history", []),
        "debate_round":     result.get("debate_round", 0),
        "structured_facts": result.get("structured_facts", {}),
        "relevant_laws":    result.get("relevant_laws", []),
    }


# ── Async Job-Based Orchestrator Endpoints ─────────────────────────────────────
# In-memory job store — suitable for single-process dev / Quick Tunnel usage.
# Thread-safe: mutated from background threads and read from the event loop.

import threading
from typing import Any

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _run_orchestrator_job(job_id: str, query: str) -> None:
    """
    Blocking function executed inside a worker thread.
    Runs the full LangGraph orchestrator and stores the result (or error)
    against *job_id* in the in-memory job store with stage progress tracking.
    """
    def on_stage_progress(stage_name: str, message: str = ""):
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["stage"] = stage_name
                _jobs[job_id]["message"] = message

    try:
        from backend.agents.orchestrator.orchestrator_graph import run_orchestrator
        from backend.agents.evidence.evidence_analyzer import build_session_id
        session_id = build_session_id(query)

        result: dict = run_orchestrator(query, session_id=session_id, on_stage=on_stage_progress)

        verdict = result.get("judge_verdict") or {}
        payload = {
            "success":          True,
            "session_id":       result.get("session_id", session_id),
            "verdict":          verdict,
            "prosecution_args": result.get("prosecution_args", ""),
            "defense_args":     result.get("defense_args", ""),
            "judge_scores":     result.get("judge_scores", {}),
            "accused_history":  result.get("accused_history", []),
            "debate_round":     result.get("debate_round", 0),
            "structured_facts": result.get("structured_facts", {}),
            "relevant_laws":    result.get("relevant_laws", []),
        }

        with _jobs_lock:
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["stage"] = "completed"
            _jobs[job_id]["message"] = "Orchestration completed successfully."
            _jobs[job_id]["result"] = payload

    except Exception as exc:
        import traceback
        traceback.print_exc()
        with _jobs_lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["stage"] = "failed"
            _jobs[job_id]["error"] = str(exc)


@app.post(
    "/api/orchestrator/start",
    status_code=202,
    tags=["Orchestrator"],
    summary="Start an async orchestrator job",
    response_description="Job accepted — poll /api/orchestrator/status/{job_id} for results.",
)
async def orchestrator_start(req: OrchestratorRunRequest):
    """
    Kick off the LangGraph Court Orchestrator **asynchronously**.

    Returns HTTP 202 with a `job_id` immediately.  The orchestrator
    runs in a background thread; poll `/api/orchestrator/status/{job_id}`
    to retrieve the result once it completes.

    Request JSON:
        { "query": "<case description or FIR text>" }

    Response JSON (HTTP 202):
        { "success": true, "job_id": "...", "status": "running", "stage": "started" }
    """
    query = (req.query or "").strip()
    if not query:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Field 'query' must not be empty."},
        )

    # Pre-validate that the graph can be built (fail fast before 202).
    try:
        _get_orchestrator_graph()
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "message": f"Orchestrator graph failed to initialise: {str(e)}",
            },
        )

    job_id = f"orch_{uuid.uuid4().hex}"

    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running",
            "stage": "started",
            "message": "Job received and queued.",
            "result": None,
            "error": None,
        }

    # Fire-and-forget: schedule the blocking work on the default thread-pool
    # executor.  asyncio.get_event_loop().run_in_executor does NOT block the
    # caller, so the 202 response is returned immediately.
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_orchestrator_job, job_id, query)

    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "job_id": job_id,
            "status": "running",
            "stage": "started",
        },
    )


@app.get(
    "/api/orchestrator/status/{job_id}",
    tags=["Orchestrator"],
    summary="Poll orchestrator job status",
)
async def orchestrator_status(job_id: str):
    """
    Check the status of a previously started orchestrator job.

    Possible statuses:
    - **running** — the pipeline is executing (stage field shows active step).
    - **completed** — finished successfully; full verdict and arguments in `result`.
    - **failed** — an error occurred; details in `error`.

    Returns HTTP 404 if `job_id` is unknown.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)

    if job is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": f"Job '{job_id}' not found."},
        )

    status = job["status"]

    if status == "completed":
        return {
            "success": True,
            "job_id": job_id,
            "status": "completed",
            "stage": "completed",
            "result": job["result"],
        }
    elif status == "failed":
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "job_id": job_id,
                "status": "failed",
                "stage": "failed",
                "error": job["error"],
            },
        )
    else:
        return {
            "success": True,
            "job_id": job_id,
            "status": "running",
            "stage": job.get("stage", "running"),
            "message": job.get("message", "Processing moot-court orchestration..."),
        }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 5001))

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        reload=False
    )