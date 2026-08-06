# LexiGraph: Visual Flow Diagrams

## Diagram 1: The Problem We Solved

### Before: Single Statute Classification

```
┌─────────────────────────────┐
│   Case: NDPS Possession     │
│   50g Heroin Found          │
└──────────────┬──────────────┘
               │
               ▼
        ┌──────────────┐
        │  Classifier  │
        │ "Which Law?" │
        └──────────────┘
               │
               ▼
        ┌──────────────┐
        │   Output:    │
        │    NDPS      │
        │   (That's    │
        │    all we    │
        │    know!)    │
        └──────────────┘
               │
               ▼
        ┌──────────────┐
        │ Stages 3,4,5 │
        │    Confused  │
        │   "What do   │
        │   we do      │
        │   now?"      │
        └──────────────┘
```

**Problem:** We only know it's NDPS. But downstream stages need to know:
- Procedural rules (BNSS)
- Evidence rules (BSA)
- Constitutional constraints (Article 21)
- Bail rules (Section 37)

---

## Diagram 2: The Solution - Legal Regime Router

### After: Complete Legal Framework

```
┌─────────────────────────────┐
│   Case: NDPS Possession     │
│   50g Heroin Found          │
└──────────────┬──────────────┘
               │
               ▼
    ┌──────────────────────────┐
    │ Legal Regime Router      │
    │ (6 Layer Builder)        │
    └──────────┬───────────────┘
               │
       ┌───────┴──────┬────────┬─────────┬──────────┬──────────┐
       │              │        │         │          │          │
       ▼              ▼        ▼         ▼          ▼          ▼
    ┌─────────┐  ┌─────────┐ ┌──────┐ ┌────────┐ ┌──────────┐ ┌──────────┐
    │Layer 1: │  │Layer 2: │ │Layer │ │Layer 4:│ │Layer 5:  │ │Layer 6:  │
    │Substan- │  │Procedur │ │ 3:   │ │Constit │ │SpecialRs │ │Judicial  │
    │tive     │  │al       │ │Evide │ │utional │ │itions    │ │Guideline │
    │         │  │         │ │nce   │ │        │ │          │ │s         │
    │NDPS_20  │  │BNSS_176 │ │BSA_  │ │Article │ │Section   │ │Precedent │
    │         │  │ BNSS_   │ │25    │ │21      │ │37        │ │s         │
    │Offence: │  │182      │ │BSA_  │ │        │ │          │ │          │
    │Possess- │  │         │ │26    │ │Right to│ │Bail      │ │Sharad v. │
    │ion      │  │Invest-  │ │      │ │Life    │ │restrict- │ │State     │
    │         │  │igation: │ │Rules:│ │Equali- │ │ions      │ │          │
    │Elements:│  │DEA      │ │      │ │ty      │ │          │ │Rajagopal │
    │Poss,    │  │         │ │Burden│ │Protect │ │"Presum-  │ │v. State  │
    │Know,    │  │Cogniz.: │ │Beyond│ │ion of  │ │ption     │ │          │
    │Qty      │  │YES      │ │Reas. │ │Lib-    │ │against   │ │High Court│
    │         │  │         │ │Doubt │ │erty"   │ │bail"     │ │Guideline │
    │Conf:    │  │Bailable:│ │Conf: │ │        │ │Conf: 0.96│ │s         │
    │0.95     │  │Condition│ │0.97  │ │Conf:   │ │          │ │Conf: 0.85│
    │         │  │Conf:    │ │      │ │0.99    │ │          │ │          │
    │         │  │0.98     │ │      │ │        │ │          │ │          │
    └─────────┘  └─────────┘ └──────┘ └────────┘ └──────────┘ └──────────┘
               │
               └───────────────────────┬──────────────────────┘
                                       │
                                       ▼
                     ┌─────────────────────────────┐
                     │ ApplicableLegalGraph Output │
                     │ (Complete Legal Framework) │
                     │                             │
                     │ All 6 layers combined       │
                     │ Graph confidence: 0.85      │
                     │ READY for downstream stages │
                     └─────────────────────────────┘
                                       │
                ┌──────────────────────┼──────────────────────┐
                │                      │                      │
                ▼                      ▼                      ▼
         ┌────────────┐        ┌────────────┐        ┌────────────┐
         │ Stage 3:   │        │ Stage 4:   │        │ Stage 5:   │
         │ Section ID │        │ Verification│       │Bail Reason │
         │            │        │             │        │            │
         │ Knows all  │        │ Knows all   │        │ Knows all  │
         │ 6 layers   │        │ 6 layers    │        │ 6 layers   │
         │            │        │             │        │            │
         │ → Correct  │        │ → Correct   │        │ → Correct  │
         │ reasoning  │        │ reasoning   │        │ reasoning  │
         └────────────┘        └────────────┘        └────────────┘
                │                      │                      │
                └──────────────────────┼──────────────────────┘
                                       │
                                       ▼
                     ┌──────────────────────────┐
                     │   Bail Prediction        │
                     │   "LIKELY REJECTED"      │
                     │                          │
                     │ Reason: Section 37       │
                     │ commercial quantity      │
                     │ restrictions apply       │
                     └──────────────────────────┘
```

---

## Diagram 3: Layer-by-Layer Construction

### How Each Layer is Built

```
                    STAGE 1: Extract Indicators
                              │
                    ┌─────────┴─────────┐
                    │                   │
              Legal Concepts      Statutory Terms
              - Possession        - NDPS_20
              - Controlled        - Heroin
              - Substance         - Commercial Qty
              
                         │
                         ▼
                    
         ┌────────────────────────────────┐
         │ LAYER 1: Substantive Law       │
         ├────────────────────────────────┤
         │ Question: What offence?        │
         │ Answer: NDPS_20 Possession    │
         │ Confidence: 0.95               │
         └────────────────────────────────┘
                         │
                         ▼
         ┌────────────────────────────────┐
         │ LAYER 2: Procedural Law        │
         ├────────────────────────────────┤
         │ Question: How investigate?    │
         │ Answer: BNSS_176-182           │
         │ Authority: DEA                 │
         │ Confidence: 0.98               │
         └────────────────────────────────┘
                         │
                         ▼
         ┌────────────────────────────────┐
         │ LAYER 3: Evidence Law          │
         ├────────────────────────────────┤
         │ Question: What evidence?       │
         │ Answer: BSA_25, BSA_26         │
         │ Key: Seizing report            │
         │ Confidence: 0.97               │
         └────────────────────────────────┘
                         │
                         ▼
         ┌────────────────────────────────┐
         │ LAYER 4: Constitutional        │
         ├────────────────────────────────┤
         │ Question: What constraints?   │
         │ Answer: Article_21             │
         │ Principle: Right to Life       │
         │ Confidence: 0.99               │
         └────────────────────────────────┘
                         │
                         ▼
         ┌────────────────────────────────┐
         │ LAYER 5: Special Restrictions  │
         ├────────────────────────────────┤
         │ Execute Rules:                 │
         │ "IF commercial_qty THEN s37"   │
         │ → YES, 50g ≥ 1g threshold      │
         │ Apply: Section_37              │
         │ Confidence: 0.96               │
         └────────────────────────────────┘
                         │
                         ▼
         ┌────────────────────────────────┐
         │ LAYER 6: Judicial Guidelines   │
         ├────────────────────────────────┤
         │ Retrieve Precedents:           │
         │ - Sharad v. State              │
         │ - Rajagopal v. State           │
         │ Confidence: 0.85               │
         └────────────────────────────────┘
                         │
                         ▼
         ┌────────────────────────────────┐
         │ COMBINE ALL LAYERS             │
         │ Graph Confidence:              │
         │ min(0.95, 0.98, 0.97, 0.99,  │
         │     0.96, 0.85) = 0.85         │
         └────────────────────────────────┘
```

---

## Diagram 4: Dependency Graph Visualization

### How Statutes Connect

```
                    NDPS_20 (Possession)
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
    PROCEDURAL         EVIDENCE          CONSTITUTIONAL
    
    BNSS_176           BSA_25            Article_21
    (Search)           (Confessions)     (Life)
        │                  │                  │
    BNSS_182           BSA_26            Article_14
    (Investigation)    (Statements)      (Equality)
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                           ▼
                   SPECIAL RESTRICTIONS
                   
                   NDPS_Section_37
                   (Bail restriction)
                           │
                           ▼
                   JUDICIAL GUIDELINES
                   
                   Sharad v. State
                   Rajagopal v. State
```

**Key Insight:** Every statute depends on others. The router makes these dependencies explicit.

---

## Diagram 5: Data Flow Through LexiGraph Pipeline

### Complete System Perspective

```
Stage 0: CASE INTAKE
    │
    │ "Defendant found with 50g heroin"
    │ "Under police custody 3 days"
    │
    ▼
Stage 1: LEGAL QUERY UNDERSTANDING
    │
    │ Extract:
    │   - Concepts: [Possession, Substance]
    │   - Keywords: [Heroin, Commercial]
    │   - Terms: [NDPS_20]
    │
    ▼
Stage 2: SECTION CANDIDATE GENERATION
    │
    │ Output: [NDPS_20, IPC_120B]
    │ (But don't know what else applies)
    │
    ▼
    ┌─────────────────────────────────────────┐
    │ NEW Stage 2.5: LEGAL REGIME ROUTER      │
    ├─────────────────────────────────────────┤
    │ Input: Candidates + Indicators          │
    │                                         │
    │ Action: Build 6-Layer Legal Graph      │
    │   ├─ Layer 1: Substantive               │
    │   ├─ Layer 2: Procedural                │
    │   ├─ Layer 3: Evidence                  │
    │   ├─ Layer 4: Constitutional            │
    │   ├─ Layer 5: Special Restrictions      │
    │   └─ Layer 6: Judicial Guidelines       │
    │                                         │
    │ Output: ApplicableLegalGraph            │
    │ (Complete legal framework)              │
    └────────┬────────────────────────────────┘
             │
    ▼ ◄ KNOWS ALL 6 LAYERS NOW
Stage 3: SECTION IDENTIFICATION
    │
    │ Input: ApplicableLegalGraph
    │ Action: Enrich section texts
    │ Output: EnrichedSectionGraph
    │
    ▼
Stage 4: STATUTORY VERIFICATION
    │
    │ Input: EnrichedSectionGraph + Graph
    │ Action: Verify all layer elements
    │ Output: VerificationResult
    │
    ▼
Stage 5: BAIL REASONING
    │
    │ Input: VerificationResult + Graph
    │ Action: Apply bail framework
    │ Key: NDPS_Section_37 applies!
    │ Output: BailRecommendation
    │
    ▼
Stage 6: PRECEDENTS
    │
    │ Input: ApplicableLegalGraph
    │ Action: Retrieve relevant cases
    │ Output: PrecedentSet
    │
    ▼
FINAL OUTPUT
    │
    └─► "BAIL: LIKELY REJECTED"
        Reason: NDPS Section 37 commercial quantity restrictions
        Supporting: Article 21 protects, but Section 37 creates presumption
        Precedent: Sharad v. State confirms this reasoning
```

---

## Diagram 6: Rule Engine Execution

### How Deterministic Rules Work

```
Input Case: 50g Heroin

Rule 1: POCSO Exclusivity
├─ Condition: primary=POCSO AND age<18 AND sexual=true
├─ Case: NOT POCSO, skip this rule
└─ Status: NOT APPLICABLE

Rule 2: NDPS Commercial Quantity
├─ Condition: statute=NDPS AND qty >= threshold(drug)
├─ Check: NDPS? YES
├─ Check: qty=50g >= heroin_threshold(1g)? YES
├─ Action: Apply(NDPS_Section_37)
├─ Result: "Presumption against bail"
└─ Status: ✓ EXECUTED

Rule 3: Temporal Statute Selection
├─ Condition: date < 2023-07-01
├─ Check: date=2024-06-15 < 2023-07-01? NO
├─ Status: NOT APPLICABLE

Rule 4: Minor + Sexual = POCSO
├─ Condition: age<18 AND sexual_offence=true
├─ Check: NOT applicable (no minor, no sexual)
└─ Status: NOT APPLICABLE

═══════════════════════════════════════════════════════════

Result After Rule Execution:
✓ Rule 2 applied
✓ NDPS_Section_37 bail restrictions ACTIVE
✓ Presumption against bail CONFIRMED
```

---

## Diagram 7: Comparison - Before vs After

### Side by Side

```
┌────────────────────────────────┬────────────────────────────────┐
│        BEFORE (Old)            │         AFTER (New)             │
├────────────────────────────────┼────────────────────────────────┤
│ Case Input                     │ Case Input                     │
└────────────────┬────────────────────────────────┬────────────────┘
                 │                                │
                 ▼                                ▼
        ┌─────────────────┐            ┌─────────────────────────┐
        │ Statute Router  │            │ Legal Regime Router     │
        │ (Classifier)    │            │ (Framework Builder)     │
        └────────┬────────┘            └───────────┬─────────────┘
                 │                                │
                 ▼                                ▼
        ┌─────────────────┐            ┌─────────────────────────┐
        │ Output: NDPS    │            │ Output:                 │
        │                 │            │ ├─ Substantive: NDPS_20 │
        │ (That's all)    │            │ ├─ Procedural: BNSS    │
        │                 │            │ ├─ Evidence: BSA       │
        │ Downstream:     │            │ ├─ Constitutional: A21 │
        │ "Now what?"     │            │ ├─ Special: Section_37 │
        │                 │            │ └─ Precedents: [...]   │
        └─────────────────┘            │                         │
                 │                     │ Downstream:             │
                 │                     │ "Complete framework!"   │
                 │                     └─────────────────────────┘
                 │                                │
    Stage 3,4,5: │                    Stage 3,4,5: │
    Guessing     │                    Confident   │
    Incomplete   │                    Complete    │
    Reasoning    │                    Reasoning   │
                 │                                │
                 ▼                                ▼
        Bail Decision: ???            Bail Decision: REJECTED
        (Unclear why)                 (Clear: Section 37)
        Confidence: Low               Confidence: High
└────────────────────────────────────────────────────────────────┘
```

---

## Diagram 8: Legal Ontology Example

### Semantic Knowledge Graph

```
                CONTROLLED_SUBSTANCE (Root)
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
      NARCOTIC      PSYCHOTROPIC    SCHEDULED_CHEMICAL
          │              │              │
          │              │              │
    ┌─────┴─────┐   ┌────┴────┐    ┌──┴─────┐
    │            │   │         │    │        │
   HEROIN    MORPHINE MDMA  LSD  PRECURSOR CHEMICAL
    │            │
    ▼            ▼
Statutes:    Statutes:
├─ NDPS_20   ├─ NDPS_20
├─NDPS_29    ├─ NDPS_8
└─NDPS_31    └─ NDPS_9
    
Elements:       Elements:
├─ Possession   ├─ Possession
├─ Knowledge    ├─ Knowledge
└─ Intent       └─ Intent

Offence Type:   Offence Type:
└─Possession    └─ Possession
                   or Trafficking

Bail Impact:    Bail Impact:
└─Section_37    └─ Section_37

Precedent:      Precedent:
└─Sharad v. St  └─ Rajagopal v. St
```

---

## Diagram 9: Confidence Scoring

### How Confidence Propagates

```
Layer 1: Substantive - Confidence 0.95
    ├─ Section code exact match: 0.95
    ├─ Reason: "NDPS_20" explicitly mentioned
    └─ Status: HIGH

Layer 2: Procedural - Confidence 0.98
    ├─ Procedure deterministic: 0.98
    ├─ Reason: "BNSS always applies to criminal cases"
    └─ Status: VERY HIGH

Layer 3: Evidence - Confidence 0.97
    ├─ Evidence rules deterministic: 0.97
    ├─ Reason: "BSA sections are prescribed"
    └─ Status: VERY HIGH

Layer 4: Constitutional - Confidence 0.99
    ├─ Constitutional rules deterministic: 0.99
    ├─ Reason: "Article 21 always applies"
    └─ Status: VERY HIGH

Layer 5: Special Restrictions - Confidence 0.96
    ├─ Rule matches case: 0.96
    ├─ Reason: "Commercial quantity rule applies, 50g >= 1g"
    └─ Status: VERY HIGH

Layer 6: Judicial Guidelines - Confidence 0.85
    ├─ Precedent relevance: 0.85
    ├─ Reason: "Precedents are from similar cases"
    └─ Status: HIGH

═════════════════════════════════════════════════════════════

Graph Confidence = MIN(all layer confidences)
                 = MIN(0.95, 0.98, 0.97, 0.99, 0.96, 0.85)
                 = 0.85

Interpretation:
├─ 0.85 means: "We're 85% confident about this complete framework"
├─ Weakest link: Judicial Guidelines (0.85)
├─ Decision: PROCEED WITH CONFIDENCE
└─ Readiness: 100% ready for downstream stages
```

---

## Summary Visual

### The Transformation

```
                    OLD ARCHITECTURE
                           │
              Single Statute Classifier
                           │
                    "What's the law?"
                    "Answer: NDPS"
                           │
                    Incomplete Output
                           │
        Downstream Confused (What about procedures?)


                    NEW ARCHITECTURE
                           │
              Multi-Layer Legal Regime Router
                           │
            "What's the complete legal framework?"
                           │
        ┌─────────────────┬─────────────────┐
        │                 │                 │
     Substantive      Procedural      Evidence
        │                 │                 │
     Constitutional    Special         Judicial
                    Restrictions      Guidelines
                           │
                 Complete Legal Graph
                           │
        Downstream Confident (Everything is clear!)
```

