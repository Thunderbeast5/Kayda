# LexiGraph Explorer Diagnostic Checklist

## Issue: "Output is different from lexigraph_agent.py"

Let's verify the connection step by step:

## ✅ Step 1: Verify Backend Code Connection

### Check 1: app.py imports
```python
# In backend/app.py line 32:
from backend.agents.lexigraph.lexigraph_agent import LexiGraphAgent

# In backend/app.py line 58:
lexigraph_agent = LexiGraphAgent()
```
**Status:** ✅ Confirmed - LexiGraphAgent is imported and initialized

### Check 2: Endpoint definition
```python
# In backend/app.py line 187:
@app.post("/api/lexigraph/analyze")
async def lexigraph_analyze_endpoint(req: LexiGraphQueryRequest):
    # ...
    result = await asyncio.to_thread(lexigraph_agent.process_query, req.query.strip(), debug=False)
    return {
        "success": True,
        "data": result,
        "agent": "LexiGraph Explorer"
    }
```
**Status:** ✅ Confirmed - Endpoint calls `lexigraph_agent.process_query()`

### Check 3: Frontend API call
```javascript
// In LexiGraphExplorerPage.jsx line 77:
const response = await fetch(`${apiUrl}/api/lexigraph/analyze`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ query }),
});
```
**Status:** ✅ Confirmed - Frontend calls correct endpoint

## ✅ Step 2: Verify Backend is Running

### Test 1: Check if process is running
```powershell
# Check if uvicorn is running on port 5001
netstat -ano | findstr :5001
```

### Test 2: Test health endpoint
```powershell
curl http://localhost:5001/api/cypher/health
```
**Expected:** Should return JSON with "status": "online"

### Test 3: Test LexiGraph endpoint directly
```powershell
cd c:\Users\Ajinkya\Desktop\MootCourt
python test_lexigraph_endpoint.py
```
**Expected:** Should return success with recommended_sections

## ✅ Step 3: Compare Outputs

### Expected Output from lexigraph_agent.py:
```json
{
  "pipeline_confidence": 0.87,
  "recommended_sections": [
    {
      "act": "BNS",
      "section": "69",
      "title": "Sexual intercourse by employing deceitful means",
      "equivalent_section": {
        "act": "IPC",
        "section": "376",
        "mapping_verified": true
      },
      "confidence": 0.89,
      "applicability": "...",
      "reason": "..."
    }
  ],
  "supporting_cases": [...],
  "supporting_evidence": [...],
  "supporting_articles": [...],
  "supporting_principles": [...],
  "rejected_sections": [...]
}
```

### What Frontend Expects:
```javascript
result.pipeline_confidence      // Number
result.recommended_sections     // Array
result.supporting_cases         // Array
result.supporting_evidence      // Array
result.supporting_articles      // Array
result.supporting_principles    // Array
result.rejected_sections        // Array
```

## 🔍 Step 4: Identify the Difference

### Question 1: Is the backend actually using lexigraph_agent.py?
**How to verify:**
1. Add a print statement in lexigraph_agent.py at the start of `process_query()`
2. Restart backend
3. Make a query from frontend
4. Check backend console logs for the print statement

### Question 2: Are there TWO different endpoints being called?
**Possible confusion:**
- `/api/cypher/query` → Uses Text2Cypher pipeline (different agent!)
- `/api/lexigraph/analyze` → Uses LexiGraphAgent pipeline ✅

**Frontend should call:** `/api/lexigraph/analyze`

### Question 3: Is there a cached old version?
**How to verify:**
1. Hard refresh browser (Ctrl+Shift+R)
2. Check browser DevTools Network tab
3. Verify URL being called is `/api/lexigraph/analyze`

## 🛠️ Step 5: Debug Steps

### Debug Step 1: Add logging to lexigraph_agent.py
```python
# Add at the start of process_query() method around line 128:
def process_query(self, query: str, debug: bool = False) -> Dict[str, Any]:
    print("=" * 100)
    print("LEXIGRAPH AGENT PROCESS_QUERY CALLED FROM API")
    print(f"Query: {query}")
    print("=" * 100)
    # ... rest of method
```

### Debug Step 2: Check backend logs
When you make a request from frontend, you should see:
```
[LexiGraphAgent] Step 1: Query Understanding & Expansion for: '...'
Original query: ...
Expanded queries (Grounded): ...
[LexiGraphAgent] Step 2: Embedding & Parallel Retrieval (Top 50)...
[LexiGraphAgent] Step 3: Candidate Filtering (Truncate to Top 20)...
[LexiGraphAgent] Step 4: Metadata Verification & Successor Mapping...
[LexiGraphAgent] Step 5: Graph Enrichment (Top 10)...
[LexiGraphAgent] Step 6: Community Retrieval (Top 5)...
[LexiGraphAgent] Step 7: Multi-Signal Scoring & Reranking...
[LexiGraphAgent] Step 8: Legal Reasoning Service...
```

### Debug Step 3: Check frontend response
Open browser DevTools → Network tab → Find the request to `/api/lexigraph/analyze`
- Check Response tab
- Verify the JSON structure matches expected output

## 📋 Common Issues & Solutions

### Issue 1: Wrong endpoint being called
**Solution:** Check frontend code calls `/api/lexigraph/analyze` not `/api/cypher/query`

### Issue 2: Backend not restarted after changes
**Solution:** 
```powershell
# Stop backend (Ctrl+C)
# Restart backend
cd backend
uvicorn app:app --host 0.0.0.0 --port 5001 --reload
```

### Issue 3: Import errors in backend
**Solution:** Check backend console for Python import errors

### Issue 4: Neo4j/Pinecone not configured
**Solution:** Check `.env` file has all required API keys:
```env
NEO4J_URI=...
NEO4J_USER=...
NEO4J_PASSWORD=...
PINECONE_API_KEY=...
PINECONE_ENVIRONMENT=...
OPENAI_API_KEY=...
GROQ_API_KEY=...
```

### Issue 5: Different data structure
**Symptom:** Frontend displays data but in wrong sections
**Solution:** Check if API response has different field names

## 🎯 Quick Verification Commands

### Terminal 1: Start Backend
```powershell
cd c:\Users\Ajinkya\Desktop\MootCourt\backend
uvicorn app:app --host 0.0.0.0 --port 5001 --reload
```

### Terminal 2: Test Endpoint
```powershell
cd c:\Users\Ajinkya\Desktop\MootCourt
python test_lexigraph_endpoint.py
```

### Terminal 3: Start Frontend
```powershell
cd c:\Users\Ajinkya\Desktop\MootCourt\version1\interface
npm run dev
```

## 📞 What to Report

If the issue persists, provide:
1. **Backend console logs** (copy the 8-step output)
2. **Frontend browser console** (any errors?)
3. **Network tab response** (from DevTools)
4. **Which endpoint is being called** (from Network tab)
5. **Expected vs Actual output** (side-by-side comparison)

---

**Last Updated:** January 2025
**File:** DIAGNOSTIC_CHECKLIST.md
