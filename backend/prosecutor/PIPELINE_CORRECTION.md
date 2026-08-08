# Pipeline Correction: Using NEW lexigraphbe (Not Old agents/lexigraph)

## Issue Identified

The prosecutor was incorrectly trying to use the **OLD** `agents/lexigraph/lexigraph_agent.py` which has different architecture (citation grounding, pinecone retrieval, community retrieval, etc.).

You explicitly mentioned using **lexigraphbe** with stages 1-6, but the initial implementation was pointing to the wrong folder.

## Correction Made

### Before (Incorrect ❌)
```python
from agents.lexigraph.lexigraph_agent import LexiGraphAgent
lexigraph_agent = LexiGraphAgent()
results = lexigraph_agent.process_query(query, debug=False)
```

This was calling:
- `agents/lexigraph/lexigraph_agent.py`
- Which has: CitationGroundingGate, Pinecone, Community Retrieval, etc.
- **This is the OLD architecture**

### After (Correct ✅)
```python
from lexigraphbe.runner import run_full_pipeline

pipeline_result = run_full_pipeline(
    text=query_text,
    user_query=f"Prosecute for {crime.crime_name}",
    court_type="Sessions Court"
)
```

This now calls:
- `lexigraphbe/runner.py`
- Which orchestrates: **Stage 0 → Stage 1 → Stage 2 → Stage 3 → Stage 4 → Stage 5 → Stage 6**
- **This is the NEW architecture you specified**

## Folder Structure Clarification

```
backend/
├── agents/
│   └── lexigraph/                    ← OLD (don't use)
│       └── lexigraph_agent.py        ← OLD retrieval system
│
├── lexigraphbe/                      ← NEW (use this!)
│   ├── pipeline.py                   ← Stage 0 (Intake)
│   ├── stage1_pipeline.py            ← Stage 1 (Query Understanding)
│   ├── stage2_pipeline.py            ← Stage 2 (Subquery Mapping)
│   ├── stage3_pipeline.py            ← Stage 3 (Chapter Identification)
│   ├── stage4_pipeline.py            ← Stage 4 (Statutory Verification)
│   ├── stage5_pipeline.py            ← Stage 5 (Bail Reasoning)
│   ├── stage6_pipeline.py            ← Stage 6 (Precedent Retrieval)
│   └── runner.py                     ← Orchestrates all stages
│
└── prosecutor/                       ← Uses lexigraphbe (NEW)
    └── prosecutor.py
```

## lexigraphbe Pipeline Stages

### Stage 0: Case Intake (`pipeline.py`)
- Extracts case metadata, parties, procedural stage
- Determines legal regime (IPC vs BNS)
- Creates `CaseContextObject`

### Stage 1: Query Understanding (`stage1_pipeline.py`)
- Decomposes case into legal concepts
- Creates sub-queries without section numbers
- Returns `LegalQueryObject`

### Stage 2: Subquery Mapping (`stage2_pipeline.py`)
- Maps sub-queries to potential statutory sections
- Returns `Stage2BatchedMappingResponse`

### Stage 3: Chapter Identification (`stage3_pipeline.py`)
- Identifies relevant chapters of law
- Narrows down applicable legal framework
- Returns `ChapterIdentificationObject`

### Stage 4: Statutory Verification (`stage4_pipeline.py`)
- Verifies and validates statutory sections
- Returns verified sections with confidence scores
- Returns `StatutoryVerificationObject`

### Stage 5: Bail Reasoning (`stage5_pipeline.py`)
- Analyzes bail applicability
- Provides legal reasoning
- Returns `BailReasoningObject`

### Stage 6: Precedent Retrieval (`stage6_pipeline.py`)
- Retrieves relevant case precedents
- Matches precedents to statutory sections
- Returns `PrecedentRetrievalObject`

## How Prosecutor Uses lexigraphbe

```python
def query_lexigraphbe_for_crime(self, crime: CrimeAnalysis):
    # Build query for specific crime
    query_text = self._build_crime_specific_query(crime)
    
    # Run FULL pipeline (stages 0-6)
    pipeline_result = run_full_pipeline(
        text=query_text,
        user_query=f"Prosecute for {crime.crime_name}",
        court_type="Sessions Court"
    )
    
    # Extract results from stage 4 (statutory) and stage 6 (precedents)
    stage4_output = pipeline_result["stage4_statutory_verification"]
    stage6_output = pipeline_result["stage6_precedent_retrieval"]
    
    # Format for prosecutor use
    results = {
        "recommended_sections": stage4_output["verified_sections"],
        "similar_cases": stage6_output["precedents"],
        ...
    }
    
    return results
```

## Benefits of Using lexigraphbe Pipeline

1. **Deterministic Stages**: Stages 3 & 4 are deterministic (no LLM), more reliable
2. **Structured Output**: Each stage has well-defined schemas
3. **Verification Built-in**: Each stage has verification agents
4. **Modular**: Can call specific stages or full pipeline
5. **Legal Regime Aware**: Properly handles IPC ↔ BNS mappings
6. **Court-Specific**: Can specify court type for tailored results

## Testing

The prosecutor now correctly uses lexigraphbe:

```bash
cd backend/prosecutor
python test_prosecutor.py

# Will show:
# [ProsecutorAgent] Querying lexigraphbe pipeline for: <crime>
# (NOT the old lexigraph agent)
```

## Summary

✅ **Corrected**: Prosecutor now uses `lexigraphbe.runner.run_full_pipeline()`  
✅ **Stages**: Runs complete pipeline (stages 0-6)  
✅ **Architecture**: Uses NEW lexigraphbe, not old agents/lexigraph  
✅ **As Requested**: Follows your specification to use lexigraphbe stages 1-6  

The prosecutor is now properly integrated with the **NEW** lexigraphbe multi-stage pipeline architecture as you intended! 🎯
