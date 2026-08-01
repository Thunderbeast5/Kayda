# LexiGraph Explorer Setup Guide

## Overview
The LexiGraph Explorer is now connected to the frontend! It uses the hierarchical GraphRAG pipeline from `backend/agents/lexigraph/lexigraph_agent.py`.

## What Was Done

### 1. Frontend Changes
- ✅ Created new page: `version1/interface/src/pages/LexiGraphExplorerPage.jsx`
- ✅ Updated homepage workspace utilities section to show "LAUNCH DEMO" for LexiGraph Explorer
- ✅ Added routing in `App.jsx` for the new page (`#/lexigraph-explorer`)
- ✅ Maintained consistent theme, fonts, and styling with Evidence Analyzer

### 2. Backend Changes
- ✅ Added new endpoint: `POST /api/lexigraph/analyze` in `backend/app.py`
- ✅ Initialized LexiGraphAgent in the backend
- ✅ Connected the full hierarchical retrieval pipeline

### 3. API Endpoint

**Endpoint:** `POST http://localhost:5001/api/lexigraph/analyze`

**Request Body:**
```json
{
  "query": "A woman alleged that a man induced her into a sexual relationship by falsely promising marriage despite already being married."
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "pipeline_confidence": 0.85,
    "recommended_sections": [
      {
        "act": "BNS",
        "section": "69",
        "title": "Sexual intercourse by employing deceitful means, etc.",
        "equivalent_section": {
          "act": "IPC",
          "section": "376",
          "mapping_verified": true
        },
        "confidence": 0.87,
        "applicability": "False promise of marriage with intent to engage in sexual intercourse.",
        "reason": "Statutory elements satisfied."
      }
    ],
    "supporting_cases": [...],
    "supporting_evidence": [...],
    "supporting_articles": [...],
    "supporting_principles": [...],
    "rejected_sections": [...]
  },
  "agent": "LexiGraph Explorer"
}
```

## How to Run

### Terminal 1: Backend Server
```powershell
cd c:\Users\Ajinkya\Desktop\MootCourt\backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 5001 --reload
```

### Terminal 2: Frontend Dev Server
```powershell
cd c:\Users\Ajinkya\Desktop\MootCourt\version1\interface
npm install
npm run dev
```

### Terminal 3: Test the Backend Directly (Optional)
```powershell
cd c:\Users\Ajinkya\Desktop\MootCourt\backend
python -m agents.lexigraph.lexigraph_agent "A woman alleged that a man induced her into a sexual relationship by falsely promising marriage."
```

## Access the Application

1. **Homepage:** http://localhost:5173/
2. **LexiGraph Explorer:** http://localhost:5173/#/lexigraph-explorer
3. **Evidence Analyzer:** http://localhost:5173/#/evidence-analyzer

## Features

### LexiGraph Explorer Page
- Natural language legal query input
- Sample query quick-launch buttons
- Multi-stage GraphRAG pipeline visualization
- Collapsible sections for:
  - Recommended Legal Sections (with IPC/BNS mappings)
  - Supporting Precedent Cases
  - Required Evidence Types
  - Constitutional Articles
  - Legal Principles
  - Rejected Sections (with reasons)
- Pipeline confidence score display
- Real-time loading states with progress indicators

### The Pipeline (8 Stages)
1. Query Understanding & Expansion
2. Embedding & Parallel Retrieval (Pinecone)
3. Candidate Filtering
4. Metadata Verification (Neo4j)
5. Graph Enrichment
6. Community Retrieval
7. Multi-Signal Scoring & Reranking
8. Legal Reasoning (LLM)

## Theme Consistency
The LexiGraph Explorer page matches the Evidence Analyzer theme:
- Background: `#FAF8F5` (cream/beige)
- Primary Text: `#2C1810` (dark brown)
- Accent Gold: `#D4AF37`
- Secondary Brown: `#8C5A3C`
- Font Heading: (same as rest of app)
- Font Body: (same as rest of app)
- Font Mono: (for code/sections)

## Troubleshooting

### Python 3.9 Compatibility Issue (FIXED)
The original error was due to Python 3.10+ union syntax (`Dict | None`). This has been fixed in:
- `backend/agents/lexigraph/services/verification_service.py`

### Backend Connection Error
If you see "Unable to reach LexiGraph backend service":
1. Make sure the backend is running on port 5001
2. Check the console for error messages
3. Verify Neo4j, Pinecone, and other services are configured in `.env`

### Missing Dependencies
```powershell
cd backend
pip install fastapi uvicorn python-multipart neo4j pinecone-client groq langchain openai
```

## Sample Test Queries

1. **Theft Case:**
   "My neighbor broke into my house and stole gold ornaments worth 5 lakhs and 50,000 cash."

2. **Dowry Death:**
   "A woman died within seven years of marriage due to harassment by her husband for dowry."

3. **Sexual Assault:**
   "A woman alleged that a man induced her into a sexual relationship by falsely promising marriage."

4. **Kidnapping:**
   "A child was kidnapped for ransom and later murdered."

5. **Rape Case:**
   "A woman was raped by a man known to her family."

## Next Steps

- Test the complete pipeline with various legal scenarios
- Verify Neo4j graph data is being retrieved correctly
- Check Pinecone vector similarity scores
- Validate LLM reasoning outputs
- Monitor pipeline performance and confidence scores
