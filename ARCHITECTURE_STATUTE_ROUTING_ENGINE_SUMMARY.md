# STATUTE ROUTING ENGINE — ARCHITECTURE SUMMARY

## Quick Reference

### Core Concept
A deterministic routing engine that assigns criminal cases to their governing statute(s) before any section identification, mapping, or bail reasoning occurs. It is the **single source of truth** for all downstream stages.

### Problem It Solves
```
❌ Current:  NDPS_20 → IPC mapping → Wrong framework → Wrong bail decision
✓ Future:   NDPS_20 → NDPS routing → NDPS framework → Correct bail decision
```

### Architecture Location in Pipeline
```
Stage 0: Case Intake
    ↓
Stage 1: Legal Query Understanding
    ↓
Stage 2: Section Candidate Generation
    ↓
→ NEW: Stage 2.5 — STATUTE ROUTING ENGINE ← YOU ARE HERE
    ↓
Stage 3: Section Identification
    ↓
Stage 4: Statutory Verification
    ↓
Stage 5: Bail Reasoning
    ↓
Stage 6: Precedents
```

---

## Design Artifacts (Available in Full Document)

### 1. Input & Output Schemas (Complete Pydantic Models)
**Input:** `StatuteRoutingInput`
- Case context (metadata)
- Legal query (extracted terms)
- Candidate sections (from Stage 2)
- Detected concepts

**Output:** `StatuteRoutingObject`
- Primary statute
- Secondary statutes
- Confidence score
- Routing reason
- Mapping policy flags
- Repository selection
- Special bail rules
- Manual review flags
- Validation results

### 2. Routing Algorithm (7-Phase Process)
1. **Extraction** → Gather all indicators
2. **Initial Scoring** → Score each statute
3. **Conflict Resolution** → Handle multiples
4. **Repository Validation** → Verify legitimacy
5. **LLM Validation** → Tie-breaking (if needed)
6. **Policy Application** → Apply routing rules
7. **Output Validation** → Final checks

### 3. Decision Tree (Flowchart)
Explicit logic for:
- Special Act detection
- Mixed-statute cases
- IPC/BNS selection
- Ambiguous cases
- Manual review triggering

### 4. Hybrid Detection Strategy (Priority-Based)
```
Priority 1 (0.40 weight): Section Code Matching (explicit)
Priority 2 (0.30 weight): Legal Concepts (semantic)
Priority 3 (0.20 weight): Trigger Keywords (indexed)
Priority 4 (0.05 weight): Repository Validation (verification)
Priority 5 (0.05 weight): LLM Reasoning (tie-breaking only)
```

### 5. Confidence Scoring System
```
Confidence ≥ 0.90   → Proceed immediately (high confidence)
Confidence 0.75-0.89 → Acceptable, validate carefully
Confidence 0.60-0.74 → Trigger LLM validation
Confidence < 0.60   → Automatic manual review
```

### 6. Statute Priority Rules
1. Explicit section coding → Highest priority
2. Statute hierarchy → Special Acts > IPC/BNS
3. Statutory exclusivity → Some statutes exclude IPC
4. Temporal precedence → Time of offence determines statute
5. Jurisdictional rules → Jurisdiction determines applicability
6. Specificity principle → More specific statute wins

### 7. Mixed-Statute Handling
```
Valid Combinations:
✓ NDPS_20 + IPC_506 (narcotics + intimidation)
✓ POCSO_4 + IPC_120B (assault + conspiracy)
✓ IT_66 + IPC_406 (hacking + breach of trust)

Invalid Combinations:
✗ POCSO_5 + IPC_375 (POCSO exclusive, IPC cannot co-exist)
✗ NDPS_20 + IPC_380 (no nexus, different crimes)
✗ NDPS_29 + IPC_302 (no nexus, different frameworks)
```

### 8. Repository Selection Logic
```
Primary Statute → Repository
├─ IPC → IPC repository
├─ BNS → BNS repository
├─ NDPS → SPECIAL_ACTS/NDPS
├─ POCSO → SPECIAL_ACTS/POCSO
├─ PMLA → SPECIAL_ACTS/PMLA
└─ Mixed → CONSOLIDATED repository
```

### 9. IPC↔BNS Mapping Policy
```
Rule 1: Primary statute determines mapping
  If primary ∈ [IPC, BNS] → allow_ipc_bns_mapping = TRUE
  Else (Special Act) → allow_ipc_bns_mapping = FALSE

Rule 2: Special Acts cannot map
  NDPS ≠ IPC (no equivalent sections exist)
  POCSO ≠ IPC (POCSO supersedes IPC)
  IT Act ≠ IPC (different legal framework)

Rule 3: Temporal constraint
  IPC → BNS mapping only if both applied to offence
  Offence before BNS commencement (1-7-2023) → Use IPC
```

### 10. Downstream Stage Contracts
```
Stage 3 (Section Identification):
├─ Uses: primary_statute, repository
├─ Must honor: allow_ipc_bns_mapping
└─ Cannot: Re-route or override

Stage 4 (Statutory Verification):
├─ Uses: primary_statute, special_bail_rule
├─ Must: Apply statute-specific verification
└─ Cannot: Override statute assignment

Stage 5 (Bail Reasoning):
├─ Uses: special_framework, allow_ipc_bns_mapping
├─ Must: Apply correct bail framework
└─ Cannot: Re-determine statute

Stage 6 (Precedents):
├─ Uses: primary_statute, repository
├─ Must: Query correct statute repository
└─ Cannot: Mix precedents from different statutes
```

### 11. Failure Modes & Recovery
```
Failure Mode 1: No Statute Detected
  → Set manual_review_required = TRUE
  
Failure Mode 2: Contradictory Evidence
  → Flag for LLM arbitration, else manual review
  
Failure Mode 3: Repository Not Found
  → Fallback to IPC, mark degraded confidence
  
Failure Mode 4: LLM Service Down
  → Use current confidence, flag uncertainty
```

### 12. Extension Mechanism
Adding new statute (e.g., Environment Protection Act):
```
Step 1: Create statute config (YAML)
Step 2: Register in StatuteRoutingEngine.add_statute()
Step 3: Define trigger keywords
Step 4: Define bail framework
Step 5: Load repository (sections.json)
Step 6: Test with sample cases
Step 7: Update documentation
```

### 13. Testing Strategy
```
Category 1: Single Statute Routing (IPC, BNS, NDPS, POCSO, etc.)
Category 2: Mixed Statute Routing (valid & invalid combinations)
Category 3: Confidence Scoring (high, medium, low)
Category 4: Decision Tree (all branches)
Category 5: Manual Review (triggering conditions)
Category 6: Repository Validation (fallback & degradation)
Category 7: Failure Handling (graceful recovery)

Coverage Target: 95%+
```

### 14. Performance Requirements
```
Response Time:
├─ Average: < 100ms per case
├─ Complex (mixed): < 200ms
├─ 95th percentile: < 500ms
└─ Maximum: 1 second

Throughput:
├─ Single-threaded: 100+ cases/sec
└─ Graceful degradation on LLM unavailable

Memory:
├─ Engine initialization: < 50MB
├─ Per-case processing: < 1MB
└─ Repository cache: < 500MB
```

### 15. Security & Audit
```
Input Validation:
├─ Whitelist section codes
├─ Sanitize statute names
├─ Validate case IDs

Configuration Security:
├─ Secure file permissions (0600)
├─ Not in version control
├─ Encrypted in transit

Audit Logging:
├─ Log all routing decisions
├─ Track manual reviews
├─ NO sensitive case details in logs
```

---

## Public API (Main Entry Point)

```python
from statute_router import StatuteRoutingEngine

# Initialize engine
engine = StatuteRoutingEngine(config_path="config/statute_config.json")

# Route a case
routing_object = engine.route(routing_input)

# Access results
primary = routing_object.primary_statute        # "NDPS"
confidence = routing_object.confidence          # 0.92
mapping_allowed = routing_object.allow_ipc_bns_mapping  # False
needs_manual_review = routing_object.manual_review_required  # False
```

---

## Supported Statutes

```
Core Statutes:
├─ IPC (Indian Penal Code, pre-2023)
├─ BNS (Bharatiya Nyaya Sanhita, 2023+)
├─ CrPC (Criminal Procedure Code)
└─ BNSS (Bharatiya Nyaya Sanhita Samhita)

Special Acts:
├─ NDPS (Narcotic Drugs & Psychotropic Substances)
├─ POCSO (Protection of Children from Sexual Offences)
├─ PMLA (Prevention of Money Laundering)
├─ UAPA (Unlawful Activities Prevention)
├─ IT Act (Information Technology Act)
├─ SC/ST Act (Prevention of Atrocities)
├─ Arms Act
├─ Dowry Prohibition Act
├─ Domestic Violence Act
└─ Juvenile Justice Act

Extensible:
└─ Easy to add new statutes (24 implemented, unlimited potential)
```

---

## Key Design Principles

### 1. Single Source of Truth
- Routing decision is made **once**, immutably
- Downstream stages consume, never override
- Prevents contradictory decisions

### 2. Deterministic Routing
- Same input → Same output (always)
- No randomness or nondeterminism
- Reproducible for audits

### 3. Hybrid Detection (Not LLM-First)
- Rules-based for 95% of cases
- LLM only for tie-breaking
- Fast, reliable, explainable

### 4. Fail-Safe Defaults
- Cannot proceed without valid routing
- Manual review for uncertain cases
- Never hallucinate statute assignment

### 5. Statute-Specific Processing
- Each statute has own verification logic
- Each statute has own bail framework
- Each statute has own repository
- No cross-statute contamination

### 6. Extensible Architecture
- New statutes added without code changes
- Plugin-based statute extensions
- Configuration-driven behavior

---

## Deliverables Generated

This architecture includes:

✓ **Purpose & Responsibilities** (Sections 1-2)
✓ **Input/Output Specification** (Sections 3-4)
✓ **Routing Algorithm** (Sections 5-7)
✓ **Confidence Scoring** (Section 8)
✓ **Statute Priority Rules** (Section 9)
✓ **Mixed-Statute Handling** (Section 10)
✓ **Repository Selection** (Section 11)
✓ **IPC↔BNS Mapping Policy** (Section 12)
✓ **Manual Review Conditions** (Section 13)
✓ **Failure Handling** (Section 14)
✓ **Downstream Stage Contracts** (Section 15)
✓ **Complete Pydantic Schema** (Section 16)
✓ **Public API Specification** (Section 17)
✓ **Sequence Diagram** (Section 18)
✓ **Class Diagram** (Section 19)
✓ **Extension Mechanism** (Section 20)
✓ **Unit Test Strategy** (Section 21)
✓ **Performance Requirements** (Section 22)
✓ **Security Considerations** (Section 23)
✓ **Logging Strategy** (Section 24)
✓ **Future Scalability** (Section 25)

---

## Next Steps (Implementation Phase)

After architecture approval:

### Phase A: Gap Analysis
- [ ] Compare design vs. existing LexiGraph code
- [ ] Identify integration points
- [ ] Determine migration strategy

### Phase B: Implementation Plan
- [ ] Specify new files to create
- [ ] Specify existing files to modify
- [ ] Specify code to delete
- [ ] Map dependencies
- [ ] Establish backward compatibility

### Phase C: Implementation
- [ ] Build Statute Routing Engine
- [ ] Integrate with Stage 2 → Stage 3
- [ ] Implement all detection phases
- [ ] Implement LLM tie-breaking
- [ ] Add test suite
- [ ] Performance optimization

### Phase D: Validation
- [ ] Unit tests (95%+ coverage)
- [ ] Integration tests
- [ ] Performance benchmarking
- [ ] Security review
- [ ] Manual testing with real cases

---

## Success Criteria

The Statute Routing Engine is successful when:

1. ✓ **Eliminates cross-statute mapping errors** (NDPS ≠ IPC)
2. ✓ **Routes all cases to correct statute** (95%+ accuracy)
3. ✓ **Confident routing for 85%+ of cases** (confidence ≥ 0.75)
4. ✓ **Completes routing in < 100ms** (average)
5. ✓ **Scales to 100+ cases/sec** (throughput)
6. ✓ **Zero incorrect IPC↔BNS mappings** (integrity)
7. ✓ **Supports new statutes via config** (extensibility)
8. ✓ **Provides audit trail for all decisions** (auditability)
9. ✓ **Handles failures gracefully** (robustness)
10. ✓ **95%+ test coverage** (reliability)

---

## Document Location

Full architecture:
```
c:\proj\MootCourt\ARCHITECTURE_STATUTE_ROUTING_ENGINE.md (Complete, 25 sections)
c:\proj\MootCourt\ARCHITECTURE_STATUTE_ROUTING_ENGINE_SUMMARY.md (This file)
```

