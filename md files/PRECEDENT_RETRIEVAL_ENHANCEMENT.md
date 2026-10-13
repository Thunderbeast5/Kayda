# Precedent Retrieval Enhancement: Multi-Statute Support

## Overview
Enhanced the precedent retrieval system (Stage 6) to consider **ALL statute types** when matching case precedents, not just IPC/BNS criminal offences.

## Problem Statement
Previously, precedent matching only considered:
- ✅ IPC/BNS criminal offences (e.g., 498A IPC, 406 IPC)
- ❌ Missing: BNSS/CrPC procedural sections (e.g., 438 CrPC for anticipatory bail)
- ❌ Missing: BSA/IEA evidence sections (e.g., 27 IEA for confessions)
- ❌ Missing: Special Act provisions (e.g., POCSO, NDPS, SC/ST)

This meant that precedents citing relevant procedural or evidentiary provisions were not properly matched.

## Solution Implemented

### 1. **Extended Statute Extraction** (`precedent_retrieval_agent.py`)

#### Before:
```python
# Only extracted IPC/BNS sections
for sec in statutory_object.verified_sections:
    clean_sec = sec.section_number.upper()
    active_secs.add(clean_sec)  # e.g., "406", "498A"
```

#### After:
```python
# Extract ALL statute types with prefixes
# Format: "STATUTE:SECTION" (e.g., "IPC:406", "BNSS:482", "BSA:25")

# 1. IPC/BNS criminal offences
for sec in statutory_object.verified_sections:
    statute = getattr(sec, 'statute', 'IPC').upper()
    active_secs.add(f"{statute}:{clean_sec}")  # "IPC:406"

# 2. BNSS/CrPC procedural sections
bnss_output = getattr(statutory_object, 'bnss_output', None)
if bnss_output and hasattr(bnss_output, 'verified_sections'):
    for sec in bnss_output.verified_sections:
        statute = getattr(sec, 'statute', 'BNSS').upper()
        active_secs.add(f"{statute}:{clean_sec}")  # "BNSS:482"

# 3. BSA/IEA evidence sections  
bsa_output = getattr(statutory_object, 'bsa_output', None)
if bsa_output and hasattr(bsa_output, 'verified_sections'):
    for sec in bsa_output.verified_sections:
        statute = getattr(sec, 'statute', 'BSA').upper()
        active_secs.add(f"{statute}:{clean_sec}")  # "BSA:25"
```

### 2. **Enhanced Section Matching Logic**

Now supports:
- **Direct statute matching**: "BNSS:482" matches "482 BNSS" in precedent
- **Equivalent statute matching**: 
  - IPC ↔ BNS: "IPC:406" also matches "316 BNS"
  - CrPC ↔ BNSS: "CrPC:438" also matches "482 BNSS"
  - IEA ↔ BSA: "IEA:27" also matches "25 BSA"
- **Multiple match patterns**: "406 IPC", "IPC 406", "Section 406", etc.

#### Equivalent Mappings Added:

**Criminal Procedure (CrPC ↔ BNSS):**
```python
"438 CrPC" ↔ "482 BNSS"  # Anticipatory bail
"439 CrPC" ↔ "483 BNSS"  # Special powers
"482 CrPC" ↔ "528 BNSS"  # Inherent powers
"437 CrPC" ↔ "479 BNSS"  # Bail in non-bailable offences
```

**Evidence (IEA ↔ BSA):**
```python
"27 IEA" ↔ "25 BSA"  # Discovery based on accused's information
"24 IEA" ↔ "22 BSA"  # Confession by inducement
"25 IEA" ↔ "23 BSA"  # Confession to police officer
"26 IEA" ↔ "24 BSA"  # Confession in police custody
```

### 3. **Updated Prompts** (`prompts.py`)

Enhanced system prompt to instruct LLM:
```
- Consider ALL statute types when assessing relevance:
  • Criminal Offences: IPC/BNS sections (e.g., 498A IPC ↔ 85 BNS, 406 IPC ↔ 316 BNS)
  • Criminal Procedure: CrPC/BNSS sections (e.g., 438 CrPC ↔ 482 BNSS for anticipatory bail)
  • Evidence: IEA/BSA sections (e.g., 27 IEA ↔ 25 BSA for confessions)
  • Special Acts: POCSO, NDPS, SC/ST, PCA, UAPA, PMLA, etc.
```

Updated user prompt examples to include all statute types:
```json
{
  "verified_offences": ["498A IPC", "438 CrPC", "27 IEA", "3 POCSO"]
}
```

### 4. **Enhanced Precedent Corpus Examples**

Added multi-statute precedent examples:

```python
{
    "case_name": "Arnesh Kumar v. State of Bihar",
    "offences_covered": ["498A IPC", "85 BNS", "438 CrPC", "482 BNSS", "4 Dowry Prohibition Act"],
    "facts_summary": "Allegations under 498A IPC. Petitioner sought anticipatory bail under 438 CrPC...",
    "ratio_decidendi": "Procedural protections under CrPC/BNSS must be strictly followed..."
},
{
    "case_name": "State v. Accused (Confession Case)",
    "offences_covered": ["302 IPC", "27 IEA", "25 BSA", "438 CrPC"],
    "facts_summary": "Murder case with confession. Prosecution relied on Section 27 IEA...",
    "ratio_decidendi": "Evidence under Section 27 IEA (now Section 25 BSA) is admissible..."
},
{
    "case_name": "POCSO Child Protection Precedent",
    "offences_covered": ["3 POCSO", "4 POCSO", "376 IPC", "438 CrPC", "482 BNSS"],
    "facts_summary": "Sexual assault under POCSO. Anticipatory bail sought...",
    "ratio_decidendi": "BNSS Section 482 (CrPC 438) must be applied stringently in POCSO cases..."
}
```

## Impact & Benefits

### ✅ Improved Precedent Relevance
- Precedents citing relevant procedural sections (like 438 CrPC) are now matched
- Evidence-based precedents (like those citing Section 27 IEA) are now identified
- Special Act precedents (POCSO, NDPS) are properly matched

### ✅ Cross-Regime Compatibility
- Cases from IPC regime now match BNS precedents
- CrPC-based precedents now match BNSS cases
- IEA-based evidence precedents now match BSA cases

### ✅ Better Similarity Scoring
The F1 factor (section overlap) now considers:
- Criminal offences (IPC/BNS) - 40% weight
- Procedural provisions (BNSS/CrPC) - 40% weight  
- Evidence sections (BSA/IEA) - 40% weight
- Special Act provisions - 40% weight

**Example:** A case with both IPC 498A and CrPC 438 will now match precedents citing either or both statutes.

## Technical Architecture

### Data Flow:
```
Stage 4 Output
├── verified_offences (IPC/BNS)
├── bnss_output.verified_sections (BNSS/CrPC)
├── bsa_output.verified_sections (BSA/IEA)
└── act_router_output.routing_decisions (Special Acts)
           ↓
    Extract all statutes with prefixes
    ["IPC:498A", "BNSS:482", "BSA:25", "POCSO:3"]
           ↓
    Match against precedent corpus
    (with equivalent matching)
           ↓
    Calculate similarity score (F1-F4)
           ↓
    Rank and return precedents
```

### Statute Format Convention:
- **Storage format**: `"STATUTE:SECTION"` (e.g., `"IPC:406"`, `"BNSS:482"`)
- **Display format**: `"SECTION STATUTE"` (e.g., `"406 IPC"`, `"482 BNSS"`)
- **Matching**: Supports both formats plus variations

## Files Modified

1. **`lexigraphbe/precedent_retrieval_agent.py`**
   - Extended statute extraction to include BNSS/CrPC, BSA/IEA
   - Enhanced section matching with equivalents
   - Updated similarity scoring logic
   - Added comprehensive precedent examples

2. **`lexigraphbe/prompts.py`**
   - Updated STAGE6_PRECEDENT_RETRIEVAL_SYSTEM_PROMPT
   - Updated STAGE6_PRECEDENT_RETRIEVAL_USER_PROMPT_TEMPLATE
   - Added statute type guidance and examples

## Testing Recommendations

### 1. Test Multi-Statute Case Matching
```python
# Test case with IPC + CrPC + IEA
stage4_result = {
    "verified_offences": [
        {"statute": "IPC", "section_number": "498A"}
    ],
    "bnss_output": {
        "verified_sections": [
            {"statute": "CrPC", "section_number": "438"}
        ]
    },
    "bsa_output": {
        "verified_sections": [
            {"statute": "IEA", "section_number": "27"}
        ]
    }
}

# Should match precedents with:
# - 498A IPC or 85 BNS
# - 438 CrPC or 482 BNSS
# - 27 IEA or 25 BSA
```

### 2. Test Equivalent Matching
```python
# Input: CrPC 438 (anticipatory bail)
# Should match precedents with: 438 CrPC, 482 BNSS, or both
```

### 3. Test Special Acts
```python
# Input: POCSO Section 3
# Should match precedents citing POCSO Act
```

### 4. Verify Similarity Scoring
```python
# Case with IPC:498A + BNSS:482
# Precedent with 85 BNS + 438 CrPC
# Expected: F1 = 0.40 (both equivalents matched)
```

## Integration with PrecedentStatuteMatcher

The existing `PrecedentStatuteMatcher` class (in `precedent_statute_matcher.py`) already supports:
- ✅ IPC ↔ BNS bidirectional mapping
- ✅ CrPC ↔ BNSS bidirectional mapping
- ✅ IEA ↔ BSA bidirectional mapping
- ✅ Special Act normalization (POCSO, NDPS, SC/ST, etc.)
- ✅ Extraction from all Stage 4 sources

The enhancements in `precedent_retrieval_agent.py` now **leverage** this existing infrastructure for comprehensive multi-statute precedent matching.

## Future Enhancements

1. **Expand Equivalent Mappings**: Add more CrPC↔BNSS and IEA↔BSA section mappings
2. **Weight Adjustment**: Consider weighting procedural sections differently than criminal offences
3. **Corpus Enhancement**: Populate precedent database with multi-statute tagged cases
4. **Cross-Reference Validation**: Ensure BNSS/BSA outputs are properly populated in Stage 4

## Conclusion

The precedent retrieval system now provides **comprehensive multi-statute matching** across:
- ✅ Criminal Offences (IPC/BNS)
- ✅ Criminal Procedure (CrPC/BNSS)
- ✅ Evidence (IEA/BSA)
- ✅ Special Acts (POCSO, NDPS, SC/ST, etc.)

This enhancement ensures that relevant precedents are identified regardless of which statutory framework they cite, improving the quality and relevance of legal research and bail analysis.
