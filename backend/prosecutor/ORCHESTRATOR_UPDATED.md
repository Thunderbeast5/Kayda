# Orchestrator Agent - Updated Architecture

## Overview

The orchestrator agent has been completely rewritten to serve as the **main backbone** of the moot court system, as per your requirements.

## New Flow

```
1. Get Case Input from User
   ↓
2. Ask User to Choose Role (Prosecution / Defense)
   ↓
3. Run Lexigraphbe 7-Stage Pipeline
   ↓
4. Pass Sections to Prosecutor or Defense Agent
   ↓
5. Facilitate Back-and-Forth Arguments
   (Student ↔ LLM)
```

## Key Features

### 1. Interactive Case Input
```python
orchestrator.get_case_input()
```
- User can input via file (PDF/TXT) or paste text directly
- CLI-based with Rich formatting

### 2. Role Selection
```python
orchestrator.get_role_choice()
```
- User chooses: `prosecution` or `defense`
- LLM automatically plays opposite role

### 3. Lexigraphbe Integration
```python
orchestrator.run_lexigraphbe_pipeline(case_text)
```
- Runs complete 7-stage pipeline:
  - Stage 0: Case Intake
  - Stage 1: Legal Query Understanding
  - Stage 2: Sub-query Mapping
  - Stage 3: Chapter Identification
  - Stage 4: Statutory Verification
  - Stage 5: Bail Reasoning
  - Stage 6: Precedent Retrieval
- Returns `OrchestratorResult` with verified sections
- Falls back to GPT simulation if lexigraphbe not available

### 4. Agent Initialization
```python
orchestrator.initialize_agent(role)
```
- Initializes prosecutor or defense agent
- Passes retrieved sections to agent

### 5. Argument Rounds
```python
orchestrator._run_argument_rounds(llm_agent)
```
- Coordinates back-and-forth between student and LLM
- Opening arguments → Rebuttals → Counter-rebuttals
- Uses retrieved sections for formulating arguments

## Usage

### Command Line
```bash
cd backend/prosecutor
python run_moot_court.py
```

### Programmatic
```python
from orchestrator_agent import OrchestratorAgent

orchestrator = OrchestratorAgent()
orchestrator.run_moot_court_session()
```

## Architecture

### OrchestratorAgent Class

#### Main Method
```python
def run_moot_court_session(self):
    """Main entry point: orchestrate complete moot court session."""
    # Step 1: Get case input
    self.case_text = self.get_case_input()
    
    # Step 2: Get role choice
    self.student_role = self.get_role_choice()
    self.llm_role = opposite of student_role
    
    # Step 3: Run lexigraphbe
    self.sections = self.run_lexigraphbe_pipeline(self.case_text)
    
    # Step 4: Initialize agent for LLM side
    llm_agent = self.initialize_agent(self.llm_role)
    
    # Step 5: Run argument rounds
    self._run_argument_rounds(llm_agent)
```

#### Helper Methods

**get_case_input() → str**
- Interactive CLI prompt for case input
- Supports file path or direct text input

**get_role_choice() → "prosecution" | "defense"**
- Interactive CLI prompt for role selection
- Returns chosen role

**run_lexigraphbe_pipeline(case_text: str) → OrchestratorResult**
- Runs complete 7-stage lexigraphbe pipeline
- Displays retrieved sections in Rich table
- Returns structured result with verified sections

**initialize_agent(role: str) → Agent**
- Initializes ProsecutorAgent or DefenseAgent
- Passes sections to agent

**_run_argument_rounds(llm_agent)**
- Manages turn-taking between student and LLM
- Handles opening arguments and rebuttals
- Continues until student types 'done'

**_get_student_argument(arg_type: str, previous_argument: str = None) → str**
- Gets argument from student via CLI
- Multi-line input (press Enter twice to submit)
- Returns empty string if user types 'done'

**_get_llm_argument(agent, arg_type: str, previous_argument: str = None) → str**
- Gets argument from LLM agent
- Calls appropriate agent method based on arg_type
- Returns formatted argument

### Legacy Compatibility

The orchestrator maintains backward compatibility with existing code:

```python
# Legacy method (still works)
def run(self, orchestrator_input: OrchestratorInput) -> OrchestratorResult:
    """Legacy method for compatibility."""
    return self.run_lexigraphbe_pipeline(orchestrator_input.case_text)

# Legacy method (still works)
def query_for_fact(self, fact_text, context_text, existing_sections) -> OrchestratorResult:
    """Targeted pipeline for specific fact."""
    # Composes query and runs pipeline
```

## Integration with Prosecutor & Defense Agents

### Prosecutor Agent
```python
from prosecutor_agent import ProsecutorAgent

agent = ProsecutorAgent()
# Sections are passed from orchestrator
agent.opening_argument()  # Returns formatted argument
agent.rebuttal(defense_arg)  # Returns rebuttal
```

### Defense Agent
```python
from defense import DefenseAgent

agent = DefenseAgent()
# Sections are passed from orchestrator  
agent.opening_bail_argument()  # Returns formatted argument
agent.defense_rebuttal(prosecution_arg)  # Returns rebuttal
```

## Lexigraphbe Pipeline Flow

```
Case Text
    ↓
Stage 0: Case Intake
    ↓ CaseContextObject
Stage 1: Legal Query Understanding
    ↓ LegalQueryObject
Stage 2: Sub-query Mapping
    ↓ BatchedMappingResponse
Stage 3: Chapter Identification
    ↓ ChapterIdentificationObject
Stage 4: Statutory Verification
    ↓ StatutoryVerificationObject
Stage 5: Bail Reasoning
    ↓ BailRecommendation
Stage 6: Precedent Retrieval
    ↓ PrecedentResponse
    ↓
OrchestratorResult (verified_sections)
    ↓
Prosecutor/Defense Agent
```

## Example Session Flow

```
User starts: python run_moot_court.py

┌─────────────────────────────────────────┐
│ Step 1: Case Input                      │
│ How would you like to input the case?   │
│   1. File (PDF/TXT)                     │
│   2. Paste text                         │
└─────────────────────────────────────────┘
> User chooses and provides case

┌─────────────────────────────────────────┐
│ Step 2: Role Selection                  │
│ Which role do you want to play?         │
│   - prosecution                         │
│   - defense                             │
└─────────────────────────────────────────┘
> User chooses 'defense'

┌─────────────────────────────────────────┐
│ Step 3: Running Lexigraphbe Pipeline   │
│ → Stage 0: Case Intake...              │
│ → Stage 1: Legal Query...              │
│ → Stage 2: Sub-query Mapping...        │
│ → Stage 3: Chapter Identification...   │
│ → Stage 4: Statutory Verification...   │
│ → Stage 5: Bail Reasoning...           │
│ → Stage 6: Precedent Retrieval...      │
│                                         │
│ ✓ Retrieved 3 statutory sections:      │
│   § 420 IPC - Cheating                 │
│   § 406 IPC - Criminal Breach of Trust │
│   § 438 CrPC - Anticipatory Bail       │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ Step 4: Initializing PROSECUTION Agent  │
│ → Prosecutor analyzing case...         │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ Step 5: Moot Court Session Started     │
│ Student Role: DEFENSE                   │
│ AI Role: PROSECUTION                    │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ Turn 1: AI OPENING (PROSECUTION)        │
│                                         │
│ [Prosecutor presents opening argument   │
│  citing § 420 and § 406...]            │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ Turn 2: YOUR REBUTTAL (DEFENSE)        │
│ Enter your rebuttal:                    │
└─────────────────────────────────────────┘
> User enters defense argument
> Press Enter twice to submit

┌─────────────────────────────────────────┐
│ Turn 3: AI REBUTTAL (PROSECUTION)       │
│                                         │
│ [Prosecutor responds to defense...]     │
└─────────────────────────────────────────┘

... continues until user types 'done'
```

## Key Improvements

### Before (Old Orchestrator)
- ❌ Just ran lexigraphbe and returned sections
- ❌ No user interaction
- ❌ No role selection
- ❌ No argument facilitation
- ❌ Separate runner needed

### After (New Orchestrator)
- ✅ Complete end-to-end flow
- ✅ Interactive CLI with Rich formatting
- ✅ User chooses role (prosecution/defense)
- ✅ Coordinates between student and LLM
- ✅ Self-contained orchestration
- ✅ Passes sections to agents automatically
- ✅ Manages turn-taking
- ✅ Maintains backward compatibility

## Files Modified

1. **orchestrator_agent.py** - Complete rewrite
   - Added interactive methods
   - Added session management
   - Added argument coordination

2. **run_moot_court.py** - New simple runner
   - Single entry point
   - Just calls orchestrator.run_moot_court_session()

## Dependencies

- Rich (for CLI formatting)
- OpenAI (for LLM calls)
- lexigraphbe (for statutory analysis)
- prosecutor_agent.py (for prosecution side)
- defense.py (for defense side)

## Configuration

Set in `.env` file:
```
OPENAI_API_KEY=your_key_here
```

## Next Steps

### To Run
```bash
cd backend/prosecutor
python run_moot_court.py
```

### To Integrate with FastAPI
```python
from prosecutor.orchestrator_agent import OrchestratorAgent

@app.post("/moot-court/start")
async def start_session(case_text: str, role: str):
    orchestrator = OrchestratorAgent()
    orchestrator.case_text = case_text
    orchestrator.student_role = role
    orchestrator.llm_role = "defense" if role == "prosecution" else "prosecution"
    
    # Run lexigraphbe
    sections = orchestrator.run_lexigraphbe_pipeline(case_text)
    
    return {"sections": sections.verified_sections}
```

## Summary

The orchestrator is now a complete **backbone** that:
1. ✅ Gets case input from user
2. ✅ Gets role choice from user  
3. ✅ Runs lexigraphbe 7-stage pipeline
4. ✅ Passes sections to prosecutor/defense agents
5. ✅ Facilitates back-and-forth arguments

It's ready to use immediately with the simple command:
```bash
python run_moot_court.py
```
