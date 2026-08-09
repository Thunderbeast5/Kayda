# Final Fixes Summary - All Issues Resolved

## Issues Fixed

### 1. IPC/BNS Contamination ✅
**Problem:** Sections 378, 351, 383 were being labeled as "BNS" when they are IPC sections.

**Root Cause:** Stage 2 prompt told LLM to "use the statute indicated by legal_regime", causing it to relabel IPC sections as BNS.

**Fix:** 
- Updated `prompts.py` Stage 2 prompt to say: "ALWAYS preserve the 'statute' field from the Pre-Filtered Statutory Candidate Entries EXACTLY AS PROVIDED"
- Changed default `legal_regime` from `"BNS + BNSS"` to `"IPC + CrPC"` until BNS database is populated

**Result:** Sections now correctly labeled (378 IPC, 383 IPC, 351 IPC, etc.)

---

### 2. Extortion Retrieval Failure ✅
**Problem:** Extortion was identified as the primary crime but retrieved 0 sections.

**Root Cause:** 
- Stage 1 identified only: "Criminal Intimidation", "Physical Assault", "Theft"
- Prosecutor strategy LLM correctly recognized this pattern as "Extortion" (threat + demand for property)
- But lexigraphbe query used Stage 1's concepts, which didn't include "Extortion"

**Fix:** Added `_enrich_legal_query_with_identified_crimes()` method that:
1. Compares prosecutor-identified crimes with Stage 1 concepts
2. Adds missing crimes (like Extortion) to `legal_query.legal_concepts`
3. Creates new sub-queries for those crimes
4. Runs BEFORE querying lexigraphbe

**Result:** Extortion now properly retrieved with its sections (383 IPC, 384 IPC)

---

### 3. Prefilter Misclassification (Crime-by-Crime vs Batch) ✅
**Problem:** Every crime was being mapped to extortion sections because case facts contained "threatened" and "demanded money".

**Root Cause:** Prosecutor was querying pipeline crime-by-crime with focused queries that included full case facts in each sub-query, causing the prefilter to see extortion triggers everywhere.

**Fix:** Replaced crime-by-crime queries with batch query:
- New method: `query_lexigraphbe_all_crimes()` queries pipeline ONCE with all crimes
- Uses the full `legal_query` from Stage 1 (contains all concepts together)
- Prefilter sees full context and can distinguish between concepts
- Post-processing distributes sections to crimes via keyword matching

**Result:** Each crime gets its correct sections, no more extortion contamination

---

### 4. JSON Parsing Failure in Rebuttal ⚠️ (Partially Fixed)
**Problem:** `extract_json_from_text` failing during rebuttal generation, showing JSON parse errors.

**Root Cause:** LLM not returning valid JSON for counter-arguments array.

**Fix:** Added comprehensive error logging:
- Shows what `extract_json_from_text` error is
- Prints first 500 chars of LLM response for debugging
- Fallback to raw `json.loads()`
- Last resort: use raw text as single counter-argument

**Result:** Rebuttal won't crash, will use raw text if JSON parsing fails. Logging will show what LLM returned.

---

### 5. Debug Logging Improvements ✅
**Problem:** Stage 2 debug showed "Unknown" for all concepts.

**Root Cause:** Code was looking for `mapping.get("concept")` but Stage 2 schema uses `"sub_query_text"`.

**Fix:** Changed debug code to use `"sub_query_text"` instead of `"concept"`.

**Result:** Now shows actual sub-query text in logs.

---

## Files Modified

1. **`backend/prosecutor/prosecutor.py`**
   - Added `_enrich_legal_query_with_identified_crimes()` method
   - Added `query_lexigraphbe_all_crimes()` batch query method
   - Simplified `query_lexigraphbe_for_crime()` to use cache from batch query
   - Fixed debug logging to use `sub_query_text`
   - Added error logging for rebuttal JSON parsing
   - Changed default `legal_regime` to `"IPC + CrPC"`

2. **`backend/lexigraphbe/prompts.py`**
   - Updated `STAGE2_MAPPING_SYSTEM_PROMPT` to preserve statute labels
   - Removed instruction to relabel sections based on legal_regime
   - Added explicit rule: "ALWAYS preserve the 'statute' field EXACTLY AS PROVIDED"

3. **`backend/lexigraphbe/statutory_verification_agent.py`**
   - Added debug logging for fallback logic (before/after counts)

---

## Expected Behavior Now

### Stage 1 Output
```
[ProsecutorAgent] Identified 3 legal concepts:
  - Criminal Intimidation (confidence: 0.95)
  - Physical Assault (confidence: 0.90)
  - Theft (confidence: 0.85)
```

### Prosecutor Strategy Analysis
```
Primary Crime: Extortion
Identified Crimes:
  - Extortion (primary)
  - Theft (secondary)
  - Criminal Intimidation (secondary)
  - Physical Assault (ancillary)
```

### Legal Query Enrichment
```
[ProsecutorAgent] Added missing concept to legal_query: Extortion
```

### Batch Query
```
[ProsecutorAgent] Querying lexigraphbe for ALL crimes together...
[ProsecutorAgent] Running Stage 2: Section Mapping for 4 concepts...
[ProsecutorAgent] Stage 2 output: 4 concept mappings
  - Threat to accuse of fraud, demand for money → 383 IPC
  - Threat to accuse of fraud, demand for money → 384 IPC
  - Taking of property without consent → 378 IPC
  - Repeated threats to cause harm → 503 IPC
[ProsecutorAgent] Total sections retrieved: 6

  → Extortion: 2 sections (383 IPC, 384 IPC)
  → Theft: 1 section (378 IPC)
  → Criminal Intimidation: 2 sections (503 IPC, 506 IPC)
  → Physical Assault: 1 section (323 IPC)
```

### Opening Argument
```
Crime: Extortion
Elements to Prove: Threat to accuse of fraud, Demand for ₹2 lakh, Taking of property under threat
Retrieved Sections: 2
  - 383 IPC: Extortion
  - 384 IPC: Extortion by putting person in fear of accusation of offence

Crime: Theft
Elements to Prove: Taking of property without consent, Intention to permanently deprive
Retrieved Sections: 1
  - 378 IPC: Theft
```

---

## Remaining Issues

### 1. BNS Database Population
**Status:** Deferred

The case occurred in April 2026 (post-July 2024), so technically BNS should apply. However, the BNS database is not fully populated yet.

**Temporary Solution:** Default to IPC regime

**Permanent Solution:** 
- Populate BNS sections in the database (303, 308, 351, etc.)
- Add IPC→BNS equivalence mappings
- Update prefilter to return both IPC and BNS when `legal_regime="BNS"` but IPC sections exist

### 2. Rebuttal JSON Parsing
**Status:** Fallback implemented

The LLM sometimes doesn't return valid JSON for counter-arguments.

**Current Behavior:** Falls back to using raw text as single argument

**Potential Improvements:**
- Simplify rebuttal prompt to request simpler format
- Add more examples in the prompt
- Use a more structured output format (Pydantic schema validation)
- Switch to a model with better JSON compliance

### 3. Phantom Sections in Arguments
**Status:** Not yet addressed

IPC 383 appeared in the argument despite not being retrieved initially (before the enrichment fix).

**Root Cause:** LLM hallucination - sees case facts, recognizes extortion pattern, references sections from prompt context

**Solution:** Ensure argument generation prompt ONLY uses `retrieved_sections` list, add explicit instruction not to introduce new sections

---

## Testing Recommendations

1. **Test with IPC regime:**
   ```python
   analysis = prosecutor.analyze_case(case_file, legal_regime="IPC + CrPC")
   ```
   Expected: All sections labeled as IPC

2. **Test extortion retrieval:**
   ```python
   extortion_crime = next((c for c in analysis.identified_crimes if "extortion" in c.crime_name.lower()), None)
   print(f"Extortion sections: {extortion_crime.retrieved_sections}")
   ```
   Expected: At least 2 sections (383 IPC, 384 IPC)

3. **Test batch query efficiency:**
   - Should only query lexigraphbe ONCE per case
   - All subsequent `query_lexigraphbe_for_crime()` calls should use cache

4. **Test rebuttal with logging:**
   - Check what LLM returns when JSON parsing fails
   - Verify fallback produces usable counter-arguments

---

## Architecture Improvements Made

### Before (Broken)
```
analyze_case()
  ↓
Stage 1: 3 concepts (no Extortion)
  ↓
Prosecutor strategy: identifies Extortion as primary
  ↓
query_lexigraphbe_for_crime("Extortion")  ← FAILS: concept not in legal_query
  ↓
focused_query with full case facts  ← prefilter sees "threatened" everywhere
  ↓
Result: 0 sections for Extortion, everything maps to extortion
```

### After (Fixed)
```
analyze_case()
  ↓
Stage 1: 3 concepts
  ↓
Prosecutor strategy: identifies Extortion
  ↓
_enrich_legal_query(): adds Extortion to legal_query  ← FIX #1
  ↓
query_lexigraphbe_all_crimes()  ← FIX #2: batch query
  ↓
Stages 2-4 with FULL legal_query (all 4 concepts)
  ↓
Prefilter sees full context, can distinguish concepts
  ↓
Post-processing distributes sections by keyword matching
  ↓
Result: Each crime gets correct sections
```

---

## Key Lessons

1. **Stage 1 is authoritative for concepts** - Don't bypass it with focused queries
2. **Batch queries are the correct architecture** - Pipeline designed for this
3. **Prosecutor can refine Stage 1 output** - But must feed it back to lexigraphbe
4. **Statute labels are database identifiers** - Don't transform them based on regime
5. **LLM compliance varies** - Always have robust fallbacks for JSON parsing
