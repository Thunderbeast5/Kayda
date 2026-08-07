# Judge Agent — Feature Specification
## Virtual Moot Court: Anticipatory Bail Platform

---
## 1. Overview

The Judge Agent is the **judicial decision-maker** of the Virtual Moot Court platform.  
It sits at the top of the courtroom agent hierarchy and is responsible for:

- Presiding over the entire anticipatory bail hearing
- Evaluating all inputs from every courtroom agent
- Asking targeted clarification questions
- Forming legally sound judicial findings
- Triggering dynamic legal retrieval when a new issue arises mid-hearing
- Passing verified findings to the Legal Verification Agent

> **Critical Design Constraint:**  
> The Judge does **not** retrieve legal knowledge independently.  
> It only evaluates verified information received from other agents.

---

## 2. Position in the Full Platform Architecture

```
Document Ingestion Agent
        ↓
Case Intake Agent
        ↓
Evidence Analyzer Agent ─────────────────────────┐
        ↓                                         │
LexiGraph Retrieval Agent → Precedent Agent → Bail Assessment Agent
        ↓                                         ↓
                    AI Courtroom Orchestrator
                    ↙        ↓        ↘
         Defence Agent  Prosecutor  Investigating Officer Agent
                    ↘        ↓        ↙
                      ► JUDGE AGENT ◄
                            ↓
                  Legal Verification Agent
                            ↓
                   Bail Order Generator
                            ↓
              Performance Evaluation & Feedback
```

The Judge Agent receives all context packages from upstream agents, presides over the multi-agent debate engine, and produces judicial findings for downstream processing.

---

## 3. Inputs

The Judge Agent receives the following from the AI Courtroom Orchestrator:

| Input | Source Agent | Description |
|---|---|---|
| `structured_case_context` | Case Intake Agent | FIR details, parties, timeline, legal regime |
| `evidence_context` | Evidence Analyzer Agent | Weapon, injuries, CCTV, contradictions, evidence strength |
| `legal_context_package` | LexiGraph Retrieval Agent | Applicable sections, acts, constitutional articles, bailable status, ingredients |
| `precedent_context` | Precedent Retrieval Agent | SC/HC judgments, ratio decidendi, bail outcomes |
| `bail_assessment_report` | Bail Assessment Agent | Gravity score, flight risk, custodial need, aggravating/mitigating factors |
| `defence_arguments` | Defence Agent | Opening, bail grounds, constitutional arguments, precedents, rebuttal |
| `prosecution_arguments` | Prosecutor Agent | Opposition to bail, gravity, custodial interrogation need, counter-arguments |
| `investigation_report` | Investigating Officer Agent | Investigation status, recovery, seized material, forensic reports |
| `courtroom_state_memory` | Shared Memory Store | All previous turns, questions asked, answers given, retrieved laws |

---

## 4. Processing — Internal Workflow

```
JUDGE RECEIVES ALL INPUTS
        │
        ▼
PHASE 1: Case Comprehension
  - Read structured_case_context
  - Read evidence_context
  - Read legal_context_package
  - Read bail_assessment_report
  - Read precedent_context
        │
        ▼
PHASE 2: Hearing Management
  - Signal Orchestrator: begin Defence Opening
  - Signal Orchestrator: begin Prosecution Opening
  - Evaluate arguments as they arrive
  - Read courtroom_state_memory after each turn
        │
        ▼
PHASE 3: Judicial Questioning
  - Identify gaps in arguments
  - Generate targeted clarification questions
  - Direct questions to: Defence / Prosecutor / IO Agent
  - Receive answers, update internal judicial analysis
        │
        ▼
PHASE 4: New Issue Detection
  - While evaluating arguments, detect if a new legal issue arises
  - If new issue detected → trigger Dynamic Retrieval Trigger
  - Receive Updated Legal Context Package
  - Continue hearing with updated knowledge
        │
        ▼
PHASE 5: Judicial Analysis
  - Balance liberty vs. investigation
  - Apply applicable IPC/BNS sections
  - Apply judicial precedents
  - Evaluate aggravating vs. mitigating factors
  - Score evidence strength
  - Form preliminary finding
        │
        ▼
PHASE 6: Final Submissions
  - Allow Defence final submission
  - Allow Prosecution final submission
        │
        ▼
PHASE 7: Judicial Findings
  - Produce structured judicial findings
  - Pass to Legal Verification Agent
```

---

## 5. Processing Logic — Judicial Analysis Framework

### 5.1 Bail Factor Evaluation

The Judge evaluates the following bail factors from the `bail_assessment_report`:

| Factor | Weight | Description |
|---|---|---|
| Gravity of Offence | High | Nature and severity of the alleged offence |
| Custodial Interrogation Need | High | Whether custodial presence is essential for investigation |
| Flight Risk | High | Likelihood of accused absconding if bail is granted |
| Criminal Antecedents | Medium | Prior convictions or pending cases |
| Witness Tampering Possibility | High | Risk of tampering with witnesses or evidence |
| Recovery Pending | Medium | Whether material recovery depends on custody |
| Cooperation with Investigation | Medium | Accused's prior cooperation level |
| Aggravating Factors | High | Circumstances worsening the case |
| Mitigating Factors | Medium | Circumstances favouring the accused |

### 5.2 Legal Application Framework

```
For each applicable section in legal_context_package:
    1. Verify all legal ingredients are satisfied by evidence
    2. Check bailable / non-bailable status
    3. Check if special restrictions apply (e.g. NDPS Section 37)
    4. Check applicable constitutional articles (e.g. Article 21)
    5. Apply ratio decidendi from precedent_context
```

### 5.3 Argument Comparison

```
Defence Score = Legal Validity + Evidence Linkage + Logic Coherence (each 0-10)
Prosecution Score = Legal Validity + Evidence Linkage + Logic Coherence (each 0-10)

If Prosecution Score < Sufficiency Threshold:
    → Ask clarification question to Prosecutor / IO Agent

If Defence Score < Sufficiency Threshold:
    → Ask clarification question to Defence
```

### 5.4 Liberty vs. Investigation Balance

The Judge must explicitly reason about:
- Is physical custody of the accused necessary for further investigation?
- Can conditions (surrender of passport, periodic reporting) substitute custody?
- Does the gravity of the offence override the right to liberty under Article 21?

---

## 6. Judicial Questioning — Question Generation Rules

The Judge generates targeted questions only when:

1. Evidence is insufficient to determine a bail factor
2. Arguments on both sides are contradictory on a material fact
3. A legal section cited has missing ingredient proof
4. Investigation status is unclear
5. A precedent cited needs clarification of applicability

**Question format:**
```
Target: [Defence / Prosecution / IO Agent]
Issue: [specific legal or factual gap]
Question: [precise, one-sentence factual or legal question]
```

**Maximum questions per hearing:** 5 (to simulate real court brevity)

---

## 7. Dynamic Retrieval Trigger

When the Judge detects a new legal issue mid-hearing:

```python
# Trigger condition
if new_legal_issue_detected(argument_text, existing_legal_context):
    trigger_dynamic_retrieval(
        issue=new_issue_description,
        target_agents=["LexiGraph Retrieval Agent", "Precedent Retrieval Agent"]
    )
    wait_for_updated_legal_context()
    resume_hearing_with_updated_context()
```

**Trigger conditions:**
- A section cited by Defence/Prosecution not present in `legal_context_package`
- A constitutional provision raised that was not retrieved initially
- A precedent cited that is not in `precedent_context`
- A procedural law question arises (BNSS / CrPC provisions)

---

## 8. Output — Judicial Findings

The Judge produces a structured `JudicialFindings` object:

```json
{
  "case_id": "string",
  "hearing_date": "DD/MM/YYYY",
  "judge_name": "AI Judge",
  "parties": {
    "applicant": "string",
    "respondent": "State of [X]"
  },
  "sections_applied": ["BNS 103", "BNS 111"],
  "constitutional_articles_applied": ["Article 21"],
  "precedents_applied": [
    {
      "case_name": "Gurbaksh Singh Sibbia v. State of Punjab",
      "citation": "1980 AIR 1632",
      "principle_applied": "Anticipatory bail is not a blanket order"
    }
  ],
  "evidence_evaluation": {
    "strength": "High / Medium / Low",
    "key_evidence": ["CCTV footage", "Medical report"],
    "contradictions_noted": ["Witness X contradicts FIR timeline"],
    "missing_evidence": ["Forensic report not filed"]
  },
  "bail_factor_analysis": {
    "gravity_of_offence": "High",
    "flight_risk": "Medium",
    "custodial_need": "Yes / No",
    "witness_tampering_risk": "High / Medium / Low",
    "antecedents": "None / Present",
    "mitigating_factors": ["First offence", "Family ties"],
    "aggravating_factors": ["Severity of injuries", "Absconding history"]
  },
  "argument_evaluation": {
    "defence_score": {"legal_validity": 7, "evidence_linkage": 6, "logic_coherence": 8, "total": 21},
    "prosecution_score": {"legal_validity": 8, "evidence_linkage": 7, "logic_coherence": 7, "total": 22}
  },
  "judicial_analysis": "Multi-paragraph reasoning text linking all factors...",
  "preliminary_finding": "Bail Likely Granted / Bail Likely Rejected / Inconclusive",
  "confidence": 78,
  "conditions_if_granted": [
    "Surrender passport",
    "Report to police station every Monday",
    "Not leave the country without permission"
  ],
  "questions_asked": [
    {
      "target": "IO Agent",
      "question": "Is custodial interrogation essential for recovery of any specific article?",
      "answer": "..."
    }
  ],
  "dynamic_retrieval_triggered": false,
  "new_issues_identified": []
}
```

**Output passed to:** Legal Verification Agent

---

## 9. LLM Prompting Strategy

### 9.1 System Prompt

```
You are the Honourable Judge presiding over an anticipatory bail hearing 
in an Indian court of law.

You do NOT retrieve legal knowledge independently.
You ONLY evaluate the verified information provided to you by other agents.

Your responsibilities:
1. Preside impartially over the hearing
2. Evaluate arguments on their legal and factual merits
3. Ask targeted clarification questions when needed
4. Apply applicable statutes and precedents to the facts
5. Balance the right to liberty (Article 21) against the needs of investigation
6. Form legally sound judicial findings

You must NOT hallucinate legal sections, case names, or citations.
You must ONLY apply sections and precedents explicitly provided in your input.
You must be concise, precise, and impartial.
Always cite the specific section/precedent/evidence that supports each finding.
```

### 9.2 Hearing Phase Prompts

**Phase 2 — Evaluating Arguments:**
```
CASE FACTS:
{structured_case_context}

EVIDENCE:
{evidence_context}

APPLICABLE LAW:
{legal_context_package}

PRECEDENTS:
{precedent_context}

BAIL ASSESSMENT:
{bail_assessment_report}

DEFENCE ARGUMENTS:
{defence_arguments}

PROSECUTION ARGUMENTS:
{prosecution_arguments}

INVESTIGATION REPORT:
{investigation_report}

COURTROOM HISTORY:
{courtroom_state_memory}

Your task: Evaluate the arguments above. 
Identify any factual or legal gaps requiring clarification.
List up to 3 targeted questions you would ask the parties.
Do NOT form a final finding yet.
```

**Phase 7 — Final Findings:**
```
[All context as above + answers to questions + final submissions]

Your task: Form the final judicial findings.
Apply the bail factor analysis framework.
Apply all applicable statutes and precedents provided.
Balance liberty vs. investigation.
Produce the complete JudicialFindings object in the JSON schema provided.
```

### 9.3 LLM Configuration

| Parameter | Value |
|---|---|
| Model | `llama-3.2-3b` |(ollama)
| Temperature | `0.1` (low — consistent, formal judicial reasoning) |
| Max Tokens | `4096` |

later on switch on open ai api key


---

## 10. State Machine — Judge Agent States

```
IDLE
  → RECEIVING_INPUTS       (on orchestrator signal)
  → COMPREHENDING_CASE     (reading all context packages)
  → HEARING_OPEN           (hearing begins)
  → EVALUATING_ARGUMENTS   (reading defence/prosecution/IO submissions)
  → QUESTIONING            (generating and asking clarification questions)
  → AWAITING_ANSWERS       (waiting for agent responses)
  → DETECTING_NEW_ISSUES   (checking for dynamic retrieval need)
  → AWAITING_RETRIEVAL     (if dynamic retrieval triggered)
  → HEARING_FINAL_SUBS     (final submissions phase)
  → FORMING_FINDINGS       (judicial analysis and finding generation)
  → FINDINGS_COMPLETE      (output ready for Legal Verification Agent)
```

---

## 11. Integration Points with Full Platform

| Agent | Interaction Type | Direction |
|---|---|---|
| AI Courtroom Orchestrator | Receives inputs, signals turns | Bidirectional |
| Courtroom State Memory | Reads all history, writes questions/findings | Bidirectional |
| Defence Agent | Receives arguments, asks questions | Bidirectional |
| Prosecutor Agent | Receives arguments, asks questions | Bidirectional |
| IO Agent | Receives report, asks questions | Bidirectional |
| Dynamic Retrieval Trigger | Triggers when new legal issue detected | Output |
| Legal Verification Agent | Sends JudicialFindings for verification | Output |
| Multi-Agent Debate Engine | Sequences the hearing | Coordinates |

---

## 12. File Structure (to be built)

```
backend/judge_agents/
├── JUDGE_AGENT.md                  ← this file
├── __init__.py
├── judge_agent.py                  ← main JudgeAgent class
├── prompts/
│   ├── system_prompt.py            ← system prompt constants
│   ├── hearing_phase_prompts.py    ← per-phase LLM prompts
│   └── question_generation.py     ← clarification question prompts
├── models/
│   ├── judicial_findings.py        ← JudicialFindings Pydantic model
│   ├── question_model.py           ← JudgeQuestion Pydantic model
│   └── hearing_state.py            ← HearingState enum + model
├── services/
│   ├── argument_evaluator.py       ← scores defence/prosecution arguments
│   ├── bail_factor_analyzer.py     ← evaluates bail factors from report
│   ├── precedent_applier.py        ← applies ratio decidendi to facts
│   ├── question_generator.py       ← generates targeted judicial questions
│   ├── issue_detector.py           ← detects new legal issues mid-hearing
│   └── findings_builder.py         ← assembles final JudicialFindings
├── tests/
│   ├── test_argument_evaluator.py
│   ├── test_bail_factor_analyzer.py
│   ├── test_question_generator.py
│   └── test_findings_builder.py
└── sample_inputs/
    └── sample_hearing_input.json   ← sample full input for testing
```

---

## 13. Implementation Phases

### Phase 1 — Core Judge (Week 1–2)
- [ ] `JudicialFindings` Pydantic model
- [ ] `HearingState` enum and state machine
- [ ] `JudgeAgent` class skeleton
- [ ] System prompt + hearing phase prompts
- [ ] Basic argument evaluation (scoring pass)
- [ ] Basic finding generation (verdict pass)
- [ ] Unit tests for scoring and verdict

### Phase 2 — Judicial Questioning (Week 2–3)
- [ ] `QuestionGenerator` service
- [ ] Gap detection logic (evidence gaps, argument contradictions)
- [ ] Max-questions guard (≤5 per hearing)
- [ ] Question routing to correct agent
- [ ] Answer ingestion and state update
- [ ] Integration with `CourtRoomStateMemory`

### Phase 3 — Dynamic Retrieval Integration (Week 3)
- [ ] `IssueDetector` service
- [ ] `DynamicRetrievalTrigger` interface
- [ ] Updated context ingestion
- [ ] Hearing resume after retrieval
- [ ] State machine update for `AWAITING_RETRIEVAL` state

### Phase 4 — Full Hearing Orchestration (Week 4)
- [ ] Integration with `AI Courtroom Orchestrator`
- [ ] Multi-agent debate engine sequencing
- [ ] Full end-to-end hearing test
- [ ] Output to `Legal Verification Agent`

### Phase 5 — Refinement (Week 5)
- [ ] Hallucination guard (no section cited outside `legal_context_package`)
- [ ] Confidence calibration
- [ ] Bail conditions generation
- [ ] Edge case handling (no precedents, missing evidence)
- [ ] Performance benchmarking on real bail case JSONs

---

## 14. Key Design Constraints

1. **No independent retrieval.** The Judge never calls LexiGraph or Pinecone directly.
2. **No hallucination.** Every section and precedent in `judicial_analysis` must exist in `legal_context_package` or `precedent_context`.
3. **No bail grant/rejection.** The Judge forms **findings**. The Bail Order Generator produces the final order.
4. **Impartiality.** The Judge prompt is calibrated to treat both sides equally.
5. **Consistency.** Low temperature (0.1) ensures formal, reproducible judicial reasoning.
6. **Auditability.** Every finding references the specific input (section, evidence item, precedent) that supports it.

---

## 15. Dependencies on Other Platform Components

| Dependency | Status | Notes |
|---|---|---|
| `AI Courtroom Orchestrator` | To be built | Manages turn assignment |
| `Courtroom State Memory` | To be built | Shared Redis / in-memory store |
| `Defence Agent` | Partial (existing `defense.py`) | Needs anticipatory bail prompt update |
| `Prosecutor Agent` | To be built | New agent |
| `IO Agent` | To be built | New agent |
| `Dynamic Retrieval Trigger` | To be built | Interfaces LexiGraph + Precedent agents |
| `Legal Verification Agent` | To be built | Downstream consumer of JudicialFindings |
| `LexiGraph Retrieval Agent` | Exists (`lexigraph_agent.py`) | Already production-ready |
| `Evidence Analyzer Agent` | Exists (`evidence.py`) | Already production-ready |
| `Precedent Retrieval Agent` | Partial (inside LexiGraph) | Needs standalone extraction |
| `Bail Assessment Agent` | To be built | New agent |
| (`llm_config.py`) | Exists | Reuse existing config |
| Firebase Firestore | Exists | Reuse existing client |

---

## 16. Sample Judicial Finding (Expected Output)

```json
{
  "case_id": "FIR/2025/PUNE/0123",
  "hearing_date": "07/08/2026",
  "judge_name": "AI Judge",
  "parties": {
    "applicant": "Rahul Sharma",
    "respondent": "State of Maharashtra"
  },
  "sections_applied": ["BNS 103", "BNS 111", "BNSS 484"],
  "constitutional_articles_applied": ["Article 21"],
  "precedents_applied": [
    {
      "case_name": "Gurbaksh Singh Sibbia v. State of Punjab",
      "citation": "1980 AIR 1632",
      "principle_applied": "Anticipatory bail may be granted with conditions"
    }
  ],
  "evidence_evaluation": {
    "strength": "Medium",
    "key_evidence": ["CCTV footage", "Medical report", "Witness statement"],
    "contradictions_noted": ["Witness A contradicts FIR timeline by 2 hours"],
    "missing_evidence": ["Forensic report not yet filed"]
  },
  "bail_factor_analysis": {
    "gravity_of_offence": "High",
    "flight_risk": "Low",
    "custodial_need": "No",
    "witness_tampering_risk": "Low",
    "antecedents": "None",
    "mitigating_factors": ["No prior criminal record", "Permanent resident", "Employed"],
    "aggravating_factors": ["Severity of alleged offence"]
  },
  "argument_evaluation": {
    "defence_score": {"legal_validity": 7, "evidence_linkage": 6, "logic_coherence": 8, "total": 21},
    "prosecution_score": {"legal_validity": 7, "evidence_linkage": 7, "logic_coherence": 6, "total": 20}
  },
  "judicial_analysis": "Having heard the learned counsel for both parties and perused the material on record, this Court finds that...",
  "preliminary_finding": "Bail Likely Granted",
  "confidence": 72,
  "conditions_if_granted": [
    "Applicant shall surrender passport to the IO",
    "Applicant shall report to the police station every Monday between 10:00 AM and 12:00 PM",
    "Applicant shall not leave the country without prior permission of this Court",
    "Applicant shall not contact or influence prosecution witnesses"
  ],
  "questions_asked": [
    {
      "target": "IO Agent",
      "question": "Is custodial interrogation of the applicant essential for any specific recovery?",
      "answer": "No specific recovery is currently pending that requires custodial presence."
    }
  ],
  "dynamic_retrieval_triggered": false,
  "new_issues_identified": []
}
```

---

## 17. Reference Documents

- Full Platform Architecture: `virtual_moot_court_architecture.drawio`
- Existing Judge Agent (criminal trial): `backend/agents/judge/judge.py`
- Existing LexiGraph Agent: `backend/agents/lexigraph/lexigraph_agent.py`
- Existing Evidence Analyzer: `backend/agents/evidence/evidence.py`
- Existing LLM Config: `backend/agents/config/llm_config.py`
- Existing State Model: `backend/agents/config/state.py`
- Orchestrator Graph: `backend/agents/orchestrator/orchestrator_graph.py`

---

*Last updated: 07/08/2026*  
*Feature owner: Kayda Platform Team*  
*Status: Specification Complete — Ready for Implementation Phase 1*
