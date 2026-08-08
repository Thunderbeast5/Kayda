# Prosecutor Agent - Interactive Workflow

## Overview
The prosecutor agent now follows a simplified, interactive workflow focused on prosecuting crimes step-by-step.

## Workflow Steps

### Step 1: Case Analysis & Crime Identification
- User enters case facts in terminal (press ENTER twice to submit)
- Prosecutor analyzes the case using lexigraphbe Stage 1 pipeline
- Identifies primary, secondary, and ancillary crimes
- Shows prosecution theory

**Output:**
- Primary Crime
- Prosecution Theory
- List of identified crimes with severity levels

### Step 2: Opening Argument
- Queries lexigraphbe pipeline (Stages 0-4) for statutory sections for the **primary crime only**
- Retrieves applicable IPC/BNS sections with ingredients
- Builds opening argument with:
  - Elements to prove
  - Retrieved statutory sections
  - Prosecution strategy

**Output:**
- Prosecution theory
- Primary charges with elements
- Retrieved sections (top 3 shown)
- Strategy for proving each charge

### Step 3: Defense Rebuttal (Interactive)
- Waits for user to enter defense argument in terminal
- User types defense counsel's argument
- Press ENTER twice to submit

### Step 4: Prosecution Counter-Arguments
- Analyzes defense argument
- Identifies which crime the defense is attacking
- Queries lexigraphbe for additional sections if needed (cached if already retrieved)
- Generates counter-arguments to rebut defense claims

**Output:**
- Focused crime being defended
- List of counter-arguments
- Additional sections retrieved (if any)

## Usage

```bash
cd backend
python prosecutor/prosecutor.py
```

Then follow the prompts:
1. Paste case facts → ENTER twice
2. Review opening argument
3. Paste defense argument → ENTER twice
4. Review prosecution rebuttal

## LLM Provider

Currently using **Groq** (configured in `.env`):
- Stages 0-2: `llama-3.1-8b-instant` (fast, lightweight)
- Stages 5-7: `llama-3.3-70b-versatile` (reasoning)

## Key Features

✅ No hardcoded examples or test cases  
✅ Interactive terminal workflow  
✅ Selective lexigraphbe querying (only for needed crimes)  
✅ Caching to avoid redundant queries  
✅ Clean output without JSON dumps  
✅ Hallucination prevention (prompts warn against copying examples)

## Files

- `prosecutor/prosecutor.py` - Main agent
- `prosecutor/test_assault_case.py` - Automated test
- `prosecutor/WORKFLOW.md` - This file
