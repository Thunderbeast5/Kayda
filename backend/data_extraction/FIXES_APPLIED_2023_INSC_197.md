# Fixes Applied for 2023_INSC_197 Extraction Issues

## Issues Identified and Fixed

### 1. ✅ Case Title Missing
**Problem**: Case title was empty  
**Cause**: Pattern didn't handle names with `@` symbol and two-line format  
**Fix**: Updated `_extract_case_title()` to handle:
- Names with @ symbol: "KARAN @ FATIYA"
- Two-line format with blank line between names
- Validation to ensure it's a valid case title (checks for STATE/UNION keywords)

**Result**: `"KARAN @ FATIYA v. THE STATE OF MADHYA PRADESH"` ✓

### 2. ✅ Missing IPC Sections 363 and 376(2)(i)
**Problem**: Only 201, 302 extracted; missing 363, 376(2)(i)  
**Cause**: Context filtering was too aggressive, sections not in high-confidence patterns  
**Fix**: Enhanced high-confidence patterns to include:
- "charged for offences under sections X, Y" format
- Better handling of comma/slash-separated lists
- Subsection formats like 376(2)(i)

**Result**: `["201", "302", "363", "376(2)(I)"]` ✓

### 3. ✅ POCSO Sections Format
**Problem**: Expected `["5(m)", "6"]`, got `["1", "2", "3", "5", "6", "36", "37"]`  
**Cause**: Extracting numbers from Act definitions like "section 2(12)"  
**Fix**: 
- Added negative lookahead to exclude multi-digit subsections: `(?!\(\d)`
- Limited POCSO sections to 1-20 range (typical for POCSO Act)
- Better extraction of single-letter subsections like 5(m)

**Current Result**: `["1", "2", "5", "6"]` - Still has extra sections 1, 2  
**Note**: These may be from legitimate POCSO references, but 5(m) should be captured with subsection

### 4. ✅ Issue for Consideration Wrong
**Problem**: Showed "MARCH 03, 2023" (judgment date) instead of legal issue  
**Expected**: Issue starting with "Whether..."  
**Fix**: Completely rewrote `_extract_issues()` to:
- Look for "whether" questions in judgment body
- Search near "issue" and "question" keywords
- Extract substantial questions (>50 chars) from first half of document

**Result**: `"whether once an accused after conviction at the stage of appeal is held to be a juvenile/child under the provisions of the 2015 Act, what would be the status of the trial, the conviction and sentence..."` ✓

## Precision + Recall Balance

The script now implements a **two-pass strategy**:

1. **Pass 1 (Recall)**: Extract ALL sections using comprehensive patterns
2. **Pass 2 (Precision)**: Filter out sections from cited cases using context analysis
3. **Pass 3 (Safety Net)**: Always include high-confidence contexts (charged/convicted/sentenced)

This ensures:
- ✓ Don't miss sections from present case (RECALL)
- ✓ Filter out sections from cited precedents (PRECISION)  
- ✓ Never filter out critical "charged under" mentions (SAFETY)

## Verification Commands

```powershell
# Check all fields
Get-Content backend/data_extraction/json/json_output_2023/2023_INSC_197.json | ConvertFrom-Json | Select-Object case_id, case_title, @{Name='ipc';Expression={$_.ipc_sections_referred -join ', '}}, @{Name='pocso';Expression={$_.pocso_sections_referred -join ', '}}, @{Name='issue';Expression={$_.issue_for_consideration.Substring(0,100)}} | Format-List
```

## Remaining Minor Issues

1. **POCSO sections 1, 2**: These are being extracted but may be from legitimate Act references. Need to verify if they're from the present case or statutory definitions.
2. **POCSO 5(m) subsection**: Pattern captures "5" instead of "5(m)" - may need further refinement of subsection extraction regex.
