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
    IMAGE_EXTENSIONS,
)
from backend.agents.lexigraph.cypher.legal_text2cypher.agents.pipeline import run_pipeline
from backend.agents.lexigraph.cypher.legal_text2cypher.config.settings import get_settings
from backend.agents.lexigraph.lexigraph_agent import LexiGraphAgent

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

# Initialize LexiGraph Agent
lexigraph_agent = LexiGraphAgent()


class CypherQueryRequest(BaseModel):
    query: str


class LexiGraphQueryRequest(BaseModel):
    query: str


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
@app.post("/api/lexigraph/query")
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


@app.post("/api/lexigraph/analyze")
async def lexigraph_analyze_endpoint(req: LexiGraphQueryRequest):
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
        result = await asyncio.to_thread(lexigraph_agent.process_query, req.query.strip(), debug=False)
        
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=5001, reload=True)

