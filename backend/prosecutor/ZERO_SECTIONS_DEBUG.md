# Zero Sections Retrieved - Debug Analysis & Fix

## Problem Summary
The prosecutor was showing **"Retrieved 0 statutory sections"** when querying lexigraphbe for crimes.

## Root Cause Analysis

### Issue #1: Schema Mismatch in Prosecutor
**Location:** `prosecutor/prosecutor.py` line ~448

**Problem:**
```python
verified_offences = stage4_output.get("verified_offences", [])
results = {"recommended_sections": verified_offences, ...}
```

The prosecutor was only checking `verified_offences` field from Stage 4 output. However, Stage 4 has TWO fields:
- `verified_offences`: New v4.0 schema format (may be empty if LLM doesn't populate it)
- `verified_sections`: Backward compatibility format (usually populated)

**Fix Applied:**
Added fallback logic to check `verified_sections` if `verified_offences` is empty, and convert the format:

```python
verified_offences = stage4_output.get("verified_offences", [])

# If verified_offences is empty, try verified_sections as fallback
if not verified_offences:
    verified_sections = stage4_output.get("verified_sections", [])
    print(f"[ProsecutorAgent] verified_offences empty, using verified_sections fallback: {len(verified_sections)} sections")
    # Convert verified_sections to a compatible format
    for v_sec in verified_sections:
        verified_offences.append({
            "section_number": v_sec.get("section_number", ""),
            "statute": v_sec.get("statute", "IPC"),
            "title": v_sec.get("section_title", ""),
            "section_title": v_sec.get("section_title", ""),
            "ingredients_matched": [ing.get("ingredient", "") for ing in v_sec.get("ingredients", [])],
            # ... more fields
        })
```

### Issue #2: Potential Empty Pipeline Output
**Hypothesis:** Stage 2, Stage 3, or Stage 4 might be returning empty results.

**Debug Logging Added:**

1. **Stage 2 Debug** (line ~424):
   ```python
   if stage2_output:
       mapped_sections = stage2_output.get("mapped_sections", [])
       print(f"[ProsecutorAgent] Stage 2 output: {len(mapped_sections)} mapped_sections")
   ```

2. **Stage 3 Debug** (line ~437):
   ```python
   if stage3_output:
       verified_offences_s3 = stage3_output.get("verified_offences", [])
       section_candidates_s3 = stage3_output.get("section_candidates", [])
       print(f"[ProsecutorAgent] Stage 3 output: {len(verified_offences_s3)} verified_offences, {len(section_candidates_s3)} section_candidates")
   ```

3. **Stage 4 Debug** (line ~455):
   ```python
   if not verified_offences:
       verified_sections = stage4_output.get("verified_sections", [])
       print(f"[ProsecutorAgent] verified_offences empty, using verified_sections fallback: {len(verified_sections)} sections")
   ```

4. **Statutory Agent Debug** (`lexigraphbe/statutory_verification_agent.py`):
   ```python
   print(f"[StatutoryVerificationAgent] Before fallback: verified_offences={len(statutory_obj.verified_offences)}, verified_sections={len(statutory_obj.verified_sections)}")
   # ... fallback logic ...
   print(f"[StatutoryVerificationAgent] After fallback: verified_offences={len(statutory_obj.verified_offences)}, verified_sections={len(statutory_obj.verified_sections)}")
   ```

## Files Modified

1. **`backend/prosecutor/prosecutor.py`**
   - Added fallback logic from `verified_offences` to `verified_sections`
   - Added debug logging for Stage 2, Stage 3, and Stage 4 outputs
   - Added format conversion for `verified_sections` → `verified_offences` format

2. **`backend/lexigraphbe/statutory_verification_agent.py`**
   - Added debug logging before and after the fallback logic

## Expected Behavior After Fix

When running the prosecutor, you should now see:

```
[ProsecutorAgent] Querying lexigraphbe for: Dishonest Inducement to Deliver Property
[ProsecutorAgent] Running Stage 2: Section Mapping...
[ProsecutorAgent] Stage 2 output: X mapped_sections
  - 420 IPC: Cheating
  - 415 IPC: Cheating
[ProsecutorAgent] Running Stage 3: Chapter Identification...
[ProsecutorAgent] Stage 3 output: Y verified_offences, Z section_candidates
[ProsecutorAgent] Running Stage 4: Statutory Verification...
[StatutoryVerificationAgent] Before fallback: verified_offences=0, verified_sections=N
[StatutoryVerificationAgent] After fallback: verified_offences=N, verified_sections=N
[ProsecutorAgent] verified_offences empty, using verified_sections fallback: N sections
[ProsecutorAgent] Retrieved N statutory sections
```

## Next Steps

1. **Run the prosecutor again** and observe the debug output to identify which stage is returning empty results
2. **If Stage 2 is empty**: Check if the legal concept → section mapping is working correctly
3. **If Stage 3 is empty**: Check if chapter identification is filtering out all candidates
4. **If Stage 4 is empty**: Check if statutory verification is failing to populate either field

## Additional Notes

### Why might verified_offences be empty?

1. **LLM didn't follow the prompt schema**: The Stage 4 prompt asks for `verified_offences` array, but the LLM might return it empty or with a different structure
2. **Pydantic validation failed**: The LLM output might not match the `VerifiedOffenceItemStage4` schema
3. **Stage 3 returned no candidates**: If Stage 3's `section_candidates` is empty, Stage 4 has nothing to verify

### Schema v4.0 Structure

Stage 4 returns `StatutoryVerificationObject` with:
```python
{
    "schema_version": "4.0",
    "verified_offences": [  # NEW format with ingredient evaluation
        {
            "section_number": "498A",
            "statute": "IPC",
            "title": "...",
            "ingredient_evaluation": [...],
            "overall_prima_facie_strength": "Strong",
            ...
        }
    ],
    "verified_sections": [  # BACKWARD COMPAT format
        {
            "section_number": "498A",
            "section_title": "...",
            "ingredients": [...],
            "overall_confidence": 0.95,
            ...
        }
    ]
}
```

The prosecutor needs to handle BOTH formats for robustness.
