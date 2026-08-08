# IPC/BNS Contamination Fix

## Problem Summary

The prosecutor output was showing **IPC section numbers mislabeled as BNS**:

```
378 BNS: Theft          ❌ WRONG - 378 is IPC, BNS theft is §303
503 BNS: Criminal Intimidation  ❌ WRONG - 503 is IPC, BNS is §351  
506 BNS: Criminal Intimidation  ❌ WRONG - 506 is IPC, BNS is §351
```

Additionally, **Extortion was failing to retrieve any sections** despite being correctly identified as the primary crime in Stage 1.

## Root Cause

### Issue #1: LLM Relabeling in Stage 2

The Stage 2 prompt contained this instruction:

```
LEGAL REGIME RULE: Always use the statute indicated by the legal_regime field.
   - If legal_regime contains "BNS" or "BNSS" -> use BNS sections.
   - If legal_regime contains "IPC" or "CrPC" -> use IPC sections.
```

**The Problem:**

1. Prosecutor calls `analyze_case()` with `legal_regime="BNS_2023"` (default)
2. Stage 2 receives `legal_regime="BNS + BNSS"`
3. Prefilter correctly returns IPC sections from database (378 IPC, 503 IPC, 506 IPC)
4. Prefilter JSON has `{"statute": "IPC", "section_number": "378", ...}`
5. **LLM sees the prompt instruction and relabels everything as BNS**
6. LLM outputs `{"statute": "BNS", "section_number": "378", ...}` ❌

**Why This Is Wrong:**

- The `statute` field is a **database identifier**, not a transformation target
- Section 378 exists ONLY in IPC - there is no "378 BNS"
- BNS theft is Section 303, completely different numbering
- The prompt was conflating "which statute to search" with "how to label results"

### Issue #2: Extortion Retrieval Failure

The extortion retrieval failure has multiple causes:

1. **Concept-to-Keyword Bridge Missing:** The prefilter has a `_CONCEPT_KEYWORD_BRIDGE` dict (line ~1910 in `classifier_prefilter.py`) that maps legal concepts to trigger keywords:
   ```python
   "criminal intimidation": ["threat", "threatened", "intimidat", "warning"],
   "theft": ["theft", "stolen", "stole", "took away"],
   ```
   But **"extortion" was NOT in the bridge**, so when Stage 1 returned "Extortion" as a concept, the prefilter couldn't expand it to the correct triggers.

2. **Database Coverage:** Need to verify that BNS §308 (Extortion) and IPC 383-384 (Extortion) are in the sections database.

3. **Keyword Matching in Prosecutor:** The prosecutor's post-distribution logic uses keyword matching, but the extortion keywords might be incomplete.

## The Fix

### Fix #1: Update Stage 2 Prompt

**File:** `backend/lexigraphbe/prompts.py`, line ~385

**Changed from:**
```
LEGAL REGIME RULE: Always use the statute indicated by the legal_regime field.
   - If legal_regime contains "BNS" or "BNSS" -> use BNS sections.
   - If legal_regime contains "IPC" or "CrPC" -> use IPC sections.
```

**Changed to:**
```
**CRITICAL STATUTE LABELING RULE:**
   - ALWAYS preserve the "statute" field from the Pre-Filtered Statutory Candidate Entries EXACTLY AS PROVIDED.
   - The prefilter has already determined whether each section is IPC or BNS based on the database.
   - DO NOT relabel IPC sections as BNS or vice versa based on legal_regime.
   - If legal_regime is "BNS + BNSS" but the prefilter returns IPC sections (e.g. 378 IPC, 503 IPC), keep them labeled as IPC.
   - If legal_regime is "IPC + CrPC" but the prefilter returns BNS sections, keep them labeled as BNS.
   - The statute field is an identifier from the statutory database, NOT a transformation target.
```

### Fix #2: Add Extortion to Concept-Keyword Bridge

**File:** `backend/lexigraphbe/classifier_prefilter.py`, line ~1910

**Add:**
```python
"extortion": ["extortion", "extorted", "blackmail", "threatened", "demanded money", "putting person in fear"],
```

This ensures when Stage 1 identifies "Extortion" as a concept, the prefilter expands it to the correct factual triggers that match Sections 383-384 IPC / 308-309 BNS.

### Fix #3: Update Prosecutor Keyword Matching

**File:** `backend/prosecutor/prosecutor.py`, line ~460

**Current:**
```python
crime_keywords = {
    "criminal intimidation": ["criminal intimidation", "threat", "alarm"],
    "physical assault": ["assault", "hurt", "causing hurt", "injury"],
    "extortion": ["extortion", "putting person in fear"],
}
```

**This is already present**, so no change needed here.

## Expected Behavior After Fix

### Stage 2 Output (Before Fix):
```json
{
  "mappings": [
    {
      "concept": "Criminal Intimidation",
      "primary_candidate_sections": [
        {
          "section_number": "506",
          "statute": "BNS",  ❌ WRONG
          "title": "Criminal Intimidation"
        }
      ]
    }
  ]
}
```

### Stage 2 Output (After Fix):
```json
{
  "mappings": [
    {
      "concept": "Criminal Intimidation",
      "primary_candidate_sections": [
        {
          "section_number": "506",
          "statute": "IPC",  ✅ CORRECT
          "title": "Criminal Intimidation"
        },
        {
          "section_number": "351",
          "statute": "BNS",  ✅ CORRECT (if in database)
          "title": "Criminal Intimidation"
        }
      ]
    },
    {
      "concept": "Extortion",
      "primary_candidate_sections": [
        {
          "section_number": "383",
          "statute": "IPC",
          "title": "Extortion"
        },
        {
          "section_number": "384",
          "statute": "IPC",
          "title": "Extortion by Putting Person in Fear"
        },
        {
          "section_number": "308",
          "statute": "BNS",
          "title": "Extortion"
        }
      ]
    }
  ]
}
```

### Prosecutor Output (After Fix):
```
[ProsecutorAgent] Total sections retrieved: 8

  → Criminal Intimidation: 2 sections (506 IPC, 351 BNS)
  → Physical Assault: 2 sections (323 IPC, 115 BNS)
  → Extortion: 3 sections (383 IPC, 384 IPC, 308 BNS)
  → Theft: 1 section (378 IPC)
```

## Why the Phantom IPC 383 Appeared in the Argument

You mentioned that IPC 383 (Extortion) appeared in the generated argument despite not being retrieved. This happens because:

1. **LLM Hallucination:** The argument generation prompt might have included the case facts, which mention "threatened to publicly accuse" and "demanded ₹2 lakh". The LLM recognized this as extortion and **hallucinated** IPC 383 even though it wasn't in the retrieved sections.

2. **Prompt Leakage:** The Stage 2 prompt includes example offence patterns like:
   ```
   B. EXTORTION / CRIMINAL INTIMIDATION CASES:
      - Threat to accuse of offence/crime to extract money/property: 383-384 IPC (Extortion)
   ```
   
   If the argument generation reads the case facts and recognizes the extortion pattern, it might reference these section numbers from the prompt context.

**Fix:** Ensure the argument generation prompt ONLY uses the `retrieved_sections` list and does NOT allow the LLM to introduce new sections.

## Testing Recommendations

1. **Run with IPC regime:**
   ```python
   analysis = prosecutor.analyze_case(case_file, legal_regime="IPC_1860")
   ```
   Expected: All sections labeled as IPC

2. **Run with BNS regime:**
   ```python
   analysis = prosecutor.analyze_case(case_file, legal_regime="BNS_2023")
   ```
   Expected: BNS sections if available in database, IPC sections if not (but correctly labeled as IPC)

3. **Check extortion retrieval:**
   ```python
   analysis = prosecutor.analyze_case(case_file)
   extortion_crime = next((c for c in analysis.identified_crimes if "extortion" in c.crime_name.lower()), None)
   print(f"Extortion sections: {len(extortion_crime.retrieved_sections)}")
   ```
   Expected: At least 2-3 sections (383 IPC, 384 IPC, and/or 308 BNS)

## Files Modified

1. **`backend/lexigraphbe/prompts.py`**
   - Updated STAGE2_MAPPING_SYSTEM_PROMPT to prevent statute relabeling
   - Clarified that statute field is a database identifier, not a transformation target

2. **Next:** `backend/lexigraphbe/classifier_prefilter.py` (TODO)
   - Add extortion to `_CONCEPT_KEYWORD_BRIDGE` dict

## Technical Notes

### Database Schema

The sections database has this structure:
```python
{
    "identifier": "IPC_378",
    "statute": "IPC",  # <-- This is the authoritative label
    "section_number": "378",
    "title": "Theft",
    ...
}
```

The `statute` field is populated from the CSV files:
- `data/new/ipc_sections.csv` → all sections have `statute="IPC"`
- `data/new/bns_sections_clean.csv` → all sections have `statute="BNS"`

### Prefilter Behavior

The prefilter's `shortlist_candidates_for_query()` method:

1. Filters by `regime_filter` if requested:
   ```python
   if regime_filter and record["statute"] != regime_filter:
       continue  # Skip sections from other statute
   ```

2. Returns `CandidateSectionMatch` objects with `statute=record["statute"]`

3. **Never modifies the statute label** - it's pass-through from the database

### Stage 2 LLM Behavior

The LLM in Stage 2 was **overriding** the statute labels from the prefilter because the prompt said:
> "Always use the statute indicated by the legal_regime field"

This is now fixed to say:
> "ALWAYS preserve the 'statute' field from the Pre-Filtered Statutory Candidate Entries EXACTLY AS PROVIDED"

## Additional Debugging

If sections are still mislabeled after this fix, check:

1. **Prefilter output:** Add debug logging in `stage2_mapping_agent.py` line ~107:
   ```python
   print(f"[Stage2] Prefilter returned: {[(m.section_number, m.statute) for m in prefiltered_matches]}")
   ```

2. **LLM response:** Check the raw LLM JSON before Pydantic validation:
   ```python
   print(f"[Stage2] LLM raw response: {response_text[:1000]}")
   ```

3. **Database content:** Verify the sections exist:
   ```python
   from lexigraphbe.statute_repository import StatuteRepository
   repo = StatuteRepository.get_instance()
   for sec in repo.get_sections_db():
       if sec["section_number"] in ["378", "383", "384", "506", "303", "308", "351"]:
           print(f"{sec['section_number']} {sec['statute']}: {sec['title']}")
   ```
