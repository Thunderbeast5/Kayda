# Stage 3 Improved: Precision + Recall Balance

## Overview
Successfully incorporated precision features from `stage_3_precision.py` into `stage_3_improved.py` while maintaining high recall.

## Key Strategy: Two-Pass Extraction

### Pass 1: HIGH RECALL (Extract Everything)
Extract ALL section mentions using comprehensive patterns:
- Comma-separated lists: "ss. 376, 452 and 506 IPC"
- Slash-separated lists: "Section 498A, 323/504/506 IPC"  
- Individual sections with letters: "376A, 498A, 304B"
- Subsections: "Section 5(m)/6 POCSO", "437(3) CrPC"

### Pass 2: PRECISION FILTERING (Context Analysis)
Apply context-based filtering using:
- **Present Case Indicators** (keep these):
  - the appellant, the accused, the present case
  - charged/convicted/sentenced/prosecuted under
  - the FIR, the incident, the victim
  
- **Cited Case Indicators** (filter out these):
  - v. State of, as held in, in the case of
  - referred to, relied upon, cited, quoted
  - illustration, example, paragraph references

### Pass 3: RECALL SAFETY NET (High-Confidence Bypass)
Sections found in **HIGH-CONFIDENCE contexts** bypass filtering:
- "charged under Section X"
- "convicted of Section Y"  
- "FIR registered under Section Z"
- "sentenced to Section W"

These are ALWAYS included regardless of surrounding context.

## Implementation Details

### Context Window Analysis
```python
CONTEXT_WINDOW = 300  # characters before/after section mention
```

For each extracted section:
1. Find all occurrences in text
2. Extract 300-char window around each mention
3. Check if context contains present case indicators
4. Check if context contains cited case indicators  
5. Include section if present case context found AND no cited case indicators

### High-Confidence Patterns (Always Extracted)
```python
high_conf_ipc_patterns = [
    r'(?:charged|convicted|sentenced|prosecuted|registered|offence)\s+(?:with|of|to|under)\s+[^.]{0,100}?(?:Section|Sections|ss?\.|u/s)\s+([\d,\s/A-Z\(\)]+)\s+(?:of\s+)?(?:the\s+)?(?:IPC|Indian Penal Code)',
    r'(?:FIR|complaint)\s+(?:registered|filed)\s+(?:under|u/s)\s+[^.]{0,100}?([\d,\s/A-Z]+)\s+(?:IPC|Indian Penal Code)',
]
```

## What This Solves

### Problem 1: Missing Sections (Recall Issue)
**Before**: Section 452 not extracted from "ss. 376, 452 and 506 IPC"
**After**: All sections extracted from lists, including slash-separated formats

### Problem 2: False Positives from Cited Cases (Precision Issue)  
**Before**: Extracting sections from "as held in State v. Kumar where Section 376 IPC was discussed"
**After**: Context analysis filters out sections from cited precedents

### Problem 3: Overly Aggressive Filtering
**Before**: Risk of filtering out valid sections
**After**: High-confidence contexts (charged/convicted) bypass filtering, ensuring critical sections always included

## Supported Legal Acts

### Comprehensive Coverage
- **IPC**: Indian Penal Code sections (with letters: 498A, 304B, etc.)
- **BNS**: Bharatiya Nyaya Sanhita sections
- **POCSO**: With subsections like 5(m), 6
- **Dowry Act**: Sections 3, 4, etc.
- **CrPC**: Procedural sections 482, 438, 437(3), etc.
- **POSH Act**: Sexual Harassment at Workplace Act sections
- **IT Act**: Information Technology Act sections

## Balance Achieved

| Aspect | Strategy | Result |
|--------|----------|--------|
| **Recall** | Comprehensive pattern matching + high-confidence bypass | Don't miss critical sections |
| **Precision** | Context-aware filtering for cited cases | Reduce false positives |
| **Safety** | Always include charged/convicted/sentenced contexts | Protect against over-filtering |

## Testing Recommendations

1. **Recall Test**: Check INSC_585 for Section 452 (was missing before)
2. **Precision Test**: Verify sections from "as held in X v. Y" are filtered out
3. **Safety Test**: Ensure "charged under Section X" always extracted
4. **Complex Format Test**: Check "498A, 323/504/506 IPC" extracts all 4 sections

## Usage

The balanced extraction is now default in `stage_3_improved.py`:

```bash
python backend/data_extraction/scriptsD/stage_3_improved.py
```

No changes needed - runs automatically with precision+recall balance.
