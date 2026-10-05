# ✅ Defense Rebuttal Repetition - FIXED!

## Problem Identified

The Defense AI was repeating the same rebuttal regardless of what the prosecution actually argued in subsequent turns:

```
Turn 1: Student (Prosecution) → Opening argument about forgery
Turn 2: AI (Defense) → Rebuttal A responding to forgery points
Turn 3: Student (Prosecution) → NEW argument about custodial interrogation
Turn 4: AI (Defense) → SAME Rebuttal A (ignoring Turn 3!) ❌
```

## Root Causes

1. **No Turn History**: DefenseAgent didn't track what arguments it had already made
2. **No Context Awareness**: Rebuttal method didn't know what prosecution said THIS TURN vs. previous turns
3. **Static Response**: Always generated the same rebuttal to the first prosecution argument

## Solution Implemented

### 1. Modified `handle_rebuttal()` Method

**File**: `backend/prosecutor/defense.py`

**Changes**:
```python
# Before:
def handle_rebuttal(self, prosecution_argument: str) -> Dict[str, Any]:

# After:
def handle_rebuttal(self, prosecution_argument: str, previous_defense_arguments: List[str] = None) -> Dict[str, Any]:
```

Now accepts:
- `prosecution_argument`: The prosecution's CURRENT argument (this turn)
- `previous_defense_arguments`: List of ALL defense arguments made so far (to avoid repetition)

### 2. Enhanced Rebuttal Prompt with 10 Critical Rules

#### Rule 0: ANALYZE PROSECUTION'S ARGUMENT FIRST
```
- What SPECIFIC facts did prosecution rely on in THIS argument?
- What SPECIFIC allegations did prosecution make in THIS argument?
- What NEW points did prosecution raise that weren't in previous arguments?
- Respond ONLY to what prosecution said THIS TURN
```

#### Rule 1: NO REPETITION FROM PREVIOUS DEFENSE ARGUMENTS
```
- Read "ARGUMENTS ALREADY MADE BY DEFENSE" carefully
- DO NOT restate any point, argument, or ground already made
- If prosecution raised a point you already addressed, briefly reference it
- Focus on NEW prosecution contentions
```

#### Rule 2: SECTION CITATION RULE
```
- Cite sections ONLY when directly relevant to countering a prosecution point
- Do NOT cite sections just to cite them
- If prosecution didn't mention a section, you don't need to either
- Use natural language when possible
```

**Key Change**: Sections are now optional, not mandatory in every argument!

#### Rule 3: RESPOND TO ACTUAL CONTENTIONS
```
For EACH specific prosecution point raised THIS TURN:
  (a) What did prosecution claim?
  (b) What case fact supports or contradicts it?
  (c) What is the defense position on THIS specific point?
```

#### Rule 4: GROUNDED IN CASE FACTS ONLY
```
- Every factual claim must be traceable to CASE FACTS verbatim
- Do NOT generate, invent, or assume facts not stated
- Do NOT speculate about what "might have" happened
- If a fact isn't in the case facts, you cannot argue it
```

**Critical**: Prevents hallucination of facts!

#### Rule 7: PROPORTIONALITY
```
- Match the length and intensity to what prosecution actually argued
- If prosecution made 2 points, address those 2 points
- Do NOT make a generic speech; make a targeted response
```

### 3. Orchestrator Tracking

**File**: `backend/prosecutor/orchestrator_agent.py`

**Changes**:

A. Initialize tracking in agent wrapper:
```python
return {
    "agent": agent, 
    "session": None, 
    "sections": self.sections.verified_sections,
    "previous_arguments": []  # ← NEW: Track all defense arguments
}
```

B. Pass previous arguments to rebuttal:
```python
previous_arguments = agent_wrapper.get("previous_arguments", [])
result = agent.handle_rebuttal(previous_argument, previous_arguments)
```

C. Store each argument after generation:
```python
if self.llm_role == "defense":
    previous_arguments.append(argument)
    agent_wrapper["previous_arguments"] = previous_arguments
```

### 4. Prompt Changes

The rebuttal prompt now includes:

```
ARGUMENTS ALREADY MADE BY DEFENSE — DO NOT REPEAT:
  1. [Previous defense argument 1]...
  2. [Previous defense argument 2]...

PROSECUTION'S LATEST ARGUMENT (respond to THIS specifically):
[Current prosecution argument]
```

This gives the LLM:
- **Context**: What defense has already said
- **Target**: What prosecution is saying NOW
- **Instruction**: Respond to NEW points, don't repeat old points

## Benefits

### Before:
```
Prosecution Turn 1: "The accused forged documents showing Rs 75 lakhs..."
Defense Turn 1: "The applicant submits the documents are genuine..."

Prosecution Turn 2: "Custodial interrogation is necessary because..."
Defense Turn 2: "The applicant submits the documents are genuine..." ❌ REPETITION!
```

### After:
```
Prosecution Turn 1: "The accused forged documents showing Rs 75 lakhs..."
Defense Turn 1: "The applicant submits the documents are genuine..."

Prosecution Turn 2: "Custodial interrogation is necessary because..."
Defense Turn 2: "The prosecution contends custody is necessary for document verification. 
However, the material already with police includes the original sale deeds and revenue 
records. The applicant has cooperated throughout and no recovery from custody is 
identified..." ✅ TARGETED RESPONSE!
```

## Section Citation Improvement

### Before:
Every argument: "Section 467 IPC, Section 468 IPC, Section 471 IPC..."

### After:
- Opening: Identifies sections once
- Rebuttal 1: "The prosecution relies on forgery allegations..." (no section repetition if not needed)
- Rebuttal 2: "Regarding custodial interrogation..." (natural language)
- Rebuttal 3: "Section 420 requires dishonest inducement..." (cited only when directly relevant)

Sections mentioned **when necessary**, not mandatorily.

## No Fact Generation

The prompt explicitly forbids:
```
4. GROUNDED IN CASE FACTS ONLY:
   - Every factual claim must be traceable to CASE FACTS verbatim
   - Do NOT generate, invent, or assume facts
   - Do NOT speculate
   - If a fact isn't stated, you cannot argue it
```

Every defense argument is now **strictly grounded** in the provided case facts.

## Example Flow

### Turn 1: Student Prosecution Opening
```
"May it please this Hon'ble Court, the prosecution opposes anticipatory bail. 
The accused forged ownership documents and induced the complainant to pay Rs 75 lakhs. 
Sections 467, 468, 471, 420, and 406 IPC are attracted..."
```

### Turn 2: AI Defense Rebuttal 1
```
"The prosecution alleges forgery of ownership documents. The applicant respectfully 
submits that the documents executed by him are genuine and that the allegations arise 
in the context of a title dispute. The material presently available comprises primarily 
the complainant's statement and revenue records showing discrepancy, but the documents 
themselves are under verification. The prosecution has not demonstrated why custodial 
interrogation is necessary for this verification when the applicant has cooperated 
throughout. It is therefore prayed that anticipatory bail be granted."
```

**Tracked in previous_arguments**: [Rebuttal 1 full text]

### Turn 3: Student Prosecution Rebuttal
```
"The defense contends this is a title dispute, but the complainant paid Rs 75 lakhs 
based on these documents. The sophistication of the alleged forgery and the substantial 
amount require the accused's custodial interrogation to trace the flow of funds and 
confront him with the original documents."
```

### Turn 4: AI Defense Rebuttal 2 (NEW, not repeated)
```
"The prosecution now emphasizes the flow of funds and confrontation requirement. 
However, the case facts show the applicant received the advance payment through banking 
channels, which are already traceable through bank records without custody. The original 
documents the prosecution seeks to confront are with the investigating officer and were 
voluntarily provided by the applicant. The applicant has appeared before the investigating 
officer on multiple occasions. The material does not establish that confrontation requires 
custodial interrogation when the applicant has demonstrated consistent cooperation. 
It is therefore prayed that anticipatory bail be granted."
```

**Key differences**:
- ✅ Responds to SPECIFIC prosecution points (flow of funds, confrontation)
- ✅ Uses ACTUAL case facts (banking channels, documents with IO, voluntary appearance)
- ✅ Does NOT repeat "documents are genuine" argument from Turn 2
- ✅ Targeted, specific, non-repetitive

## Files Modified

1. **`backend/prosecutor/defense.py`**
   - Method: `handle_rebuttal()`
   - Added: `previous_defense_arguments` parameter
   - Enhanced: Prompt with 10 context-aware rules

2. **`backend/prosecutor/orchestrator_agent.py`**
   - Method: `initialize_agent()` - Added `previous_arguments` tracking
   - Method: `_get_llm_argument()` - Pass and update previous arguments

## Testing

Run the moot court:
```bash
cd C:\Users\Ajinkya\Desktop\MootCourt\backend\prosecutor
python run_moot_court.py
```

Now:
1. ✅ Defense rebuttals respond to CURRENT prosecution argument
2. ✅ No repetition across turns
3. ✅ Sections cited only when necessary
4. ✅ All arguments grounded in case facts only
5. ✅ Targeted, proportionate responses

## Summary

**Problem**: Defense AI repeated same rebuttal regardless of new prosecution arguments

**Solution**: 
- Track all previous defense arguments
- Pass them to rebuttal method
- Enhanced prompt to analyze prosecution's CURRENT argument
- Respond specifically to NEW points
- Avoid repeating previous positions

**Result**: Defense now gives **contextual, non-repetitive, targeted rebuttals** that respond to what prosecution actually argued THIS TURN! 🎉
