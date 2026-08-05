# IPC Retrieval System Fixes

## Problem Summary

The IPC retrieval system was generating false positives due to semantic matching instead of strict ingredient-based matching:

1. **IPC 120B (conspiracy) incorrectly selected** when facts showed solo fraud (no agreement between multiple persons)
2. **IPC 406 vs IPC 420 confusion** - "dishonestly inducing delivery" (IPC 420 cheating) was matching IPC 406 (criminal breach of trust which requires entrustment)
3. **IPC 411 incorrectly accepted** when facts showed accused stole property (not received stolen property)
4. **Candidate explosion** - 63 candidates instead of <10 meaningful sections

## Root Cause

- **Stage 1a (Chapter Selection)**: Used semantic similarity ("investment scam" → "conspiracy") instead of ingredient checklist
- **Stage 1b (Section Selection)**: Checked ingredients but with semantic matching rather than strict literal matching
- **Binary Gate**: Checked ingredient presence but didn't enforce factual support requirement
- **No ingredient pre-filter**: Over-inclusive candidate generation from semantic associations

## Solutions Implemented

### 1. Stage 1a: Ingredient-Based Chapter Selection

**File**: `backend/prosecutor/services/llm_ipc_retrieval_service.py`
**Lines**: ~330-430

**Changes**:
- Rewrote prompt to enforce ingredient checklist BEFORE chapter selection
- Added explicit examples showing:
  - Solo fraud ≠ conspiracy (missing "agreement between multiple persons")
  - Matrimonial cruelty + threats = correct chapters
  - Applicant's denial ≠ false charge allegation
- Added "INGREDIENT-BASED SELECTION PROCESS" instructions
- Emphasized: "DO NOT select chapters based on semantic similarity"

**Key Addition**: Conspiracy chapter validation rule
```python
"OF CRIMINAL CONSPIRACY": {
    "required_any": [
        "agreement between", "conspiracy", "conspired", "along with",
        "in conspiracy with", "common design", "multiple persons",
        "co-conspirator", "joint plan", "planned together"
    ],
    "required_context": [
        "agreement", "conspiracy", "conspired", "along with", "multiple"
    ]
}
```

### 2. Stage 1b: Literal Ingredient Matching

**File**: `backend/prosecutor/services/llm_ipc_retrieval_service.py`
**Lines**: ~555-670

**Changes**:
- Rewrote prompt with "CRITICAL RULE: Match facts to LITERAL STATUTORY INGREDIENTS, not semantic themes"
- Added "COMMON ERRORS TO AVOID" section explicitly covering:
  - IPC 406 (entrustment + misappropriation) vs IPC 420 (deception + inducement)
  - IPC 411 (receiving from another thief) vs theft by accused
  - IPC 120B (requires multiple persons with agreement) vs solo fraud
- Added detailed example showing IPC 406 rejection when facts show false promise (which is IPC 420)
- Changed instruction from "matched_ingredients" to "literal fact matching ingredient X"

**Before**:
```
A section is selected ONLY when ALL its essential statutory ingredients 
are present (YES) or possibly present (UNKNOWN) on the facts.
```

**After**:
```
CRITICAL RULE: Match facts to LITERAL STATUTORY INGREDIENTS, not semantic themes.

For each section:
1. Identify its EXACT statutory ingredients (not related concepts)
2. Check if facts LITERALLY support each ingredient
3. Select ONLY if ALL core ingredients are supported
```

### 3. Binary Gate: Stricter Ingredient Enforcement

**File**: `backend/prosecutor/services/llm_ipc_retrieval_service.py`
**Lines**: ~820-950

**Changes**:
- Removed "POSSIBLE" classification (was too permissive)
- Changed from 3-level (SUPPORTED/POSSIBLE/NOT_SUPPORTED) to 2-level (SUPPORTED/NOT_SUPPORTED)
- Added "CRITICAL DISTINCTIONS" section with explicit rules:
  - IPC 406 vs IPC 420: "If facts show false promise → use IPC 420, NOT IPC 406"
  - IPC 411: "If facts show accused STOLE the property → reject IPC 411"
  - IPC 120B: "Solo fraud → reject IPC 120B"
- Removed "POSSIBLE" from accepted decisions

**Before**:
```python
if decision in ["SUPPORTED", "POSSIBLE"]:
    passed.append(cand)
```

**After**:
```python
if decision == "SUPPORTED":
    passed.append(cand)
```

### 4. Enhanced Chapter Validation

**File**: `backend/prosecutor/services/llm_ipc_retrieval_service.py`
**Lines**: ~990-1020

**Added**: Conspiracy chapter validation rule to catch false positives in fallback path

## Expected Results

After these fixes:

1. **IPC 120B (conspiracy)**: ✓ Rejected for solo fraud (no agreement/multiple persons)
2. **IPC 406 ingredient matching**: ✓ Correctly distinguishes entrustment vs inducement
3. **IPC 411 binary gate**: ✓ Rejects when accused is original thief (not receiver)
4. **Candidate count**: ✓ Reduced from 63 → <10 meaningful sections

## Testing

Run the test script to verify fixes:

```bash
cd backend
python test_ipc_retrieval_fixes.py
```

Expected output:
- ✓ PASS: IPC 120B (conspiracy) correctly rejected
- ✓ PASS: IPC 406 correctly rejected OR reasoning shows entrustment (not inducement)
- ✓ PASS: IPC 411 (receiving stolen property) correctly rejected
- ✓ SUCCESS: Candidate count reduced to <10

## Files Modified

1. `backend/prosecutor/services/llm_ipc_retrieval_service.py`
   - Stage 1a chapter prompt (lines ~330-430)
   - Stage 1b section prompt (lines ~555-670)
   - Stage 1c binary gate prompt (lines ~820-950)
   - Chapter validation rules (lines ~990-1020)

## Backward Compatibility

✓ No breaking changes to API contract
✓ Return format unchanged (matches PineconeService contract)
✓ Downstream services (merge_service, verification_service) require no modifications

## Next Steps

1. Test with actual bail application fact patterns
2. Monitor candidate count (should be <10 for typical cases)
3. Verify conspiracy chapter rejection in production logs
4. Check IPC 406/420 distinction accuracy
5. Validate IPC 411 rejection for non-receiving scenarios
