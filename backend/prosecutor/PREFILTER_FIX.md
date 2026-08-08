# Prefilter Misclassification Fix - Architecture Correction

## Problem Statement

When querying for "Criminal Intimidation" and "Physical Assault", the prosecutor was getting "Extortion" sections instead. Every crime was being misclassified as extortion because the **case facts contained extortion trigger keywords** ("threatened", "transfer money") that dominated the prefilter.

## Root Cause

### The Broken Architecture (Crime-by-Crime Queries)

The original `query_lexigraphbe_for_crime()` method created a **focused query for each crime individually**:

```python
# BROKEN: One crime at a time
for crime in crimes:
    focused_query = LegalQueryObject(
        legal_concepts=[matching_concept],  # ONLY THIS CRIME
        sub_queries=[SubQueryItem(
            query=f"{crime.crime_name}: {', '.join(crime.legal_elements)}. Facts: {case_facts_snippet}"
            # ^^^^ THE PROBLEM: Full case facts included in every crime's query
        )],
        important_facts=self.legal_query.important_facts
    )
    stage2_result = stage2_pipeline.run(focused_query)
```

**Why This Failed:**

1. **Case Facts Bleed:** The sub-query for "Criminal Intimidation" contained the FULL case facts (800 chars), which included "threatened to publicly accuse", "demanded ₹2 lakh", "transfer money"

2. **Prefilter Dominance:** The `classifier_prefilter.py` uses **factual trigger detection**:
   ```python
   extortion_triggers = ["demanded", "extort", "putting person in fear", "threat", "intimidation"]
   ```
   When it saw "threatened" and "demanded ₹2 lakh" in the "Criminal Intimidation" query, it triggered the extortion prefilter, returning Section 384 IPC instead of Section 506 IPC.

3. **Context Loss:** Stage 3 couldn't distinguish which parts of the facts were relevant to which crime, because it only saw ONE crime concept at a time.

4. **Repeated Misclassification:** Every crime query hit the same extortion triggers:
   - "Criminal Intimidation" → saw "threatened" → mapped to 384 IPC (Extortion)
   - "Physical Assault" → saw "threatened" → mapped to 384 IPC (Extortion)
   - "Dishonest Inducement" → saw "transfer money" → mapped to 384 IPC (Extortion)

## The Correct Architecture (Batch Query)

The lexigraphbe pipeline was **designed to handle multiple crimes together**, not one at a time. This is why Stage 1 returns a `LegalQueryObject` with **ALL legal concepts in a single object**.

### The Fix

**New Method:** `query_lexigraphbe_all_crimes()`

```python
def query_lexigraphbe_all_crimes(self) -> Dict[str, List[Dict[str, Any]]]:
    """
    Query lexigraphbe pipeline ONCE for ALL crimes using the full legal_query from Stage 1.
    The prefilter sees ALL concepts at once and can properly distinguish between them.
    """
    # Use the FULL legal_query from Stage 1 (contains all concepts together)
    print(f"[ProsecutorAgent] Running Stage 2: Section Mapping for {len(self.legal_query.legal_concepts)} concepts...")
    stage2_pipeline = Stage2Pipeline()
    stage2_result = stage2_pipeline.run(self.legal_query)  # <-- ALL CRIMES AT ONCE
    
    # ... Stage 3, Stage 4 ...
    
    # Distribute sections to crimes by matching titles and concepts
    for crime in self.prosecutor_analysis.identified_crimes:
        crime_keywords = {
            "criminal intimidation": ["criminal intimidation", "threat", "alarm"],
            "physical assault": ["assault", "hurt", "causing hurt", "injury"],
            "dishonest inducement": ["cheat", "fraud", "dishonest", "deceive"],
            "theft": ["theft", "dishonestly", "movable property"],
            "extortion": ["extortion", "putting person in fear"],
        }
        
        keywords = crime_keywords.get(crime.crime_name.lower(), [])
        matched_sections = [sec for sec in all_sections if any(kw in sec.title.lower() for kw in keywords)]
        
        # Cache results per crime
        self.retrieved_sections_cache[crime.crime_name.lower()] = {
            "recommended_sections": matched_sections,
            ...
        }
```

**Simplified Interface:** `query_lexigraphbe_for_crime()`

The old complex method is now just a wrapper:

```python
def query_lexigraphbe_for_crime(self, crime: CrimeAnalysis) -> Dict[str, Any]:
    """
    Query lexigraphbe for a specific crime.
    Uses batch query internally to avoid prefilter misclassification.
    """
    # Check cache
    if cache_key in self.retrieved_sections_cache:
        return self.retrieved_sections_cache[cache_key]
    
    # Query all crimes together (correct architecture)
    self.query_lexigraphbe_all_crimes()
    
    # Return cached result for this crime
    return self.retrieved_sections_cache.get(cache_key, {})
```

## Why This Works

### 1. Prefilter Sees Full Context

When the prefilter receives ALL concepts at once:
- `["Criminal Intimidation", "Physical Assault", "Dishonest Inducement", "Theft"]`

It can **distinguish** between them instead of treating each in isolation.

### 2. Stage 2 Maps Correctly

The Section Mapping Agent sees:
```json
{
  "legal_concepts": [
    {"concept": "Criminal Intimidation", "confidence": 0.95},
    {"concept": "Physical Assault", "confidence": 0.95},
    {"concept": "Dishonest Inducement", "confidence": 0.95},
    {"concept": "Theft", "confidence": 0.95}
  ]
}
```

And returns a **batched mapping** with separate mappings for each concept:
```json
{
  "mappings": [
    {
      "concept": "Criminal Intimidation",
      "primary_candidate_sections": [
        {"section_number": "506", "statute": "IPC", "title": "Criminal Intimidation"}
      ]
    },
    {
      "concept": "Physical Assault",
      "primary_candidate_sections": [
        {"section_number": "323", "statute": "IPC", "title": "Voluntarily Causing Hurt"}
      ]
    },
    ...
  ]
}
```

### 3. No Case Facts Bleed

The sub-queries in `self.legal_query` were created by Stage 1, which properly scoped the facts to each concept. The prosecutor doesn't inject the full case facts snippet into every sub-query.

### 4. Post-Processing Distribution

After getting ALL sections back, the prosecutor uses **keyword matching** to distribute sections to crimes:

- "Criminal Intimidation" → matches sections with "threat", "intimidation", "alarm"
- "Physical Assault" → matches sections with "assault", "hurt", "injury"
- "Extortion" → matches sections with "extortion", "putting person in fear"

This ensures each crime gets its correct sections.

## Benefits

1. **Correct Classification:** No more extortion everywhere
2. **Efficiency:** One pipeline run instead of N runs (one per crime)
3. **Cache Sharing:** All crimes share the same Stage 2/3/4 outputs
4. **Architectural Alignment:** Uses the pipeline as designed
5. **Prefilter Accuracy:** The prefilter can properly distinguish concepts

## Expected Output After Fix

```
[ProsecutorAgent] Querying lexigraphbe for ALL crimes together...
[ProsecutorAgent] Running Stage 2: Section Mapping for 4 concepts...
[ProsecutorAgent] Stage 2 output: 4 concept mappings
  - Criminal Intimidation → 506 IPC
  - Physical Assault → 323 IPC
  - Dishonest Inducement → 415 IPC
  - Theft → 378 IPC
[ProsecutorAgent] Running Stage 3: Chapter Identification...
[ProsecutorAgent] Stage 3 output: 4 verified_offences, 6 section_candidates
[ProsecutorAgent] Running Stage 4: Statutory Verification...
[ProsecutorAgent] Total sections retrieved: 6

  → Criminal Intimidation: 1 sections
  → Physical Assault: 2 sections
  → Dishonest Inducement: 2 sections
  → Theft: 1 sections

[ProsecutorAgent] Querying lexigraphbe for: Dishonest Inducement to Deliver Property
[ProsecutorAgent] Using cached results: 2 sections
[ProsecutorAgent] Retrieved 2 statutory sections
```

## Files Modified

1. **`backend/prosecutor/prosecutor.py`**
   - Added new method: `query_lexigraphbe_all_crimes()` (queries pipeline once for all crimes)
   - Simplified: `query_lexigraphbe_for_crime()` (now just a cache lookup wrapper)
   - Removed: Old focused query logic with case facts injection

2. **Created:** `backend/prosecutor/PREFILTER_FIX.md` (this document)

## Technical Notes

### Why Focused Queries Failed

The focused query approach violated the **semantic contract** of the lexigraphbe pipeline:

1. **Stage 1 is the authoritative source** of legal concepts for a case
2. **Stage 2–4 consume Stage 1 output wholesale**, not fragmented subsets
3. **Prefilters rely on concept co-occurrence** to disambiguate overlapping factual patterns

When the prosecutor created focused queries with one concept + full facts, it broke assumptions 1 and 3.

### Keyword-Based Distribution

The post-processing keyword matching is a **pragmatic fallback** for cases where Stage 4 doesn't explicitly tag which concept each section maps to. A future enhancement could use:

- **Stage 2 mapping metadata** (which concept triggered each section)
- **Ingredient overlap scoring** (match crime elements to section ingredients)
- **LLM-based relevance ranking** (ask the LLM which sections match which crime)

For now, keyword matching is sufficient and deterministic.
