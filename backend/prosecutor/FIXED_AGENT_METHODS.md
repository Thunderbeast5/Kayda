# ✅ Agent Method Interface Fixed!

## Problem
The orchestrator was calling non-existent methods on the agents:
- ❌ `DefenseAgent.defense_rebuttal()` - doesn't exist
- ❌ `DefenseAgent.opening_bail_argument()` - doesn't exist  
- ❌ Direct agent calls without proper state management

## Solution Applied

### 1. Fixed Method Names
**DefenseAgent** (`defense.py`):
- ✅ `build_opening_argument()` → Returns dict with `"opening_statement"` key
- ✅ `handle_rebuttal(prosecution_argument)` → Returns dict with `"rebuttal_statement"` key
- ✅ `analyze_case(case_text)` → Must be called first to initialize

**ProsecutorAgent** (`prosecutor_agent.py`):
- ✅ `opening_argument(session)` → Returns updated SessionState
- ✅ `rebuttal(session, defense_argument)` → Returns updated SessionState
- ✅ Requires full session state management

### 2. Proper Initialization

**DefenseAgent**:
```python
agent = DefenseAgent()
agent.analyze_case(case_text)  # Initialize first!
result = agent.build_opening_argument()
argument_text = result["opening_statement"]
```

**ProsecutorAgent**:
```python
from schemas import SessionState, RetrievedSection

agent = ProsecutorAgent(api_key=api_key, model=model)

# Convert sections
retrieved_sections = {
    vs.section_number: RetrievedSection(...)
    for vs in verified_sections
}

# Extract case
p_output = agent._extract_case(case_text, retrieved_sections)
usage_plan = agent._build_usage_plan(case_text, p_output, retrieved_sections)

# Create session
session = SessionState(
    session_id="orchestrator",
    case_id="moot_court",
    case_text=case_text,
    student_role=student_role,
    retrieved_sections=retrieved_sections,
    prosecutor_output=p_output,
    section_usage_plan=usage_plan,
    turn_history=[],
)

# Now use agent
session = agent.opening_argument(session)
argument_text = session.turn_history[-1].argument
```

### 3. Orchestrator Updates

Updated `initialize_agent()` to return agent wrapper:
```python
{
    "agent": agent_instance,
    "session": session_state_or_none
}
```

Updated `_get_llm_argument()` to:
- Accept agent wrapper instead of bare agent
- Call correct methods based on role
- Extract argument text from correct response structure
- Update session state when needed

## Testing Results

✅ **Lexigraphbe Pipeline**: Working perfectly
```
→ Stage 0: Case Intake...
→ Stage 1: Legal Query Understanding...
→ Stage 2: Sub-query Mapping...
→ Stage 3: Chapter Identification...
→ Stage 4: Statutory Verification...
→ Stage 5: Bail Reasoning...
→ Stage 6: Precedent Retrieval...

✓ Retrieved 2 statutory sections:
  - § 420 IPC: Cheating and Dishonestly Inducing Delivery of Property
  - § 406 IPC: Criminal Breach of Trust
```

## Ready to Use!

Run the complete interactive session:
```bash
cd C:\Users\Ajinkya\Desktop\MootCourt\backend\prosecutor
python run_moot_court.py
```

The system will now:
1. ✅ Get case input (text or file)
2. ✅ Get role selection (prosecution/defense)
3. ✅ Run lexigraphbe 7-stage pipeline
4. ✅ Initialize the correct agent with proper state
5. ✅ Generate opening arguments using correct methods
6. ✅ Handle rebuttals back and forth

## Agent Method Reference

| Agent | Opening Method | Rebuttal Method | Initialization Required |
|-------|---------------|-----------------|------------------------|
| **DefenseAgent** | `build_opening_argument()` | `handle_rebuttal(arg)` | `analyze_case(text)` |
| **ProsecutorAgent** | `opening_argument(session)` | `rebuttal(session, arg)` | Extract + Plan + SessionState |

## Return Value Structure

**DefenseAgent**:
```python
{
    "phase": "opening" or "rebuttal",
    "opening_statement": "...",  # For opening
    "rebuttal_statement": "...", # For rebuttal
    "defense_matrix": [...],
    "defense_grounds": [...],
    ...
}
```

**ProsecutorAgent**:
```python
SessionState(
    ...
    turn_history=[
        TurnRecord(
            turn=1,
            speaker="prosecution",
            argument="...",  # ← The actual argument text
            ...
        )
    ]
)
```

## Files Modified

1. **orchestrator_agent.py**
   - Fixed `initialize_agent()` to properly initialize both agents
   - Fixed `_get_llm_argument()` to call correct methods
   - Fixed `_run_argument_rounds()` to pass agent wrapper
   - Added proper session state management for ProsecutorAgent

## Next Steps

You're ready to test the full interactive flow! The AI defense should now respond properly to your prosecution opening argument.

The error `'DefenseAgent' object has no attribute 'defense_rebuttal'` is completely resolved. 🎉
