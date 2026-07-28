import os
import sys
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

from evidence.evidence_analyzer import (
    build_session_id,
    extract_text,
    extract_facts,
    store_to_firestore,
    store_to_pinecone,
    _get_firestore_client,
    IMAGE_EXTENSIONS,
)
from backend.agents.lexigraph.cypher.legal_text2cypher.agents.pipeline import run_pipeline
from backend.agents.lexigraph.cypher.legal_text2cypher.config.settings import get_settings

lexigraph_agent_instance = None


def get_lexigraph_agent():
    global lexigraph_agent_instance
    if lexigraph_agent_instance is None:
        from backend.agents.lexigraph.lexigraph_agent import LexiGraphAgent
        lexigraph_agent_instance = LexiGraphAgent()
    return lexigraph_agent_instance

app = FastAPI(title="MootCourt Legal Intelligence & Evidence API")

# Enable CORS for localhost and 127.0.0.1 on various ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = backend_dir / "temp_uploads"
TEMP_DIR.mkdir(exist_ok=True)


class CypherQueryRequest(BaseModel):
    query: str


class LexiGraphAgentQueryRequest(BaseModel):
    query: str
    debug: bool = False


@app.get("/api/cypher/health")
async def cypher_health():
    try:
        cfg = get_settings()
        return {
            "status": "online",
            "neo4j_uri": cfg.neo4j_uri,
            "model": cfg.groq_model,
        }
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


@app.post("/api/cypher/query")
@app.post("/api/query")
async def cypher_query_endpoint(req: CypherQueryRequest):
    if not req.query or not req.query.strip():
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Query string cannot be empty."}
        )
    
    try:
        # Run synchronous Text2Cypher multi-stage pipeline in threadpool
        result = await asyncio.to_thread(run_pipeline, req.query.strip())
        
        # Dump model to json-serializable dict
        data = result.model_dump(mode="json")
        
        intent_val = result.intent.value if hasattr(result.intent, "value") else str(result.intent)
        
        return {
            "success": True,
            "data": data,
            "intent": intent_val,
            "answer": result.answer,
            "response": result.answer,
            "agent": "LexiGraph Cypher",
        }
    except Exception as e:
        print(f"Error executing Text2Cypher pipeline: {str(e)}", file=sys.stderr)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Legal Text2Cypher pipeline error: {str(e)}"
            }
        )


import json
from datetime import datetime, timezone

HISTORY_FILE = TEMP_DIR / "lexigraph_history.json"


def _get_firestore_db():
    try:
        return _get_firestore_client()
    except Exception as e:
        print(f"[Firebase] Firestore client unavailable from evidence_analyzer: {e}", file=sys.stderr)
        return None


def save_lexigraph_query_session(query_id: str, query: str, result: dict) -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    session_data = {
        "query_id": query_id,
        "query": query,
        "created_at": created_at,
        "pipeline_confidence": result.get("pipeline_confidence", 0.0),
        "primary_intent": result.get("community", {}).get("primary_intent") if isinstance(result.get("community"), dict) else "general_offences",
        "recommended_count": len(result.get("recommended_sections") or []),
        "precedents_count": len(result.get("supporting_cases") or []) + len(result.get("similar_cases") or []),
        "result": result,
    }

    # 1. Save to Firebase Firestore if client available
    firestore_saved = False
    try:
        db = _get_firestore_db()
        if db:
            db.collection("lexigraph_queries").document(query_id).set(session_data)
            firestore_saved = True
            print(f"[Firebase] Saved LexiGraph query '{query_id}' to Firestore collection 'lexigraph_queries'")
    except Exception as e:
        print(f"[Firebase] Firestore set error: {e}", file=sys.stderr)

    # 2. Local JSON fallback file persistence (always updated)
    try:
        history = []
        if HISTORY_FILE.exists():
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                try:
                    history = json.load(f)
                except Exception:
                    history = []
        # Prepend latest
        history.insert(0, session_data)
        # Cap local storage at 100 entries
        history = history[:100]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception as local_err:
        print(f"[Firebase] Local history file write error: {local_err}", file=sys.stderr)

    session_data["saved_to_firestore"] = firestore_saved
    return session_data


def list_lexigraph_history(limit: int = 50) -> list:
    sessions = []
    
    # Try Firestore first
    try:
        db = _get_firestore_db()
        if db:
            docs = db.collection("lexigraph_queries").order_by("created_at", direction="DESCENDING").limit(limit).stream()
            for doc in docs:
                data = doc.to_dict()
                sessions.append({
                    "query_id": data.get("query_id") or doc.id,
                    "query": data.get("query", ""),
                    "created_at": data.get("created_at", ""),
                    "pipeline_confidence": data.get("pipeline_confidence", 0.0),
                    "primary_intent": data.get("primary_intent", "general_offences"),
                    "recommended_count": data.get("recommended_count", 0),
                    "precedents_count": data.get("precedents_count", 0),
                    "source": "firestore"
                })
            if sessions:
                return sessions
    except Exception as e:
        print(f"[Firebase] Could not fetch history from Firestore: {e}", file=sys.stderr)

    # Fallback to local JSON store
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
                for item in history[:limit]:
                    sessions.append({
                        "query_id": item.get("query_id", ""),
                        "query": item.get("query", ""),
                        "created_at": item.get("created_at", ""),
                        "pipeline_confidence": item.get("pipeline_confidence", 0.0),
                        "primary_intent": item.get("primary_intent", "general_offences"),
                        "recommended_count": item.get("recommended_count", 0),
                        "precedents_count": item.get("precedents_count", 0),
                        "source": "local"
                    })
        except Exception as local_err:
            print(f"[Firebase] Error reading local history: {local_err}", file=sys.stderr)

    return sessions


def get_lexigraph_session_by_id(query_id: str) -> dict:
    # Try Firestore
    try:
        db = _get_firestore_db()
        if db:
            doc = db.collection("lexigraph_queries").document(query_id).get()
            if doc.exists:
                return doc.to_dict()
    except Exception as e:
        print(f"[Firebase] Could not fetch doc '{query_id}' from Firestore: {e}", file=sys.stderr)

    # Fallback to local JSON
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
                for item in history:
                    if item.get("query_id") == query_id:
                        return item
        except Exception as local_err:
            print(f"[Firebase] Local history lookup error: {local_err}", file=sys.stderr)

    return None


@app.post("/api/lexigraph-agent/query")
@app.post("/api/lexigraph/agent/query")
@app.post("/api/lexigraph/query")
async def lexigraph_agent_query_endpoint(req: LexiGraphAgentQueryRequest):
    if not req.query or not req.query.strip():
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Query string cannot be empty."}
        )
    try:
        agent = get_lexigraph_agent()
        result = await asyncio.to_thread(agent.process_query, req.query.strip(), req.debug)
        
        query_id = f"lexi_{uuid.uuid4().hex[:12]}"
        saved_session = await asyncio.to_thread(save_lexigraph_query_session, query_id, req.query.strip(), result)

        return {
            "success": True,
            "query_id": query_id,
            "created_at": saved_session.get("created_at"),
            "saved_to_firestore": saved_session.get("saved_to_firestore", False),
            "data": result,
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
        
        # Run extraction pipeline
        raw_text = extract_text(str(temp_file_path))
        facts = extract_facts(raw_text)
        
        # Save to Firestore & Pinecone
        store_to_firestore(session_id, raw_text, facts)
        store_to_pinecone(session_id, facts)
        
        return {
            "success": True,
            "data": {
                "rawText": raw_text,
                "facts": facts
            }
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=5001, reload=True)

