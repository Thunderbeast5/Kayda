# STATUTE ROUTING ENGINE: RESEARCH-GRADE ARCHITECTURE DESIGN

## Executive Summary

The Statute Routing Engine (SRE) is a critical upstream component that determines which statute(s) govern a criminal case **before** any section identification, mapping, or bail reasoning occurs. It serves as the **single source of truth** for all downstream processing stages, eliminating systemic errors caused by incorrect statute attribution.

---

## 1. PURPOSE

**Core Purpose**

Enable the LexiGraph anticipatory bail system to correctly handle:
- IPC (Indian Penal Code)
- BNS (Bharatiya Nyaya Sanhita)
- Special Acts (NDPS, POCSO, PMLA, UAPA, IT Act, etc.)

Without conflating them or attempting invalid cross-statute mappings.

**Problem Statement**

Current pipeline treats all offences as IPC/BNS candidates, causing:
- NDPS sections incorrectly mapped to IPC equivalents (none exist)
- POCSO offences treated under IPC instead of POCSO framework
- Wrong bail reasoning applied (IPC bail rules ≠ Special Act bail rules)
- Incorrect confidence scoring
- Unreliable precedent retrieval

**Solution Approach**

Insert a deterministic routing stage that:
1. Analyzes candidate sections from Stage 2
2. Detects statutory indicators (keywords, concepts, triggers)
3. Validates against known statute repositories
4. Uses LLM only for final tie-breaking
5. Outputs an immutable routing decision
6. Gates all downstream statute-specific logic

---

## 2. RESPONSIBILITIES

The Statute Routing Engine is responsible for:

### 2.1 Statute Detection
- Identify all applicable statutes from candidate sections and detected concepts
- Distinguish between primary (governing) and secondary (overlapping) statutes
- Detect mixed-statute scenarios (e.g., NDPS + IPC)

### 2.2 Confidence Scoring
- Assign confidence to each detected statute
- Identify when confidence falls below actionable threshold
- Flag ambiguous cases for manual review

### 2.3 Mapping Policy Enforcement
- Determine whether IPC↔BNS mapping is applicable
- Enforce rule: IPC/BNS only can map; Special Acts cannot
- Prevent invalid mappings

### 2.4 Repository Selection
- Select the appropriate repository (IPC, BNS, SPECIAL_ACTS, etc.)
- Ensure all sections align with selected repository
- Prevent cross-repository contamination

### 2.5 Special Bail Rules
- Identify statute-specific bail frameworks
- Flag when standard bail reasoning doesn't apply
- Record special rules (e.g., NDPS Section 37, POCSO bail provisions)

### 2.6 Routing Validation
- Validate routing output against consistency rules
- Reject invalid combinations
- Ensure no contradictions before passing to downstream stages

### 2.7 Decision Immutability
- Ensure downstream stages cannot re-route or override decisions
- Make routing a contract, not a suggestion

---

## 3. INPUTS

The Statute Routing Engine receives:

```python
# Core Input Object
StatuteRoutingInput:
    case_context: CaseContextObject
        - case_id
        - jurisdiction
        - date_of_offence
        - nature_of_accusation
        
    legal_query: LegalQueryObject
        - original_query_text
        - cleaned_query
        - extracted_concepts (list of legal terms)
        - extracted_keywords (list of domain keywords)
        
    candidate_sections: List[SectionCandidate]
        - section_code (e.g., "IPC_302", "NDPS_29", "POCSO_4")
        - section_text
        - detected_statute
        - confidence_from_stage2
        - legal_concepts_detected
        
    detected_concepts: List[LegalConcept]
        - concept_name
        - concept_type (element, procedure, bail_framework)
        - source_statute (or None if ambiguous)
        - extracted_from (text span or section)
```

**Key Constraints on Input**

- Must be non-null, cleaned, and validated
- Candidate sections must come from Stage 2 (section candidate generation)
- Extracted concepts must be normalized to canonical legal terminology
- No raw text processing—only structured data

---

## 4. OUTPUTS

The Statute Routing Engine produces:

```python
StatuteRoutingObject:
    primary_statute: str  # e.g., "NDPS", "IPC", "POCSO"
    secondary_statutes: List[str]  # e.g., ["IPC"] if NDPS + IPC
    all_detected_statutes: List[str]  # All candidates considered
    
    confidence: float  # 0.0 to 1.0
    confidence_breakdown: Dict[str, float]  # Per-statute confidence
    
    routing_reason: str  # Human-readable explanation
    detection_evidence: Dict[str, any]  # What triggered each statute
    
    allow_ipc_bns_mapping: bool  # Gate for cross-statute mapping
    enable_bns_parallel: bool  # Whether to generate BNS equivalents
    
    special_bail_rule: Optional[str]  # e.g., "NDPS_SECTION_37"
    special_framework: Optional[str]  # e.g., "POCSO_BAIL_FRAMEWORK"
    
    repository: str  # e.g., "IPC", "SPECIAL_ACTS", "CONSOLIDATED"
    repository_path: str  # Path to specific statute database
    
    manual_review_required: bool
    manual_review_reason: Optional[str]
    
    routing_valid: bool  # False if validation fails
    validation_errors: List[str]
    
    timestamp: datetime
    routing_version: str  # For future evolution
```

---

## 5. ROUTING ALGORITHM

The routing algorithm executes in phases:

### Phase 1: Extraction
Extract all indicators from input:
- Section codes from candidates
- Keywords from query
- Concepts detected
- Metadata (jurisdiction, nature of accusation)

### Phase 2: Initial Statute Scoring
For each statute in supported repertoire:
- Check if any section code matches
- Check if triggers/keywords match
- Check if detected concepts align
- Compute interim confidence

### Phase 3: Conflict Resolution
If multiple statutes score high:
- Apply statute priority rules
- Detect mixed-statute legitimacy
- Flag contradictions

### Phase 4: Repository Validation
Validate each statute against its repository definition:
- Verify section codes exist in statute
- Verify legal concepts are valid under that statute
- Check for cross-statute contamination

### Phase 5: LLM Validation (if needed)
If confidence < 0.75 after phase 4:
- Construct validation prompt
- Ask LLM to confirm/refute detected statutes
- Use LLM confidence as tie-breaker only

### Phase 6: Policy Application
Apply routing rules:
- Set `allow_ipc_bns_mapping` based on primary statute
- Identify special bail frameworks
- Set repository selection
- Flag manual review if needed

### Phase 7: Validation & Output
Validate entire output against consistency rules:
- No contradictions
- Repository matches primary statute
- Special rules are legitimate
- Output is complete

---

## 6. DECISION TREE

```
START: Candidate Sections Received
│
├─ Step 1: Extract Section Codes
│  │
│  └─ Do any section codes belong to SPECIAL_ACTS?
│     │
│     ├─ YES → Go to Step 2a
│     └─ NO → Go to Step 2b
│
├─ Step 2a: Special Act Detected
│  │
│  └─ Are there also IPC/BNS sections?
│     │
│     ├─ YES → Mixed-Statute Case (Step 5)
│     └─ NO → Single Special Act (Step 3)
│
├─ Step 2b: Only IPC/BNS Sections
│  │
│  └─ Are there BNS sections?
│     │
│     ├─ YES → Is jurisdiction modern BNS state?
│     │  │
│     │  ├─ YES → Primary=BNS, Secondary=IPC (Step 4)
│     │  └─ NO → Primary=IPC, Secondary=BNS (Step 4)
│     │
│     └─ NO → Primary=IPC, No Secondary (Step 4)
│
├─ Step 3: Single Special Act
│  │
│  ├─ Confidence = Section Code Match (high)
│  ├─ allow_ipc_bns_mapping = FALSE
│  ├─ repository = SPECIAL_ACTS
│  ├─ special_bail_rule = Look up in statute config
│  └─ Go to Step 7
│
├─ Step 4: IPC/BNS Only
│  │
│  ├─ Confidence = Section Code Match (high)
│  ├─ allow_ipc_bns_mapping = TRUE
│  ├─ enable_bns_parallel = TRUE (if BNS present)
│  ├─ repository = IPC (or BNS)
│  ├─ special_bail_rule = None (standard CrPC/BNSS applies)
│  └─ Go to Step 7
│
├─ Step 5: Mixed-Statute Case
│  │
│  ├─ primary_statute = Apply Priority Rules
│  ├─ secondary_statutes = Others
│  ├─ allow_ipc_bns_mapping = TRUE only for IPC/BNS secondaries
│  ├─ repository = Select based on primary_statute
│  ├─ special_bail_rule = From primary_statute
│  └─ Go to Step 7
│
├─ Step 6: Ambiguous Case (No Clear Match)
│  │
│  ├─ Trigger LLM Validation
│  ├─ If LLM confidence < 0.75 → manual_review_required = TRUE
│  ├─ Else → Use LLM decision
│  └─ Go to Step 7
│
├─ Step 7: Output Validation
│  │
│  ├─ Check for contradictions
│  ├─ Validate repository selection
│  ├─ Validate special_bail_rule legitimacy
│  ├─ If validation fails → Set routing_valid=FALSE, record errors
│  └─ Return StatuteRoutingObject
│
└─ END: Routing Decision Complete
```

---

## 7. HYBRID DETECTION STRATEGY

Detection priority (used to build initial confidence):

```
Priority 1: Section Code Matching (Weight: 0.40)
├─ Extract section codes from candidates
├─ Normalize format (e.g., "IPC 302" → "IPC_302")
├─ Query statute registry
├─ If found → Confidence += 0.40
└─ If multiple statutes match → Continue to Priority 2

Priority 2: Detected Legal Concepts (Weight: 0.30)
├─ Cross-reference detected concepts against statute ontology
├─ Example: "narcotic substance" → NDPS indicator
├─ Example: "minor" + "sexual" → POCSO indicator
├─ Count concept matches per statute
├─ If statute-specific concepts present → Confidence += 0.30
└─ Normalize by number of concepts

Priority 3: Trigger Keywords (Weight: 0.20)
├─ Query trigger dictionary (configured, not hard-coded)
├─ Example: "ganja", "charas" → NDPS
├─ Example: "scheduled caste" → SC/ST Act
├─ Count keyword matches per statute
├─ If triggers present → Confidence += 0.20
└─ Cap at 0.20 to avoid over-weighting keywords

Priority 4: Repository Validation (Weight: 0.05)
├─ Query statute repository
├─ Verify that detected statute actually has these sections
├─ Verify legal concepts are valid under statute
├─ If validation passes → Confidence += 0.05
└─ If validation fails → Red flag, investigate

Priority 5: LLM Reasoning (Weight: 0.05)
├─ Triggered only if overall confidence < 0.75
├─ Ask LLM: "Which statute(s) govern this case?"
├─ Use LLM response as tie-breaker
├─ LLM confidence becomes final confidence (cap at 0.05 addition)
└─ If LLM also uncertain → manual_review_required = TRUE
```

**Example Detection Walkthrough**

Case: "Possession of 50 grams of heroin"

```
Candidate Sections: ["NDPS_20", "IPC_120B"]

Priority 1: Section Code Matching
├─ NDPS_20 found in NDPS repository → +0.40
├─ IPC_120B found in IPC repository → +0.40
└─ Both detected, continue

Priority 2: Detected Legal Concepts
├─ Concept: "controlled substance" → NDPS-specific → +0.30 to NDPS
├─ Concept: "criminal conspiracy" → Both NDPS & IPC → +0.15 each
└─ NDPS concept count higher

Priority 3: Trigger Keywords
├─ "heroin" is in NDPS trigger dictionary → +0.20 to NDPS
├─ No IPC-specific triggers → +0 to IPC
└─ NDPS leads

Priority 4: Repository Validation
├─ NDPS_20 validates ✓ → +0.05
├─ IPC_120B validates ✓ → +0.05
└─ No contradictions

Priority 5: LLM Reasoning
├─ NDPS confidence: 0.40 + 0.30 + 0.20 + 0.05 = 0.95 (no LLM needed)
├─ IPC confidence: 0.40 + 0.15 + 0.00 + 0.05 = 0.60
└─ Clear winner: NDPS

Result:
├─ primary_statute: "NDPS"
├─ secondary_statutes: ["IPC"]
├─ confidence: 0.95
└─ allow_ipc_bns_mapping: FALSE (NDPS is primary)
```

---

## 8. CONFIDENCE SCORING

Confidence is a composite metric used to determine routing certainty.

### 8.1 Scoring Formula

```
confidence(statute) = Σ(priority_i × weight_i) for all priorities

where:
  priority_1_score = (matched_sections / total_sections) × 0.40
  priority_2_score = (concept_matches / concept_threshold) × 0.30
  priority_3_score = (trigger_matches / trigger_threshold) × 0.20
  priority_4_score = repository_validation_score × 0.05
  priority_5_score = llm_confidence × 0.05
  
Final confidence = min(sum of scores, 1.0)
```

### 8.2 Confidence Thresholds

```
Confidence ≥ 0.90 → High confidence
├─ Proceed immediately
├─ No LLM consultation needed
└─ Routing is final

Confidence 0.75 - 0.89 → Medium confidence
├─ Acceptable, proceed with validation
├─ LLM consultation optional
└─ Flag for monitoring

Confidence 0.60 - 0.74 → Low confidence
├─ Trigger LLM validation
├─ If LLM agrees, proceed
└─ If LLM also uncertain, manual review

Confidence < 0.60 → Very low confidence
├─ Automatic manual review
├─ Do NOT attempt to route
└─ Return with manual_review_required=TRUE
```

### 8.3 Confidence Breakdown

For transparency, output detailed breakdown:

```python
confidence_breakdown = {
    "NDPS": {
        "section_code_match": 0.40,
        "concept_match": 0.28,
        "trigger_match": 0.18,
        "repository_validation": 0.05,
        "llm_boost": 0.00,
        "total": 0.91,
        "threshold_status": "EXCEEDS_THRESHOLD"
    },
    "IPC": {
        "section_code_match": 0.40,
        "concept_match": 0.10,
        "trigger_match": 0.00,
        "repository_validation": 0.05,
        "llm_boost": 0.00,
        "total": 0.55,
        "threshold_status": "BELOW_THRESHOLD"
    }
}
```

### 8.4 Confidence Penalties

Reduce confidence if:
- Section codes don't normalize (unclear format) → -0.10
- Concepts contradict statute framework → -0.15
- Repository validation fails → -0.20
- LLM expresses uncertainty → -0.05
- Multiple conflicting signals → -0.10

---

## 9. STATUTE PRIORITY RULES

When multiple statutes score high, apply priority rules in order:

### Rule 1: Explicit Section Coding
**Highest Priority**

If section code explicitly belongs to one statute, that statute wins.

```
Example: "NDPS_20" → NDPS wins over IPC
         (No ambiguity, section is statute-specific)
```

### Rule 2: Statute Hierarchy
**Special Acts > IPC/BNS**

If a Special Act is detected, it takes priority unless it's clearly a secondary role.

```
Example: Case charges NDPS_20 + IPC_120B
         → Primary: NDPS (governs primary charge)
         → Secondary: IPC (conspiracy component only)
         
Example: Case charges IPC_302 + POCSO_5
         → Primary: POCSO (governs principal charge)
         → Secondary: IPC (not applicable; POCSO is exclusive)
```

### Rule 3: Statutory Exclusivity
**Some statutes exclude IPC**

If case falls squarely under an exclusive statute, IPC cannot apply:

```
POCSO Cases:
├─ POCSO offences override IPC equivalents
├─ IPC can apply only for non-sexual, non-child elements
└─ Example: POCSO_5 + IPC_120B allowed, but NOT POCSO_5 + IPC_302

NDPS Cases:
├─ NDPS governs narcotics
├─ IPC can apply only for violence/criminal intimidation
└─ Example: NDPS_29 + IPC_506 allowed, but NOT NDPS_29 + IPC_380
```

### Rule 4: Temporal Precedence
**Time of Offence Determines Statute**

For cases spanning IPC→BNS transition:

```
Offence before BNS commencement date (1-7-2023):
├─ Primary: IPC
└─ Secondary: BNS (if state adopted early)

Offence after BNS commencement date:
├─ Primary: BNS (in applicable states)
└─ Secondary: IPC (for reference only)

Mixed Timeline (offence before, arrest after):
├─ Primary: Statute at time of offence
├─ Secondary: Current statute (for bail purposes)
└─ Flag: "TEMPORAL_CONFLICT" for manual review
```

### Rule 5: Jurisdictional Rules
**Jurisdiction Determines Applicability**

```
UAPA Cases:
├─ Only applicable in jurisdictions recognizing it
├─ Some states don't have UAPA courts
└─ Requires special jurisdiction verification

SC/ST Act Cases:
├─ Applies in all states but
├─ Requires proof of protected characteristics
└─ Cannot be primary if no SC/ST victim

Domestic Violence Act:
├─ Applies only to intimate relationships
├─ Cannot be primary for stranger violence
└─ Requires domestic context verification
```

### Rule 6: Specificity Principle
**More Specific Statute Wins**

```
Between IPC and Special Act:
├─ Special Act (more specific) wins
└─ IPC is only secondary backup

Between two Special Acts:
├─ The statute covering the principal charge wins
└─ Other statutes become secondary
```

**Priority Order (Descending)**
```
1. POCSO (if minor/sexual element)
2. Specialized Acts (NDPS, PMLA, IT Act, etc.)
3. General Statutes (IPC/BNS)
```

---

## 10. MIXED-STATUTE HANDLING

Mixed-statute cases (e.g., NDPS + IPC) require special handling to prevent errors.

### 10.1 Valid Mixed-Statute Combinations

**NDPS + IPC**
```
Valid:
├─ NDPS_20 (possession) + IPC_506 (criminal intimidation)
├─ NDPS_29 (trafficking) + IPC_120B (criminal conspiracy)
└─ NDPS_31 (financing) + IPC_409 (criminal breach of trust)

Invalid:
├─ NDPS_20 + IPC_380 (theft) — narcotics aren't "stolen"
├─ NDPS_29 + IPC_302 (murder) — different crimes entirely
└─ NDPS_9 + IPC_420 (cheating) — no nexus
```

**POCSO + IPC**
```
Valid:
├─ POCSO_4 (penetrative assault) + IPC_120B (conspiracy)
├─ POCSO_8 (abduction) + IPC_328 (causing hurt by poison)
└─ POCSO_11 (false imprisonment) + IPC_376 NOT allowed (POCSO exclusive)

Invalid:
├─ POCSO_5 (non-penetrative assault) + IPC_375 (rape) — POCSO exclusive
├─ POCSO_3 (sexual harassment) + IPC_294 (indecent behaviour) — separate frameworks
└─ Any POCSO charge + IPC sexual assault — POCSO supersedes
```

**IT Act + IPC**
```
Valid:
├─ IT_66 (hacking) + IPC_406 (criminal breach of trust)
├─ IT_67 (pornography) + IPC_507 (criminal intimidation)
└─ IT_73 (identity theft) + IPC_420 (cheating)

Invalid:
├─ IT_66 + IPC_379 (theft) — data isn't "stolen" in traditional sense
├─ IT_67 + IPC_295 (religious offense) — different frameworks
└─ IT_72 + IPC_504 (abusive words) — no nexus
```

### 10.2 Mixed-Statute Processing Rules

When mixed statutes are detected:

```
Step 1: Identify Primary Statute
├─ Apply Statute Priority Rules (Section 9)
└─ Usually the statute governing the principal charge

Step 2: Identify Secondary Statutes
├─ List all other statutes
├─ Verify they don't contradict primary
├─ Verify nexus exists (not random combination)
└─ Flag if nexus is questionable

Step 3: Mapping Policy
├─ If primary = IPC/BNS → allow_ipc_bns_mapping = TRUE
├─ If primary = Special Act → allow_ipc_bns_mapping = FALSE
├─ Secondary IPC/BNS can map to themselves
└─ Secondary Special Acts cannot map to anything

Step 4: Repository Selection
├─ Primary statute determines primary repository
├─ Secondary statutes documented in secondary_repositories field
├─ All sections cross-indexed by statute

Step 5: Bail Framework Selection
├─ If primary statute is Special Act → Use special_bail_rule
├─ If primary statute is IPC/BNS → Use standard CrPC/BNSS
├─ Document all applicable bail rules
└─ Flag conflicting bail frameworks for manual review

Step 6: Confidence Calculation
├─ Each statute gets independent confidence score
├─ Primary statute confidence must exceed threshold
├─ Secondary statute confidence should be > 0.60
├─ If secondary confidence < 0.60 → Flag for manual review
└─ Overall confidence = primary_confidence (secondary must validate)
```

### 10.3 Rejection Criteria for Mixed Statutes

Reject mixed-statute combination if:

```
1. No valid nexus between charges
   ├─ Example: NDPS_20 + SC/ST Act (no relation)
   └─ Reject unless victim is SC/ST AND drugs involved

2. Statutes are mutually exclusive
   ├─ Example: POCSO_5 (minor victim) + IPC_375 (adult rape law)
   └─ POCSO supersedes; IPC_375 cannot co-exist

3. Secondary statute confidence < 0.40
   ├─ Too uncertain to include
   └─ Reject secondary, proceed with primary only

4. Multiple primary statutes (ambiguous primary)
   ├─ Example: POCSO_5 + NDPS_20 with equal confidence
   └─ Cannot determine primary; manual review required

5. Contradictory bail frameworks
   ├─ Example: NDPS (has mandatory detention) + Juvenile Act (presumption of innocence)
   └─ Cannot apply conflicting frameworks; manual review required
```

---

## 11. REPOSITORY SELECTION

After routing, select the repository to query for sections and statute interpretation.

### 11.1 Repository Types

```python
class RepositoryType(Enum):
    IPC = "IPC"                    # Indian Penal Code (pre-2023)
    BNS = "BNS"                    # Bharatiya Nyaya Sanhita (2023+)
    CRPC = "CRPC"                  # Criminal Procedure Code
    BNSS = "BNSS"                  # Bharatiya Nyaya Sanhita Samhita
    
    # Special Acts
    NDPS = "NDPS"                  # Narcotic Drugs & Psychotropic Substances Act
    POCSO = "POCSO"                # Protection of Children from Sexual Offences
    PMLA = "PMLA"                  # Prevention of Money Laundering Act
    UAPA = "UAPA"                  # Unlawful Activities Prevention Act
    IT_ACT = "IT_ACT"              # Information Technology Act
    SC_ST_ACT = "SC_ST_ACT"        # Prevention of Atrocities Act
    ARMS_ACT = "ARMS_ACT"          # Arms Act
    DOWRY_ACT = "DOWRY_ACT"        # Dowry Prohibition Act
    DV_ACT = "DV_ACT"              # Domestic Violence Act
    JJ_ACT = "JJ_ACT"              # Juvenile Justice Act
    
    # Consolidated (for mixed cases)
    CONSOLIDATED = "CONSOLIDATED" # Multiple statutes
```

### 11.2 Repository Selection Logic

```python
def select_repository(routing_object: StatuteRoutingObject) -> str:
    """Select repository based on primary statute and context."""
    
    if routing_object.primary_statute == "IPC":
        if jurisdiction_is_modern_bns(routing_object.case_context):
            return RepositoryType.BNS.value
        else:
            return RepositoryType.IPC.value
    
    elif routing_object.primary_statute in [
        "NDPS", "POCSO", "PMLA", "UAPA", "IT_ACT",
        "SC_ST_ACT", "ARMS_ACT", "DOWRY_ACT", "DV_ACT", "JJ_ACT"
    ]:
        return routing_object.primary_statute
    
    elif len(routing_object.secondary_statutes) > 0:
        return RepositoryType.CONSOLIDATED.value
    
    else:
        raise RoutingError("Cannot determine repository")
```

### 11.3 Repository Path Structure

```
repositories/
├── ipc/
│   ├── sections.json          # IPC sections 1-511
│   ├── chapters.json          # IPC chapter metadata
│   ├── offence_types.json     # Classification
│   └── bail_rules.json        # CrPC bail provisions
│
├── bns/
│   ├── sections.json          # BNS sections
│   ├── chapters.json          # BNS chapter metadata
│   └── bail_rules.json        # BNSS bail provisions
│
├── special_acts/
│   ├── ndps/
│   │   ├── sections.json
│   │   ├── offence_classification.json
│   │   ├── bail_framework.json     # NDPS_37, bail provisions
│   │   └── triggers.json           # Keywords: narcotics, drugs, etc.
│   │
│   ├── pocso/
│   │   ├── sections.json
│   │   ├── age_based_provisions.json
│   │   ├── bail_framework.json
│   │   └── triggers.json           # Keywords: minor, child, etc.
│   │
│   ├── pmla/
│   │   ├── sections.json
│   │   ├── offence_classification.json
│   │   ├── bail_framework.json
│   │   └── triggers.json
│   │
│   ├── uapa/
│   │   ├── sections.json
│   │   ├── bail_framework.json
│   │   └── triggers.json
│   │
│   ├── it_act/
│   │   ├── sections.json
│   │   ├── offence_classification.json
│   │   └── triggers.json
│   │
│   └── [other_special_acts]/
│
└── consolidated/
    └── multi_statute_routing.json
```

### 11.4 Repository Validation

Before returning routing object, validate repository choice:

```python
def validate_repository_selection(routing_object: StatuteRoutingObject) -> bool:
    """Ensure repository matches primary statute."""
    
    repo = routing_object.repository
    primary = routing_object.primary_statute
    
    # Rule 1: Repository must exist
    if repo not in valid_repositories():
        return False
    
    # Rule 2: Repository must match primary statute
    if repo in ["NDPS", "POCSO", "PMLA", "UAPA", "IT_ACT"]:
        if primary != repo:
            return False
    
    # Rule 3: If primary is IPC, repo must be IPC or BNS
    if primary == "IPC":
        if repo not in ["IPC", "BNS"]:
            return False
    
    # Rule 4: If mixed, repo must be CONSOLIDATED
    if len(routing_object.secondary_statutes) > 0:
        # Exception: If secondary are only IPC/BNS variants
        non_ipc_bns = [s for s in routing_object.secondary_statutes 
                       if s not in ["IPC", "BNS"]]
        if non_ipc_bns:
            if repo != "CONSOLIDATED":
                return False
    
    return True
```

---

## 12. IPC↔BNS MAPPING POLICY

Mapping between IPC and BNS is allowed ONLY in specific conditions.

### 12.1 Mapping Policy Rules

```
Rule 1: Primary Statute Determines Mapping
├─ If primary_statute in ["IPC", "BNS"] → allow_ipc_bns_mapping = TRUE
└─ Else → allow_ipc_bns_mapping = FALSE

Rule 2: Special Acts Cannot Map
├─ If primary_statute in [NDPS, POCSO, PMLA, UAPA, ...] → allow_ipc_bns_mapping = FALSE
└─ This is non-negotiable

Rule 3: Mixed Cases
├─ If secondary_statutes contains IPC/BNS → They can map to each other
├─ But do NOT map secondary statutes between IPC/BNS and Special Acts
└─ Example: NDPS_20 is NOT equivalent to any IPC section (no mapping)

Rule 4: Temporal Constraint
├─ IPC → BNS mapping only if both statutes applied to offence
├─ If offence predates BNS (before 1-7-2023), BNS mapping is reference only
└─ Legal result must be determined under statute applicable at time of offence

Rule 5: Jurisdiction Constraint
├─ Only map to BNS if jurisdiction has adopted BNS
├─ Some states adopted BNS before national commencement
└─ Verify jurisdiction before mapping decision
```

### 12.2 Mapping Scope

```python
class MappingScope(Enum):
    NO_MAPPING = "NO_MAPPING"           # Special Acts
    IPC_TO_BNS = "IPC_TO_BNS"           # If case is under IPC
    BNS_TO_IPC = "BNS_TO_IPC"           # If case is under BNS (reference)
    BIDIRECTIONAL = "BIDIRECTIONAL"     # Generate both equivalents
    LIMITED = "LIMITED"                 # Map only for specific sections
```

### 12.3 Invalid Mapping Scenarios

**NEVER attempt these mappings:**

```
NDPS_20 → IPC equivalent
├─ NDPS covers narcotics possession
├─ IPC has NO narcotics-specific section
└─ Cannot map; different legal framework

POCSO_5 → IPC_375
├─ POCSO_5 is for non-penetrative assault on minors
├─ IPC_375 is for rape (adult context)
├─ Cannot map; POCSO supersedes IPC

IT_ACT_66 → IPC_379
├─ IT_ACT_66 is for hacking (unauthorized access)
├─ IPC_379 is for theft
├─ Cannot map; different mens rea

PMLA_3 → IPC equivalent
├─ PMLA covers money laundering
├─ IPC has no narcotics-specific section
└─ Cannot map
```

### 12.4 Valid Mapping Examples

**Allowed:**

```
Case 1: IPC_302 (murder)
├─ BNS_103 (murder equivalent)
├─ allow_ipc_bns_mapping = TRUE
├─ enable_bns_parallel = TRUE
└─ Generate both IPC and BNS interpretations

Case 2: BNS_105 (culpable homicide)
├─ IPC_304 (culpable homicide equivalent)
├─ allow_ipc_bns_mapping = TRUE
├─ enable_bns_parallel = TRUE
└─ Provide both for reference

Case 3: NDPS_20 (possession)
├─ IPC_120B (conspiracy) might also apply
├─ allow_ipc_bns_mapping = FALSE (for NDPS)
├─ But allow IPC_120B to stand on its own
└─ No cross-statute mapping
```

---

## 13. MANUAL REVIEW CONDITIONS

Manual review is triggered automatically when routing cannot achieve sufficient confidence or encounters contradictions.

### 13.1 Automatic Manual Review Triggers

Trigger manual review (set `manual_review_required = True`) if:

```
1. Confidence < 0.60
   ├─ Routing is too uncertain
   ├─ Requires human judgment
   └─ LLM also unable to confirm

2. Contradictory Section Codes
   ├─ Candidate sections belong to conflicting statutes
   ├─ Example: POCSO_5 + IPC_375 (contradictory)
   └─ Human must determine which is correct charge

3. Temporal Conflict
   ├─ Offence date spans IPC→BNS transition
   ├─ Unclear which statute applies
   └─ Jurisdiction-specific determination needed

4. Jurisdictional Uncertainty
   ├─ Statute may not be recognized in jurisdiction
   ├─ Example: UAPA in non-implementing state
   └─ Requires jurisdictional verification

5. Multiple Equally-Confident Statutes
   ├─ Two statutes score ≥ 0.75 equally
   ├─ Cannot determine primary
   └─ Human arbitration needed

6. Mixed Statute Validity Unclear
   ├─ Nexus between charges questionable
   ├─ Example: NDPS_20 + SC/ST Act (unclear connection)
   └─ Human must verify both charges apply

7. Special Bail Framework Ambiguity
   ├─ Multiple conflicting bail frameworks apply
   ├─ Example: Juvenile Justice Act + NDPS
   └─ Cannot determine which framework governs

8. Repository Validation Failed
   ├─ Detected sections don't exist in repository
   ├─ Data integrity issue
   └─ Requires investigation
```

### 13.2 Manual Review Priority Levels

```python
class ManualReviewPriority(Enum):
    CRITICAL = "CRITICAL"      # Must review before proceeding
    HIGH = "HIGH"               # Review before bail decision
    MEDIUM = "MEDIUM"           # Review for reference/appeal
    LOW = "LOW"                 # Review if time permits
```

Assign priority based on:

```
CRITICAL:
├─ Confidence < 0.50
├─ Contradictory statutes
├─ Bail framework conflict
└─ Jurisdictional uncertainty

HIGH:
├─ Confidence 0.50-0.65
├─ Mixed statutes with weak secondary confidence
└─ Temporal conflicts

MEDIUM:
├─ Confidence 0.65-0.75
├─ Ambiguous primary statue
└─ Special rules requiring verification

LOW:
├─ Confidence 0.75-0.85
├─ Clear primary, minor ambiguities
└─ Reference-level review
```

### 13.3 Manual Review Output

When manual review is required, provide structured context:

```python
manual_review_context = {
    "review_required": True,
    "priority": "HIGH",
    "reason": "Mixed statute with low secondary confidence",
    
    "candidate_statutes": {
        "NDPS": {"confidence": 0.88, "evidence": "Section NDPS_20 explicitly mentioned"},
        "IPC": {"confidence": 0.45, "evidence": "Conspiracy mentioned but unclear nexus"}
    },
    
    "questions_for_reviewer": [
        "Does IPC_120B conspiracy charge apply or is this NDPS-only case?",
        "Is there evidence of criminal conspiracy or just possession?"
    ],
    
    "suggested_action": "Contact prosecution to clarify charges",
    "escalation_path": "Senior legal analyst → Law team lead"
}
```

---

## 14. FAILURE HANDLING

The routing engine must handle failures gracefully without corrupting downstream logic.

### 14.1 Failure Modes

```
Failure Mode 1: No Statute Detected
├─ Symptom: All confidence scores < 0.50
├─ Cause: Section codes unrecognized, no trigger matches
├─ Recovery: Set manual_review_required = TRUE, return partial result
└─ Downstream: Cannot proceed; return error to user

Failure Mode 2: Contradictory Evidence
├─ Symptom: Section codes from conflicting statutes
├─ Cause: Data quality issue or genuine conflicting charges
├─ Recovery: Flag all candidates, let LLM arbitrate, manual review if LLM uncertain
└─ Downstream: May proceed if LLM confident, else error

Failure Mode 3: Repository Not Found
├─ Symptom: Selected repository doesn't exist in system
├─ Cause: Configuration error or missing statute definition
├─ Recovery: Log error, select fallback repository (IPC), manual review required
└─ Downstream: Cached result with degraded confidence

Failure Mode 4: Invalid Statute Configuration
├─ Symptom: Statute triggers/rules malformed
├─ Cause: Configuration file corruption
├─ Recovery: Skip that statute, continue with others
└─ Downstream: Reduced coverage for that statute

Failure Mode 5: LLM Service Unavailable
├─ Symptom: LLM call fails when needed for tie-breaking
├─ Cause: Service outage or rate limiting
├─ Recovery: Use last-known-good confidence, flag uncertainty
└─ Downstream: May proceed with reduced confidence, manual review recommended

Failure Mode 6: Circular Routing Dependency
├─ Symptom: Routing decision depends on its own output
├─ Cause: Misconfigured routing rules
├─ Recovery: Break cycle by returning first-detected statute
└─ Downstream: Flag as anomaly for investigation
```

### 14.2 Error Handling Strategy

```python
class RoutingError(Exception):
    """Base exception for routing errors."""
    pass

class NoStatuteDetectedError(RoutingError):
    """Raised when no statute can be detected."""
    pass

class ConflictingStatuteError(RoutingError):
    """Raised when statute assignment is contradictory."""
    pass

class RepositoryNotFoundError(RoutingError):
    """Raised when selected repository doesn't exist."""
    pass

class InvalidConfigurationError(RoutingError):
    """Raised when statute configuration is invalid."""
    pass

class LLMServiceError(RoutingError):
    """Raised when LLM service is unavailable."""
    pass
```

### 14.3 Graceful Degradation

If routing encounters errors:

```
Step 1: Attempt Primary Routing
├─ If success → Return result
└─ If failure → Continue

Step 2: Attempt Fallback Routing
├─ Use only section code matching (no LLM)
├─ Use cached statute knowledge
├─ Reduce confidence appropriately
└─ If success → Return degraded result with warning

Step 3: Attempt Minimal Routing
├─ Select IPC as default statute
├─ Mark all confidence as "degraded"
├─ Set manual_review_required = TRUE
└─ Return with comprehensive error documentation

Step 4: Return Error
├─ If all attempts fail
├─ Log full error context
└─ Return exception to caller (not to downstream stages)
```

### 14.4 Error Recovery Examples

**Example 1: Unrecognized Section Code**

```
Input: Candidate sections = ["UNKNOWN_ACT_99"]

Error Handling:
├─ Attempt to normalize: No mapping found
├─ Attempt fallback: Query cached statute list → Not found
├─ Attempt minimal: Assign IPC, confidence = 0.20
└─ Return: StatuteRoutingObject with:
    {
        primary_statute: "IPC",
        confidence: 0.20,
        manual_review_required: True,
        manual_review_reason: "Unrecognized section code UNKNOWN_ACT_99",
        routing_valid: False,
        validation_errors: ["Section UNKNOWN_ACT_99 not found in any repository"]
    }
```

**Example 2: Repository Configuration Error**

```
Input: Primary statute = "NDPS", repository = "NDPS"

Error Handling:
├─ Attempt to load NDPS repository → File not found
├─ Fallback: Load IPC repository (always available)
├─ Log: "NDPS repository unavailable, using IPC for fallback routing"
└─ Return: StatuteRoutingObject with:
    {
        primary_statute: "NDPS",
        repository: "IPC",  // Fallback
        confidence: 0.70,
        manual_review_required: True,
        manual_review_reason: "NDPS repository unavailable; IPC used for fallback",
        routing_valid: True,  // Still valid, just degraded
        validation_warnings: ["Repository fallback used"]
    }
```

**Example 3: LLM Service Timeout**

```
Input: Ambiguous case, confidence = 0.65, needs LLM tie-breaking

Error Handling:
├─ Attempt LLM call → Timeout after 5 seconds
├─ Fallback: Use current confidence (0.65)
├─ Log: "LLM service unavailable; using current confidence"
└─ Return: StatuteRoutingObject with:
    {
        primary_statute: [highest confidence statute],
        confidence: 0.65,
        manual_review_required: True,
        manual_review_reason: "LLM service unavailable; recommendation uncertain",
        routing_valid: True,
        validation_warnings: ["LLM tie-breaking not performed"]
    }
```

---

## 15. DOWNSTREAM STAGE INTERACTIONS

The Statute Routing Engine interfaces with multiple downstream stages. Each interaction has specific contracts and constraints.

### 15.1 Stage 3: Section Identification

**Input from SRE:**
```
StatuteRoutingObject with:
- primary_statute: "NDPS"
- repository: "SPECIAL_ACTS"
```

**Stage 3 Responsibilities:**
```
├─ Use primary_statute to select section definition repository
├─ Retrieve section definitions ONLY from designated repository
├─ Do NOT attempt to find IPC equivalents if allow_ipc_bns_mapping=FALSE
├─ Map candidate sections to full section texts
└─ Output: EnrichedSectionObject with section metadata
```

**Contract:**
```
- Stage 3 SHALL NOT re-route or challenge SRE decision
- Stage 3 SHALL NOT override primary_statute
- Stage 3 SHALL honor allow_ipc_bns_mapping flag
- Stage 3 SHALL document repository used
- Stage 3 SHALL raise exception if repository unavailable
```

**Example Flow:**

```
SRE Output:
{
    primary_statute: "NDPS",
    repository: "SPECIAL_ACTS",
    allow_ipc_bns_mapping: FALSE
}

Stage 3 Actions:
├─ Load SPECIAL_ACTS/NDPS repository
├─ For each candidate section:
│  ├─ Retrieve full section text from NDPS
│  ├─ Extract elements required for NDPS offence
│  └─ Do NOT search IPC for equivalent
├─ Output EnrichedSectionObject
└─ Send to Stage 4
```

### 15.2 Stage 4: Statutory Verification

**Input from SRE:**
```
StatuteRoutingObject with:
- primary_statute: "POCSO"
- special_bail_rule: "POCSO_BAIL_PROVISIONS"
```

**Stage 4 Responsibilities:**
```
├─ Verify offence elements against selected statute framework
├─ Use POCSO-specific verification logic
├─ Do NOT apply IPC verification if POCSO is primary
├─ Identify age-based provisions (POCSO-specific)
├─ Verify victim is minor (POCSO requirement)
└─ Output: VerificationResult with statute-specific findings
```

**Contract:**
```
- Stage 4 SHALL NOT override statute assignment
- Stage 4 SHALL use special_bail_rule if provided
- Stage 4 SHALL apply statute-specific verification logic
- Stage 4 SHALL document verification framework used
- Stage 4 SHALL not fall back to IPC verification unless explicitly allowed
```

**Example Flow:**

```
SRE Output:
{
    primary_statute: "POCSO",
    special_bail_rule: "POCSO_BAIL_PROVISIONS",
    secondary_statutes: ["IPC"]
}

Stage 4 Actions:
├─ For primary charge (POCSO):
│  ├─ Apply POCSO-specific element verification
│  ├─ Check: Victim age < 18 (mandatory)
│  ├─ Check: Sexual assault elements (POCSO-defined)
│  └─ Use POCSO bail framework
├─ For secondary charge (IPC):
│  ├─ Apply standard IPC verification only if nexus to primary
│  ├─ Example: IPC_120B conspiracy with POCSO charge
│  └─ Do NOT apply IPC verification to POCSO charge itself
├─ Output VerificationResult
└─ Send to Stage 5
```

### 15.3 Stage 5: Bail Reasoning

**Input from SRE:**
```
StatuteRoutingObject with:
- primary_statute: "NDPS"
- special_bail_rule: "NDPS_SECTION_37"
- allow_ipc_bns_mapping: FALSE
```

**Stage 5 Responsibilities:**
```
├─ Apply bail framework specified by SRE
├─ If special_bail_rule provided: Use statute-specific framework
├─ If no special_bail_rule: Use standard CrPC/BNSS framework
├─ Do NOT apply IPC/BNS bail rules to Special Acts
├─ Do NOT cross-statute bail reasoning
└─ Output: BailReasoningResult with statute-specific recommendations
```

**Contract:**
```
- Stage 5 SHALL follow special_bail_rule if provided
- Stage 5 SHALL NOT override statute assignment
- Stage 5 SHALL apply correct bail framework
- Stage 5 SHALL document framework used in reasoning
- Stage 5 SHALL not hallucinate bail provisions
```

**Example Flow:**

```
SRE Output:
{
    primary_statute: "NDPS",
    special_bail_rule: "NDPS_SECTION_37",
    special_framework: "NDPS_BAIL_FRAMEWORK"
}

Stage 5 Actions:
├─ Load NDPS bail framework from statute config
├─ Apply NDPS-specific considerations:
│  ├─ Commercial quantity determination
│  ├─ Habitual offender status
│  ├─ International trafficking indicators
│  └─ NDPS Section 37 provisions (special bail conditions)
├─ Generate bail recommendation based on NDPS framework
├─ Do NOT use standard CrPC bail reasoning
└─ Output BailReasoningResult
```

### 15.4 Stage 6: Precedent Retrieval

**Input from SRE:**
```
StatuteRoutingObject with:
- primary_statute: "POCSO"
- repository: "SPECIAL_ACTS"
```

**Stage 6 Responsibilities:**
```
├─ Query precedent repository based on primary_statute
├─ Retrieve cases decided under POCSO, not IPC
├─ Do NOT retrieve IPC precedents for POCSO charges
├─ Apply statute-specific precedent weights
└─ Output: PrecedentSet with relevant cases
```

**Contract:**
```
- Stage 6 SHALL query correct statute repository
- Stage 6 SHALL NOT mix precedents from different statutes
- Stage 6 SHALL document statute for each precedent
- Stage 6 SHALL not hallucinate precedents
- Stage 6 SHALL apply statute-specific weights
```

**Example Flow:**

```
SRE Output:
{
    primary_statute: "IT_ACT",
    repository: "SPECIAL_ACTS"
}

Stage 6 Actions:
├─ Query precedent repository for IT_ACT cases
├─ Filter: Cases with IT_ACT_66 (hacking)
├─ Exclude: Cases decided under IPC_379 (theft)
├─ Sort by:
│  ├─ Recency (recent precedents preferred)
│  ├─ Authority level (SC > HC > District)
│  └─ Fact similarity
├─ Return: PrecedentSet with IT_ACT cases only
└─ Document: "All precedents from IT_ACT repository"
```

### 15.5 Cross-Stage Dependencies

SRE output flows downstream immutably:

```
SRE Output

  ↓ (immutable contract)

Stage 3: Section Identification
  ├─ Uses: primary_statute, repository
  └─ Outputs: EnrichedSectionObject

  ↓

Stage 4: Statutory Verification
  ├─ Uses: primary_statute, special_bail_rule, repository
  └─ Outputs: VerificationResult

  ↓

Stage 5: Bail Reasoning
  ├─ Uses: primary_statute, special_framework, allow_ipc_bns_mapping
  └─ Outputs: BailReasoningResult

  ↓

Stage 6: Precedent Retrieval
  ├─ Uses: primary_statute, repository
  └─ Outputs: PrecedentSet
```

**Key Invariant:**
```
No downstream stage may:
├─ Override primary_statute
├─ Re-route to different statute
├─ Ignore allow_ipc_bns_mapping
├─ Query wrong repository
├─ Apply wrong bail framework
└─ Without raising exception (breaking the pipeline)
```

---

## 16. COMPLETE PYDANTIC SCHEMA

The Statute Routing Engine uses Pydantic for type safety and validation.

```python
# statute_routing.py

from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, validator

# ============================================================================
# ENUMS
# ============================================================================

class StatuteType(str, Enum):
    """Supported statute types."""
    IPC = "IPC"
    BNS = "BNS"
    CRPC = "CRPC"
    BNSS = "BNSS"
    NDPS = "NDPS"
    POCSO = "POCSO"
    PMLA = "PMLA"
    UAPA = "UAPA"
    IT_ACT = "IT_ACT"
    SC_ST_ACT = "SC_ST_ACT"
    ARMS_ACT = "ARMS_ACT"
    DOWRY_ACT = "DOWRY_ACT"
    DV_ACT = "DV_ACT"
    JJ_ACT = "JJ_ACT"

class RepositoryType(str, Enum):
    """Repository types for statute sections."""
    IPC = "IPC"
    BNS = "BNS"
    NDPS = "NDPS"
    POCSO = "POCSO"
    PMLA = "PMLA"
    UAPA = "UAPA"
    IT_ACT = "IT_ACT"
    SC_ST_ACT = "SC_ST_ACT"
    ARMS_ACT = "ARMS_ACT"
    DOWRY_ACT = "DOWRY_ACT"
    DV_ACT = "DV_ACT"
    JJ_ACT = "JJ_ACT"
    CONSOLIDATED = "CONSOLIDATED"

class ManualReviewPriority(str, Enum):
    """Priority levels for manual review."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class ConfidenceThreshold(str, Enum):
    """Confidence threshold categories."""
    VERY_HIGH = "VERY_HIGH"      # >= 0.90
    HIGH = "HIGH"                 # 0.75-0.89
    MEDIUM = "MEDIUM"             # 0.60-0.74
    LOW = "LOW"                   # < 0.60

# ============================================================================
# INPUT MODELS
# ============================================================================

class CaseContextObject(BaseModel):
    """Metadata about the case."""
    case_id: str
    jurisdiction: str
    date_of_offence: datetime
    date_of_arrest: Optional[datetime] = None
    nature_of_accusation: str
    accused_details: Optional[Dict[str, Any]] = None
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

class LegalQueryObject(BaseModel):
    """Original legal query from case intake."""
    original_query_text: str
    cleaned_query: str
    extracted_concepts: List[str] = Field(default_factory=list)
    extracted_keywords: List[str] = Field(default_factory=list)
    extracted_entities: Optional[Dict[str, Any]] = None

class SectionCandidate(BaseModel):
    """Candidate section from Stage 2."""
    section_code: str  # e.g., "IPC_302", "NDPS_29"
    section_text: str
    detected_statute: Optional[str] = None
    confidence_from_stage2: float = Field(ge=0.0, le=1.0)
    legal_concepts_detected: List[str] = Field(default_factory=list)
    source: str = "Stage2"

class LegalConcept(BaseModel):
    """Detected legal concept."""
    concept_name: str
    concept_type: str  # "element", "procedure", "bail_framework"
    source_statute: Optional[str] = None
    extracted_from: str
    confidence: float = Field(ge=0.0, le=1.0)

class StatuteRoutingInput(BaseModel):
    """Complete input to Statute Routing Engine."""
    case_context: CaseContextObject
    legal_query: LegalQueryObject
    candidate_sections: List[SectionCandidate]
    detected_concepts: List[LegalConcept] = Field(default_factory=list)
    override_primary_statute: Optional[str] = None
    
    class Config:
        validate_assignment = True

# ============================================================================
# OUTPUT MODELS
# ============================================================================

class ConfidenceBreakdown(BaseModel):
    """Detailed confidence breakdown per statute."""
    statute: str
    section_code_match: float = Field(ge=0.0, le=1.0)
    concept_match: float = Field(ge=0.0, le=1.0)
    trigger_match: float = Field(ge=0.0, le=1.0)
    repository_validation: float = Field(ge=0.0, le=1.0)
    llm_boost: float = Field(ge=0.0, le=1.0)
    total: float = Field(ge=0.0, le=1.0)
    threshold_status: str
    reasoning: str = ""

class DetectionEvidence(BaseModel):
    """Evidence supporting statute detection."""
    statute: str
    matched_sections: List[str] = Field(default_factory=list)
    matched_concepts: List[str] = Field(default_factory=list)
    matched_triggers: List[str] = Field(default_factory=list)
    repository_validation_passed: bool
    llm_confirmation: Optional[bool] = None
    reasoning: str = ""

class RoutingValidationError(BaseModel):
    """Validation error in routing."""
    error_code: str
    error_message: str
    affected_statute: Optional[str] = None
    severity: str = "ERROR"

class ManualReviewContext(BaseModel):
    """Context for manual review."""
    review_required: bool
    priority: ManualReviewPriority
    reason: str
    candidate_statutes: Dict[str, Dict[str, Any]]
    questions_for_reviewer: List[str] = Field(default_factory=list)
    suggested_action: str = ""
    escalation_path: str = ""
    estimated_review_time: int = 0  # minutes

class StatuteRoutingObject(BaseModel):
    """Complete output from Statute Routing Engine."""
    
    # Primary routing decisions
    primary_statute: str = Field(..., description="Primary governing statute")
    secondary_statutes: List[str] = Field(default_factory=list)
    all_detected_statutes: List[str] = Field(default_factory=list)
    
    # Confidence metrics
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_breakdown: Dict[str, ConfidenceBreakdown]
    confidence_threshold: ConfidenceThreshold
    
    # Reasoning
    routing_reason: str
    detection_evidence: Dict[str, DetectionEvidence]
    
    # Mapping policy
    allow_ipc_bns_mapping: bool
    enable_bns_parallel: bool = False
    
    # Special provisions
    special_bail_rule: Optional[str] = None
    special_framework: Optional[str] = None
    special_framework_description: Optional[str] = None
    
    # Repository selection
    repository: str
    repository_path: Optional[str] = None
    
    # Manual review
    manual_review_required: bool
    manual_review_priority: Optional[ManualReviewPriority] = None
    manual_review_context: Optional[ManualReviewContext] = None
    
    # Validation
    routing_valid: bool
    validation_errors: List[RoutingValidationError] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)
    
    # Metadata
    timestamp: datetime = Field(default_factory=datetime.now)
    routing_version: str = "1.0.0"
    
    @validator('confidence')
    def validate_confidence(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v
    
    @validator('primary_statute')
    def validate_primary_statute(cls, v):
        valid_statutes = [st.value for st in StatuteType]
        if v not in valid_statutes:
            raise ValueError(f"Invalid statute: {v}")
        return v
    
    @validator('repository')
    def validate_repository(cls, v):
        valid_repos = [rt.value for rt in RepositoryType]
        if v not in valid_repos:
            raise ValueError(f"Invalid repository: {v}")
        return v
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
        validate_assignment = True
```

---

## 17. PUBLIC API

The Statute Routing Engine exposes a minimal, focused public API.

```python
# statute_router_api.py

from typing import Optional
from statute_routing import (
    StatuteRoutingInput,
    StatuteRoutingObject,
    RoutingError,
    NoStatuteDetectedError,
)

class StatuteRoutingEngine:
    """
    Public API for the Statute Routing Engine.
    
    This is the single entry point for all routing operations.
    """
    
    def __init__(self, config_path: str = "config/statute_config.json"):
        """
        Initialize the routing engine.
        
        Args:
            config_path: Path to statute configuration file
            
        Raises:
            InvalidConfigurationError: If config cannot be loaded
        """
        self.config_path = config_path
        self._load_configuration()
        self._initialize_repositories()
        self._initialize_trigger_dictionary()
    
    def route(self, routing_input: StatuteRoutingInput) -> StatuteRoutingObject:
        """
        Route a case to the appropriate statute(s).
        
        This is the primary entry point. It orchestrates all routing phases.
        
        Args:
            routing_input: Complete input data for routing
            
        Returns:
            StatuteRoutingObject with routing decision
            
        Raises:
            RoutingError: If routing fails and cannot recover
            NoStatuteDetectedError: If no statute can be detected
            
        Examples:
            >>> from statute_routing import StatuteRoutingInput, CaseContextObject
            >>> 
            >>> case_context = CaseContextObject(
            ...     case_id="CASE_001",
            ...     jurisdiction="Delhi",
            ...     date_of_offence=datetime.now(),
            ...     nature_of_accusation="Drug possession"
            ... )
            >>> 
            >>> routing_input = StatuteRoutingInput(
            ...     case_context=case_context,
            ...     legal_query=...,
            ...     candidate_sections=[...]
            ... )
            >>> 
            >>> engine = StatuteRoutingEngine()
            >>> routing_object = engine.route(routing_input)
            >>> 
            >>> print(f"Primary statute: {routing_object.primary_statute}")
            >>> print(f"Confidence: {routing_object.confidence}")
        """
        pass
    
    def route_with_override(
        self,
        routing_input: StatuteRoutingInput,
        override_primary_statute: str
    ) -> StatuteRoutingObject:
        """
        Route with forced override of primary statute.
        
        Use only when you know the correct statute and want to skip
        automated detection. For debugging/testing only.
        
        Args:
            routing_input: Complete input data for routing
            override_primary_statute: Force this as primary statute
            
        Returns:
            StatuteRoutingObject with override applied
            
        Raises:
            ValueError: If override statute is invalid
        """
        pass
    
    def validate_routing_output(
        self,
        routing_object: StatuteRoutingObject
    ) -> bool:
        """
        Validate a routing output for consistency.
        
        Args:
            routing_object: Routing object to validate
            
        Returns:
            True if valid, False otherwise
            
        Raises:
            RoutingError: If validation encounters errors
        """
        pass
    
    def get_statute_info(self, statute: str) -> Dict[str, Any]:
        """
        Retrieve configuration info for a statute.
        
        Args:
            statute: Statute code (e.g., "NDPS")
            
        Returns:
            Dictionary with statute metadata
            
        Raises:
            ValueError: If statute not supported
        """
        pass
    
    def add_statute(
        self,
        statute_code: str,
        statute_config: Dict[str, Any]
    ) -> None:
        """
        Add support for a new statute (extension mechanism).
        
        Args:
            statute_code: Unique code for statute
            statute_config: Configuration dict with:
                - triggers: List of keywords
                - sections: List of valid sections
                - bail_framework: Bail rules
                - exclusive: Whether statute excludes IPC/BNS
                
        Raises:
            ValueError: If statute_code already exists
            InvalidConfigurationError: If config is invalid
        """
        pass
    
    def get_audit_trail(
        self,
        routing_object: StatuteRoutingObject
    ) -> Dict[str, Any]:
        """
        Generate audit trail for routing decision.
        
        Useful for explaining why a certain routing was chosen.
        
        Args:
            routing_object: Routing result to audit
            
        Returns:
            Dictionary with detailed audit trail
        """
        pass

# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def route_case(
    case_context: CaseContextObject,
    legal_query: LegalQueryObject,
    candidate_sections: List[SectionCandidate]
) -> StatuteRoutingObject:
    """
    Convenience function: Route a case with minimal setup.
    
    Args:
        case_context: Case metadata
        legal_query: Extracted query
        candidate_sections: Section candidates from Stage 2
        
    Returns:
        Routing decision
    """
    engine = StatuteRoutingEngine()
    routing_input = StatuteRoutingInput(
        case_context=case_context,
        legal_query=legal_query,
        candidate_sections=candidate_sections
    )
    return engine.route(routing_input)

def get_statute_routing_info(statute: str) -> Dict[str, Any]:
    """Convenience function: Get statute info."""
    engine = StatuteRoutingEngine()
    return engine.get_statute_info(statute)

def validate_routing_decision(routing_object: StatuteRoutingObject) -> bool:
    """Convenience function: Validate routing."""
    engine = StatuteRoutingEngine()
    return engine.validate_routing_output(routing_object)
```

---

## 18. SEQUENCE DIAGRAM

```
Participant: Case Intake
Participant: Stage 2 (Section Candidates)
Participant: Statute Routing Engine (SRE)
Participant: Detection Phase
Participant: LLM (conditional)
Participant: Output Validation
Participant: Stage 3 (Section Identification)

Case Intake ->> Stage 2: Pass case context
Stage 2 ->> Stage 2: Generate candidates
Stage 2 ->> SRE: Pass routing input

SRE ->> Detection Phase: Extract indicators
Detection Phase ->> Detection Phase: Priority 1: Section codes
Detection Phase ->> Detection Phase: Priority 2: Legal concepts
Detection Phase ->> Detection Phase: Priority 3: Triggers
Detection Phase ->> Detection Phase: Priority 4: Repository validation

alt Confidence >= 0.75
    Detection Phase ->> Output Validation: Return initial routing
else Confidence < 0.75
    Detection Phase ->> LLM: Request tie-breaking
    LLM ->> LLM: Analyze ambiguous case
    LLM ->> Detection Phase: Return confidence
    Detection Phase ->> Output Validation: Include LLM result
end

Output Validation ->> Output Validation: Validate routing object
Output Validation ->> Output Validation: Check contradictions
Output Validation ->> Output Validation: Verify repository selection

alt Validation passes
    Output Validation ->> SRE: Mark routing_valid=True
else Validation fails
    Output Validation ->> SRE: Add errors, mark routing_valid=False
end

alt Confidence >= 0.75 AND routing_valid=True
    SRE ->> Stage 3: Return routing (final)
else Confidence < 0.75 OR routing_valid=False
    SRE ->> SRE: Set manual_review_required=True
    SRE ->> Stage 3: Return routing (with manual review flag)
end

Stage 3 ->> Stage 3: Honor SRE decision
```

---

## 19. CLASS DIAGRAM

```
┌─────────────────────────────────────┐
│   StatuteRoutingEngine (main API)   │
├─────────────────────────────────────┤
│ - config: RoutingConfig             │
│ - repositories: RepositoryManager   │
│ - triggers: TriggerDictionary       │
│ - llm: LLMClient (optional)         │
├─────────────────────────────────────┤
│ + route(input) → RoutingObject      │
│ + validate_output(routing) → bool   │
│ + add_statute(code, config) → void  │
│ + get_statute_info(code) → dict     │
└─────────────────────────────────────┘
            △
            │ uses
            │
    ┌───────┴────────┐
    │                │
    ▼                ▼
┌──────────────┐  ┌──────────────────────┐
│ Detection    │  │ Validation           │
│ Engine       │  │ Engine               │
├──────────────┤  ├──────────────────────┤
│ - priorities │  │ - rules              │
│ - scores     │  │ - checks             │
├──────────────┤  ├──────────────────────┤
│ + detect()   │  │ + validate()         │
│ + score()    │  │ + check_contradictions│
│ + resolve()  │  └──────────────────────┘
└──────────────┘
    △
    │ uses
    │
    ▼
┌──────────────────────────────┐
│ Repository Manager           │
├──────────────────────────────┤
│ - repos: Dict[str, Repo]     │
│ - cache: RepoCache           │
├──────────────────────────────┤
│ + load_repo(statute) → Repo  │
│ + validate_section() → bool  │
│ + get_sections() → list      │
└──────────────────────────────┘
    △
    │
    ├───────────────────────────┬──────────────┬─────────────┐
    │                           │              │             │
    ▼                           ▼              ▼             ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ IPC Repo     │  │ NDPS Repo    │  │ POCSO Repo   │  │ PMLA Repo    │
├──────────────┤  ├──────────────┤  ├──────────────┤  ├──────────────┤
│ sections     │  │ sections     │  │ sections     │  │ sections     │
│ bail_rules   │  │ triggers     │  │ age_rules    │  │ bail_rules   │
│ offences     │  │ bail_rules   │  │ bail_rules   │  │ triggers     │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘

┌──────────────────────────────┐
│ Trigger Dictionary           │
├──────────────────────────────┤
│ - statute_triggers: dict     │
│ - priority_weights: dict     │
├──────────────────────────────┤
│ + get_triggers(statute)      │
│ + match_keywords() → list    │
│ + update_triggers() → void   │
└──────────────────────────────┘

┌──────────────────────────────┐
│ Input Models (Pydantic)      │
├──────────────────────────────┤
│ - CaseContextObject          │
│ - LegalQueryObject           │
│ - SectionCandidate           │
│ - StatuteRoutingInput        │
└──────────────────────────────┘

┌──────────────────────────────┐
│ Output Models (Pydantic)     │
├──────────────────────────────┤
│ - ConfidenceBreakdown        │
│ - DetectionEvidence          │
│ - ManualReviewContext        │
│ - StatuteRoutingObject       │
└──────────────────────────────┘
```

---

## 20. EXTENSION MECHANISM FOR NEW STATUTES

The Statute Routing Engine is designed to support new statutes with minimal code changes.

### 20.1 Adding a New Statute

To add support for a new statute (e.g., "Environment Protection Act"):

**Step 1: Create Statute Configuration File**

```yaml
# config/statutes/environment_act.yaml

statute_code: "ENV_ACT"
statute_name: "Environment Protection Act"
statute_type: "SPECIAL_ACT"

# Is this statute exclusive (overrides IPC)?
exclusive: true

# Valid section ranges
section_ranges:
  - start: 1
    end: 100
    type: "primary_offences"

# Triggers (keywords that indicate this statute)
triggers:
  - environmental damage
  - pollution
  - hazardous waste
  - air quality
  - water contamination
  - emission standards
  - noise pollution
  - protected area
  - wildlife destruction
  - ecological impact

# Bail framework
bail_framework:
  framework_name: "Environment Act Bail Rules"
  default_bail_consideration: "environmental_impact"
  special_provisions:
    - name: "Environmental Officer Custody"
      applicable_conditions: "ecological threat"
    - name: "Mandatory Environmental Assessment"
      applicable_conditions: "always"

# Valid element types (for verification)
element_types:
  - causation_of_harm
  - environmental_impact
  - intentionality
  - negligence

# IPC compatibility
can_apply_with_ipc:
  - reason: "Conspiracy to cause environmental damage"
    ipc_sections: ["IPC_120B"]
  - reason: "Criminal intimidation for environmental whistleblowing"
    ipc_sections: ["IPC_506"]

# Precedent configuration
precedent_config:
  repository: "SPECIAL_ACTS"
  weight: 1.0
  recency_factor: 0.8
```

**Step 2: Register Statute in System**

```python
# In your initialization code

from statute_router import StatuteRoutingEngine

engine = StatuteRoutingEngine()

# Load and register new statute
env_config = load_yaml("config/statutes/environment_act.yaml")
engine.add_statute("ENV_ACT", env_config)
```

**Step 3: Update Trigger Dictionary**

```python
# This happens automatically when you call add_statute()
# But you can also manually update:

engine.trigger_dictionary.update(
    statute="ENV_ACT",
    new_triggers=[
        "environmental damage",
        "pollution",
        # ... more triggers
    ]
)
```

**Step 4: Load Repository Data**

```python
# Create repository file: repositories/special_acts/environment_act/sections.json

{
  "statute": "ENV_ACT",
  "sections": [
    {
      "section_number": 1,
      "section_text": "Short title and commencement",
      "type": "administrative"
    },
    {
      "section_number": 15,
      "section_text": "Prohibition of emission...",
      "type": "primary_offence",
      "bail_eligible": true,
      "elements": ["causation_of_harm", "intentionality"]
    },
    ...
  ]
}
```

**Step 5: Test the New Statute**

```python
# Test routing with environment case
test_input = StatuteRoutingInput(
    case_context=...,
    legal_query=...,
    candidate_sections=[
        SectionCandidate(
            section_code="ENV_ACT_15",
            section_text="...",
            detected_statute="ENV_ACT"
        )
    ]
)

result = engine.route(test_input)
assert result.primary_statute == "ENV_ACT"
assert result.confidence >= 0.85
```

### 20.2 Extension Checklist

When adding a new statute:

```
□ Create statute configuration file (YAML)
□ Register statute in StatuteRoutingEngine
□ Define trigger keywords
□ Define bail framework rules
□ Create repository files (sections.json)
□ Add test cases
□ Document excluded IPC sections (if applicable)
□ Document applicable secondary statutes
□ Verify precedent repository is populated
□ Update documentation
□ Mark routing version increment
```

### 20.3 Backward Compatibility

New statutes are added without breaking existing functionality:

```python
# Old code continues to work
result = engine.route(input_without_new_statute)
# → Still works, new statute just ignored

# New code uses new statute
result = engine.route(input_with_new_statute)
# → Routes correctly to new statute

# Version checking
assert result.routing_version == "1.0.0"  # or higher
```

---

## 21. UNIT-TEST STRATEGY

Comprehensive testing ensures routing engine reliability.

### 21.1 Test Categories

**Category 1: Single Statute Routing**

```python
# test_single_statute_routing.py

def test_ipc_only_routing():
    """Test: Pure IPC case (no Special Acts)."""
    # Setup: IPC_302 (murder)
    # Expected: primary_statute="IPC", allow_ipc_bns_mapping=True
    pass

def test_bns_only_routing():
    """Test: Pure BNS case."""
    # Setup: BNS_103 (murder equivalent)
    # Expected: primary_statute="BNS", allow_ipc_bns_mapping=True
    pass

def test_ndps_single_routing():
    """Test: Pure NDPS case."""
    # Setup: NDPS_20 (possession)
    # Expected: primary_statute="NDPS", allow_ipc_bns_mapping=False
    pass

def test_pocso_single_routing():
    """Test: Pure POCSO case."""
    # Setup: POCSO_5 (assault on minor)
    # Expected: primary_statute="POCSO", allow_ipc_bns_mapping=False
    pass

# ... similar tests for each statute type
```

**Category 2: Mixed Statute Routing**

```python
# test_mixed_statute_routing.py

def test_ndps_plus_ipc_routing():
    """Test: NDPS with conspiracy charge."""
    # Setup: NDPS_29 + IPC_120B
    # Expected: primary="NDPS", secondary=["IPC"], valid combination
    pass

def test_pocso_exclusive_routing():
    """Test: POCSO with attempted IPC mapping."""
    # Setup: POCSO_5 + IPC_375 (rape)
    # Expected: POCSO only, IPC_375 rejected (POCSO exclusive)
    pass

def test_invalid_mixed_routing():
    """Test: Invalid statute combination."""
    # Setup: NDPS_20 + SC/ST Act (no nexus)
    # Expected: Confidence < 0.60, manual_review_required=True
    pass
```

**Category 3: Confidence Scoring**

```python
# test_confidence_scoring.py

def test_high_confidence_section_match():
    """Test: Section code explicit match → high confidence."""
    # Setup: Section code matches exactly
    # Expected: confidence >= 0.85
    pass

def test_medium_confidence_concept_match():
    """Test: Concepts match but no explicit section."""
    # Expected: confidence 0.65-0.75
    pass

def test_low_confidence_trigger_only():
    """Test: Only keywords match."""
    # Expected: confidence < 0.65, LLM consultation triggered
    pass
```

**Category 4: Decision Tree**

```python
# test_decision_tree.py

def test_decision_tree_path_special_act():
    """Test: Decision tree correctly routes to Special Act."""
    pass

def test_decision_tree_path_ipc_bns():
    """Test: Decision tree correctly routes to IPC/BNS."""
    pass

def test_decision_tree_path_mixed():
    """Test: Decision tree correctly handles mixed case."""
    pass
```

**Category 5: Manual Review Triggering**

```python
# test_manual_review.py

def test_manual_review_low_confidence():
    """Test: confidence < 0.60 triggers manual review."""
    pass

def test_manual_review_contradictions():
    """Test: Conflicting charges trigger manual review."""
    pass

def test_manual_review_priority_critical():
    """Test: Critical cases properly prioritized."""
    pass
```

**Category 6: Repository Validation**

```python
# test_repository_validation.py

def test_repository_selection_special_act():
    """Test: NDPS case selects SPECIAL_ACTS repo."""
    pass

def test_repository_fallback():
    """Test: Graceful fallback if repo unavailable."""
    pass

def test_repository_consistency():
    """Test: All sections exist in selected repo."""
    pass
```

**Category 7: Failure Handling**

```python
# test_failure_handling.py

def test_unrecognized_section_code():
    """Test: Unknown section gracefully handled."""
    pass

def test_llm_service_unavailable():
    """Test: Continue without LLM if unavailable."""
    pass

def test_config_file_missing():
    """Test: Graceful degradation with missing config."""
    pass
```

### 21.2 Test Fixtures

```python
# conftest.py (pytest configuration)

import pytest
from datetime import datetime
from statute_routing import (
    StatuteRoutingInput,
    CaseContextObject,
    LegalQueryObject,
    SectionCandidate,
    StatuteRoutingEngine
)

@pytest.fixture
def routing_engine():
    """Provide initialized routing engine."""
    return StatuteRoutingEngine(config_path="config/test_config.json")

@pytest.fixture
def sample_ndps_case():
    """Provide sample NDPS case input."""
    case_context = CaseContextObject(
        case_id="TEST_NDPS_001",
        jurisdiction="Delhi",
        date_of_offence=datetime(2024, 1, 15),
        nature_of_accusation="Possession of narcotics"
    )
    
    legal_query = LegalQueryObject(
        original_query_text="Defendant found with 50g heroin",
        cleaned_query="possession heroin 50g",
        extracted_keywords=["heroin", "possession"],
        extracted_concepts=["controlled_substance"]
    )
    
    candidate_sections = [
        SectionCandidate(
            section_code="NDPS_20",
            section_text="...",
            detected_statute="NDPS",
            confidence_from_stage2=0.92
        )
    ]
    
    return StatuteRoutingInput(
        case_context=case_context,
        legal_query=legal_query,
        candidate_sections=candidate_sections
    )

@pytest.fixture
def sample_pocso_case():
    """Provide sample POCSO case input."""
    # Similar structure for POCSO
    pass
```

### 21.3 Coverage Goals

```
Target Coverage: 95%+

Untestable areas (excluded):
- External LLM responses (mocked)
- File system operations (mocked)
- Network requests (mocked)

Testable areas (required):
- All routing logic paths
- All decision tree branches
- All confidence calculations
- All validation rules
- All error conditions
- All statute combinations
```

---

## 22. PERFORMANCE CONSIDERATIONS

The routing engine must perform at scale without degrading system throughput.

### 22.1 Performance Requirements

```
Requirement 1: Response Time
├─ Average case routing: < 100ms
├─ Complex cases (mixed statute): < 200ms
├─ 95th percentile: < 500ms
└─ Maximum allowed: 1 second

Requirement 2: Throughput
├─ Single-threaded: 100+ cases/sec
├─ No blocking on LLM calls
├─ Graceful degradation on LLM unavailable

Requirement 3: Memory
├─ Engine initialization: < 50MB
├─ Per-case processing: < 1MB
├─ Repository cache: < 500MB (configurable)

Requirement 4: Scalability
├─ No performance degradation with new statutes
├─ Repositories loadable on-demand
├─ Cache invalidation strategy: TTL-based
```

### 22.2 Optimization Strategies

**Strategy 1: Section Code Matching (Priority 1)**

```python
# Use exact string matching, not regex
# → O(1) lookup in hash table

section_index = {
    "IPC_302": {"statute": "IPC", "type": "murder"},
    "NDPS_20": {"statute": "NDPS", "type": "possession"},
    # ... precompiled at startup
}

def match_section_code(code: str) -> Optional[Dict]:
    return section_index.get(code)  # O(1)
```

**Strategy 2: Trigger Matching (Priority 3)**

```python
# Use compiled regex for keyword matching
# → Fast substring search

import re

trigger_patterns = {
    "NDPS": re.compile(r"\b(heroin|ganja|charas|opium)\b", re.IGNORECASE),
    "POCSO": re.compile(r"\b(minor|child|under 18)\b", re.IGNORECASE),
}

def match_triggers(text: str, statute: str) -> bool:
    pattern = trigger_patterns.get(statute)
    return pattern.search(text) is not None if pattern else False
```

**Strategy 3: Concept Matching (Priority 2)**

```python
# Use semantic hash instead of NLP for speed
# → O(1) lookup

concept_statute_map = {
    "controlled_substance": ["NDPS"],
    "sexual_assault_minor": ["POCSO"],
    "criminal_conspiracy": ["IPC", "BNS", "NDPS"],  # Multi-statute
}

def match_concepts(concepts: List[str]) -> Dict[str, List[str]]:
    """
    Fast concept matching: O(n) where n = num concepts
    """
    statute_scores = {}
    for concept in concepts:
        for statute in concept_statute_map.get(concept, []):
            statute_scores[statute] = statute_scores.get(statute, 0) + 1
    return statute_scores
```

**Strategy 4: Repository Caching**

```python
# Cache frequently-accessed repositories in memory
# → Reduce file I/O

from functools import lru_cache

@lru_cache(maxsize=14)  # One per statute
def get_repository(statute: str) -> Repository:
    """Load and cache repository."""
    # Load from disk only if not cached
    return load_repository_from_disk(statute)

# Clear cache periodically (e.g., hourly)
def invalidate_cache_if_needed():
    if cache_age > TTL:
        get_repository.cache_clear()
```

**Strategy 5: LLM Call Minimization**

```python
# Only call LLM if absolutely necessary
# → Avoid 500-2000ms network delay

def needs_llm_consultation(confidence: float) -> bool:
    """Skip LLM if confidence already high."""
    return confidence < 0.75  # Only call if uncertain

# If LLM calls needed, batch them
def route_batch(cases: List[StatuteRoutingInput]) -> List[StatuteRoutingObject]:
    """
    Route multiple cases in one batch.
    Combine ambiguous cases for single LLM call.
    """
    pass
```

### 22.3 Benchmarking

```python
# benchmark_routing.py

import time
from statute_router import StatuteRoutingEngine

def benchmark_single_routing():
    """Measure time for single case routing."""
    engine = StatuteRoutingEngine()
    test_cases = [
        # Sample test cases
    ]
    
    times = []
    for case in test_cases:
        start = time.perf_counter()
        result = engine.route(case)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    print(f"Mean: {statistics.mean(times)*1000:.2f}ms")
    print(f"P95: {sorted(times)[int(len(times)*0.95)]*1000:.2f}ms")
    print(f"Max: {max(times)*1000:.2f}ms")

def benchmark_batch_routing():
    """Measure throughput for batch routing."""
    # Similar benchmarking for batch operations
    pass
```

---

## 23. SECURITY CONSIDERATIONS

The routing engine handles sensitive legal data and must implement appropriate security controls.

### 23.1 Input Validation

```python
# Validate all inputs to prevent injection attacks

class InputValidator:
    """Validate and sanitize routing engine inputs."""
    
    @staticmethod
    def validate_section_code(code: str) -> str:
        """
        Validate section code format.
        
        Valid formats:
        - IPC_302
        - NDPS_29
        - POCSO_5
        - BNS_103
        """
        # Whitelist pattern: STATUTE_NUMBER
        pattern = r"^[A-Z_]+_\d+$"
        if not re.match(pattern, code):
            raise ValueError(f"Invalid section code format: {code}")
        
        # Limit length
        if len(code) > 50:
            raise ValueError(f"Section code too long: {code}")
        
        return code.upper()
    
    @staticmethod
    def validate_statute_code(code: str) -> str:
        """Validate statute code against whitelist."""
        valid_statutes = [st.value for st in StatuteType]
        if code not in valid_statutes:
            raise ValueError(f"Invalid statute: {code}")
        return code
    
    @staticmethod
    def validate_case_id(case_id: str) -> str:
        """Validate case ID format."""
        # Prevent SQL injection, path traversal, etc.
        pattern = r"^[A-Za-z0-9_\-]{1,255}$"
        if not re.match(pattern, case_id):
            raise ValueError(f"Invalid case ID format: {case_id}")
        return case_id
```

### 23.2 Configuration Security

```python
# config/statute_config.json is sensitive and should be:
# - Read from secure location
# - Restricted file permissions (0600)
# - Not committed to version control
# - Encrypted in transit/rest if needed

class ConfigurationLoader:
    """Securely load configuration."""
    
    @staticmethod
    def load_config(path: str) -> Dict:
        """Load configuration with security checks."""
        # Verify file exists
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config not found: {path}")
        
        # Verify file permissions (reject if world-readable)
        stat_info = os.stat(path)
        if stat_info.st_mode & 0o077:  # Check if readable by others
            raise PermissionError(f"Config file has insecure permissions: {path}")
        
        # Load and validate
        with open(path, 'r') as f:
            config = json.load(f)
        
        # Validate schema
        validate_config_schema(config)
        
        return config
```

### 23.3 LLM Integration Security

```python
# When calling LLM for routing, be careful not to leak sensitive data

class LLMClient:
    """Secure LLM client for routing decisions."""
    
    @staticmethod
    def query_llm_for_routing(query: str) -> str:
        """
        Query LLM for tie-breaking.
        
        Security considerations:
        - Do NOT send full case details to LLM
        - Send only: statute indicators, section codes, keywords
        - Redact: names, case IDs, sensitive identifiers
        - Use HTTPS for all LLM calls
        - Implement rate limiting to prevent abuse
        """
        
        # Redact sensitive information
        redacted_query = redact_pii(query)
        
        # Call LLM
        response = make_llm_call(redacted_query, timeout=5)
        
        # Validate response
        if not is_valid_routing_response(response):
            raise ValueError("Invalid LLM response")
        
        return response
```

### 23.4 Audit Logging

```python
# Log all routing decisions for audit trail

class RoutingAuditLog:
    """Audit logging for routing decisions."""
    
    @staticmethod
    def log_routing_decision(
        case_id: str,
        routing_object: StatuteRoutingObject,
        user_id: Optional[str] = None
    ) -> None:
        """
        Log routing decision for audit trail.
        
        Logged fields:
        - case_id
        - timestamp
        - user_id (if applicable)
        - primary_statute
        - confidence
        - manual_review_required
        - routing_reason
        
        NOT logged:
        - Case details (names, addresses, etc.)
        - Defendant identifiers
        """
        
        audit_entry = {
            "case_id": case_id,
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "primary_statute": routing_object.primary_statute,
            "confidence": routing_object.confidence,
            "manual_review": routing_object.manual_review_required,
            "routing_reason": routing_object.routing_reason,
        }
        
        # Write to secure audit log
        write_audit_log(audit_entry)
```

---

## 24. LOGGING STRATEGY

Comprehensive logging enables monitoring and debugging.

### 24.1 Logging Levels

```python
# Use standard Python logging levels

import logging

logger = logging.getLogger("StatuteRoutingEngine")

# DEBUG: Detailed information for diagnosing problems
logger.debug(f"Section code matched: {section_code} → {statute}")

# INFO: General informational messages
logger.info(f"Routing case {case_id} to {primary_statute}")

# WARNING: Something unexpected but recoverable
logger.warning(f"Low confidence for {case_id}: {confidence}")

# ERROR: Serious problem but doesn't stop execution
logger.error(f"Repository load failed for {statute}: {error}")

# CRITICAL: System cannot continue
logger.critical(f"Configuration invalid, cannot proceed: {error}")
```

### 24.2 Structured Logging

```python
# Use structured logging for machine parsing

import structlog

logger = structlog.get_logger()

# Structured log entry
logger.info(
    "routing_decision",
    case_id=case_id,
    primary_statute=primary_statute,
    secondary_statutes=secondary_statutes,
    confidence=confidence,
    manual_review=manual_review_required,
    duration_ms=elapsed_time * 1000,
)
```

### 24.3 Log Output Examples

```
[2024-01-15T10:30:45.123Z] INFO: routing_decision
  case_id="CASE_2024_001"
  primary_statute="NDPS"
  confidence=0.92
  duration_ms=87

[2024-01-15T10:30:46.456Z] WARNING: low_confidence
  case_id="CASE_2024_002"
  primary_statute="POCSO"
  confidence=0.58
  reason="Ambiguous_age_documentation"
  manual_review_required=true

[2024-01-15T10:30:47.789Z] ERROR: repository_error
  statute="NDPS"
  error="Repository_file_not_found"
  fallback_used="IPC"
```

---

## 25. FUTURE SCALABILITY

The routing engine is designed to support evolution and scaling.

### 25.1 Planned Enhancements

**Phase 2: Multi-Jurisdiction Support**
```
Current:
├─ Single jurisdiction (India-centric)
└─ IPC/BNS routing

Future:
├─ Support for other jurisdictions
├─ Statute version management (IPC 1860 vs amendments)
├─ Jurisdiction-specific bail frameworks
└─ Multi-country legal frameworks
```

**Phase 3: ML-Based Confidence Scoring**
```
Current:
├─ Rule-based confidence calculation
└─ LLM tie-breaking

Future:
├─ Train ML model on case routing history
├─ Learn statute patterns from precedent data
├─ Improve confidence prediction
└─ Anomaly detection for unusual cases
```

**Phase 4: Real-Time Statute Updates**
```
Current:
├─ Static configuration files
└─ Manual updates

Future:
├─ Subscribe to statute amendments
├─ Automatic configuration updates
├─ Version management for routing decisions
└─ Backward-compatible routing with law changes
```

**Phase 5: Advanced Mixed-Statute Handling**
```
Current:
├─ Basic mixed-statute detection
└─ Limited nexus validation

Future:
├─ Graph-based statute relationships
├─ Automatic nexus scoring
├─ Complex multi-statute orchestration
└─ Statute interaction matrices
```

**Phase 6: Explainable AI Integration**
```
Current:
├─ Basic routing reason text
└─ Confidence breakdown

Future:
├─ Detailed decision explanations
├─ Counterfactual reasoning
├─ What-if analysis
└─ Interactive routing exploration
```

### 25.2 Architectural Extensibility

The engine supports evolution through:

```
1. Plugin Architecture
   ├─ Custom detection engines
   ├─ Custom validation rules
   ├─ Custom confidence algorithms
   └─ Loaded dynamically at runtime

2. Event-Driven Architecture
   ├─ Emit routing events
   ├─ Allow subscribers to extend behavior
   ├─ Non-blocking processing
   └─ Enable real-time updates

3. Microservice Deployment
   ├─ Separate routing engine from other stages
   ├─ Independent scaling
   ├─ API-first design (already implemented)
   └─ Containerized deployment

4. Caching and CDN
   ├─ Cache frequently-routed statutes
   ├─ Distribute routing decisions
   ├─ Edge computing support
   └─ Reduced latency
```

### 25.3 Data Collection for ML Training

```
Future ML models will need training data:

├─ Routing Decision History
│  ├─ case_id
│  ├─ input_features
│  ├─ routing_decision
│  ├─ confidence
│  ├─ manual_review_flag
│  └─ actual_outcome (from court)
│
├─ Feedback Loop
│  ├─ Collect manual review outcomes
│  ├─ Collect appeals/reversals
│  ├─ Identify misrouted cases
│  └─ Train model on mistakes
│
└─ Validation Data
   ├─ Reserve 20% of cases for validation
   ├─ Measure model accuracy
   ├─ Compare ML vs rule-based routing
   └─ Monitor model drift over time
```

### 25.4 Statute Knowledge Graph

Future version may use knowledge graph:

```
Statutes as Nodes
├─ IPC (node)
├─ BNS (node)
├─ NDPS (node)
└─ POCSO (node)

Relationships as Edges
├─ IPC → BNS (equivalent_section)
├─ NDPS → IPC (can_combine_with)
├─ POCSO → IPC (excludes)
└─ SC/ST_ACT → IPC (enhances)

Benefits:
├─ Automatic nexus scoring
├─ Relationship-based routing
├─ Conflict detection
└─ Statute reasoning
```

---

## SUMMARY: ARCHITECTURE DESIGN COMPLETE

This comprehensive design document specifies the Statute Routing Engine as a research-grade system that:

### What It Does
- **Determines the governing statute(s)** for criminal cases before downstream processing
- **Prevents invalid cross-statute mappings** (e.g., NDPS to IPC)
- **Applies statute-specific reasoning** (bail frameworks, elements, precedents)
- **Becomes the single source of truth** for all downstream stages

### How It Works
1. **Phase 1: Extraction** → Gather indicators from input
2. **Phase 2: Initial Scoring** → Score each statute against priorities
3. **Phase 3: Conflict Resolution** → Handle multiple candidates
4. **Phase 4: Repository Validation** → Verify against statute definitions
5. **Phase 5: LLM Validation** → Tie-breaking if needed
6. **Phase 6: Policy Application** → Apply routing rules
7. **Phase 7: Output Validation** → Final consistency checks

### Key Properties
✓ **Deterministic** — Same input always produces same output
✓ **Transparent** — Detailed confidence breakdown and reasoning
✓ **Extensible** — Easy to add new statutes
✓ **Fault-Tolerant** — Graceful degradation on errors
✓ **Auditable** — Complete decision trail for review
✓ **Scalable** — Designed for high throughput
✓ **Secure** — Validates inputs, logs decisions
✓ **Testable** — 95%+ test coverage target

### Deliverables Ready for Implementation
1. ✓ Complete Pydantic schema (Section 16)
2. ✓ Public API specification (Section 17)
3. ✓ Unit test strategy (Section 21)
4. ✓ Performance requirements (Section 22)
5. ✓ Security controls (Section 23)
6. ✓ Logging framework (Section 24)
7. ✓ Extension mechanism (Section 20)

---

# NEXT STEPS: IMPLEMENTATION PLANNING

After this architecture is approved, the next phase will be:

1. **Gap Analysis** → Compare design against existing LexiGraph code
2. **Implementation Plan** → Specify:
   - New files to create
   - Existing files to modify
   - Code to delete
   - Migration strategy
   - Backward compatibility approach
   - Integration points with Stage 2, 3, 4, 5, 6

3. **Implementation** → Build the engine following this design

This architecture document is complete and ready for review.

