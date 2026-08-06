# LEGAL REGIME ROUTER: RESEARCH-GRADE ARCHITECTURE

## Paradigm Shift: From Statute Classification to Legal Regime Reasoning

### What Changed

**Before (Statute-Centric)**
```
Case → Route to NDPS → Apply NDPS reasoning
```

**After (Legal-Regime-Centric)**
```
Case → Build Applicable Legal Graph → Execute by Legal Layer
```

The difference is that statutes are **classified**; legal regimes are **structured graphs**.

---

## 1. CORE CONCEPT: APPLICABLE LEGAL GRAPH

Instead of outputting a statute, output a **legal graph**.

### Example: NDPS Possession Case

```
Applicable Legal Graph
│
├─ Substantive Law Layer
│  └─ NDPS Act, Section 20
│     ├─ Elements: Possession, Knowledge, Quantity
│     ├─ Offence Type: Possession of Controlled Substance
│     └─ Severity: Scheduled substance dependent
│
├─ Procedural Law Layer
│  ├─ BNSS (Bharat
ia Nyaya Sanhita Samhita) Sections 176-182
│  ├─ Investigation Authority: Drug Enforcement Agency
│  ├─ Cognizable: Yes
│  ├─ Bailable: Conditional (NDPS Section 37)
│  └─ Special Procedures: Commercial Quantity Rules
│
├─ Evidence Law Layer
│  ├─ Bharatiya Sakshya Act (BSA) Articles 1-164
│  ├─ Key Evidence Types: Seizing Report, Chain of Custody
│  ├─ Admissibility Rules: BSA Sections 25, 26 (confessions)
│  └─ Burden of Proof: Beyond Reasonable Doubt
│
├─ Constitutional Layer
│  ├─ Article 21 (Right to Life)
│  ├─ Article 20 (Protection Against Retrospective Laws)
│  ├─ Article 14 (Equality)
│  └─ Article 19 (Freedom of Movement)
│
├─ Special Restrictions Layer
│  ├─ NDPS Section 37 (Bail Restrictions)
│  ├─ Presumption Against Bail (unless innocent)
│  └─ Commercial Quantity Determination
│
└─ Judicial Guidelines Layer
   ├─ Supreme Court Judgment: Sharad Birdhichand Sarda v. State (bail principles)
   ├─ Supreme Court: R Rajagopal v. State (NDPS prosecution)
   └─ High Court Precedents: Drug trafficking guidelines
```

This graph is **not a classification**; it's a **complete legal framework**.

---

## 2. LEGAL DOMAINS TAXONOMY

Instead of hardcoding statutes, define **legal domains**.

```
Legal Domain Hierarchy
│
├─ Criminal Law
│  ├─ General Criminal
│  │  ├─ IPC (Sections 1-511)
│  │  └─ BNS (Sections 1-226, 2023+)
│  │
│  ├─ Special Criminal
│  │  ├─ NDPS (Narcotic Drugs)
│  │  ├─ POCSO (Child Sexual Abuse)
│  │  ├─ PMLA (Money Laundering)
│  │  ├─ UAPA (Terrorism)
│  │  ├─ IT Act (Cyber Crime)
│  │  ├─ SC/ST Act (Atrocities)
│  │  ├─ Arms Act (Weapons)
│  │  ├─ Dowry Act (Dowry Crimes)
│  │  ├─ DV Act (Domestic Violence)
│  │  └─ JJ Act (Juvenile)
│  │
│  └─ Economic Criminal
│     ├─ Securities Laws
│     ├─ Tax Laws
│     ├─ Companies Act
│     └─ GST Laws
│
├─ Civil Law
│  ├─ Family Law
│  ├─ Property Law
│  ├─ Contract Law
│  └─ Tort Law
│
├─ Constitutional Law
│  ├─ Fundamental Rights
│  ├─ Directive Principles
│  └─ Powers of Courts
│
└─ Evidence & Procedure
   ├─ Criminal Procedure (BNSS)
   ├─ Civil Procedure (CPC)
   └─ Evidence (BSA)
```

Every statute/act belongs to exactly one domain. Every domain has:
- Substantive law rules
- Procedural rules
- Evidence rules
- Bail framework
- Sentencing guidelines

---

## 3. LEGAL REGIME ROUTER ARCHITECTURE

The new router is **not a classifier; it's a graph builder**.

```
Case
  │
  ├─ Extract Legal Indicators
  │  ├─ Substantive facts (who, what, when, where, why)
  │  ├─ Legal concepts (possession, assault, conspiracy)
  │  ├─ Statutory terms (section numbers, offence types)
  │  └─ Procedural context (jurisdiction, arrest date, bail hearing)
  │
  ├─ Build Applicable Legal Graph
  │  ├─ Determine Legal Domain
  │  ├─ Select Applicable Statutes
  │  ├─ Map Procedural Rules
  │  ├─ Map Evidence Rules
  │  ├─ Map Constitutional Constraints
  │  └─ Map Special Restrictions
  │
  ├─ Validate Graph Consistency
  │  ├─ No contradictory rules
  │  ├─ All dependencies satisfied
  │  ├─ All required elements present
  │  └─ All constraints honored
  │
  ├─ Execute Rule Engine
  │  ├─ Apply substantive law rules
  │  ├─ Apply procedural law rules
  │  └─ Determine applicable special provisions
  │
  └─ Output: Applicable Legal Graph
     ├─ Substantive Layer
     ├─ Procedural Layer
     ├─ Evidence Layer
     ├─ Constitutional Layer
     ├─ Special Restrictions Layer
     └─ Judicial Guidelines Layer
```

---

## 4. LEGAL REGIME OUTPUT SCHEMA

The router outputs a **legal graph**, not a statute code.

```python
class LegalLayer(BaseModel):
    """A layer of legal framework (substantive, procedural, etc.)."""
    layer_type: str  # "SUBSTANTIVE", "PROCEDURAL", "EVIDENCE", etc.
    statutes: List[ApplicableStatute]
    rules: List[LegalRule]
    constraints: List[LegalConstraint]
    precedents: List[Precedent]

class ApplicableStatute(BaseModel):
    """A statute applicable to this case."""
    statute_code: str  # "NDPS", "BNS_103", "BNSS_176", etc.
    statute_name: str
    domain: str  # "Criminal", "Evidence", "Procedure", etc.
    applicable_sections: List[str]
    reasons: List[str]  # Why this statute applies
    confidence: float
    version: str  # "2023", "2025", etc.

class LegalRule(BaseModel):
    """A rule derived from applicable statutes."""
    rule_id: str
    rule_text: str
    source_statute: str
    rule_type: str  # "Mandatory", "Discretionary", "Conditional"
    applicability_condition: Optional[str]
    consequences: List[str]

class LegalConstraint(BaseModel):
    """A constraint that limits legal interpretation."""
    constraint_id: str
    constraint_source: str  # "Constitution", "Statute", "Precedent"
    constraint_text: str
    severity: str  # "HARD", "SOFT"

class ApplicableLegalGraph(BaseModel):
    """Complete legal regime for a case."""
    case_id: str
    timestamp: datetime
    
    substantive_layer: LegalLayer
    procedural_layer: LegalLayer
    evidence_layer: LegalLayer
    constitutional_layer: LegalLayer
    special_restrictions_layer: LegalLayer
    judicial_guidelines_layer: LegalLayer
    
    # Dependencies between layers
    legal_dependencies: Graph[str, str]  # Statute → Required Statute
    
    # Overall confidence
    graph_confidence: float
    
    # Which stages can proceed
    stages_ready: Dict[str, bool]
    
    # Audit trail
    routing_decisions: List[RoutingDecision]
    manual_review_flags: List[ManualReviewFlag]

class RoutingDecision(BaseModel):
    """Why a particular statute was included."""
    statute: str
    reason: str
    evidence: List[str]
    confidence: float
    timestamp: datetime
```

---

## 5. LEGAL DEPENDENCY GRAPH

Every statute depends on other statutes. Map these dependencies.

```python
class LegalDependencyGraph:
    """Manages dependencies between applicable statutes."""
    
    dependencies = {
        # Substantive layer depends on constitutional
        "NDPS_20": {
            "requires": ["Constitution_Article_21"],
            "procedure": ["BNSS_176", "BNSS_182"],
            "evidence": ["BSA_Section_25", "BSA_Section_26"],
            "bail_rules": ["NDPS_Section_37"],
            "affected_by": ["NDPS_Amendment_2025"],
        },
        
        "POCSO_5": {
            "requires": ["Constitution_Article_15"],  # Protection of child
            "procedure": ["BNSS_184"],  # Special procedure for minors
            "evidence": ["BSA_164"],  # Medical evidence
            "bail_rules": ["POCSO_Bail_Framework"],
            "conflicts_with": ["IPC_375"],  # POCSO supersedes IPC for minors
        },
        
        "BNSS_176": {
            # Procedural statute depends on substantive
            "applies_to_all": ["All_Criminal_Statutes"],
        },
        
        "BSA_164": {
            # Evidence statute
            "required_by": ["POCSO_5", "NDPS_20"],
        }
    }
    
    def get_applicable_graph(self, primary_statute: str) -> Graph:
        """Get all statutes required by primary statute."""
        graph = Graph()
        # BFS/DFS to find all dependencies
        return graph
    
    def validate_consistency(self, graph: Graph) -> bool:
        """Ensure no contradictory rules in graph."""
        # Check for conflicts (e.g., POCSO + IPC_375)
        # Check for missing requirements
        # Check for version conflicts
        return True
```

---

## 6. LEGAL ONTOLOGY

Instead of keyword matching, use semantic legal ontology.

```python
class LegalOntology:
    """Semantic representation of legal concepts."""
    
    concepts = {
        "POSSESSION": {
            "parent": "ACTUS_REUS",
            "children": ["POSSESSION_PHYSICAL", "POSSESSION_CONSTRUCTIVE"],
            "statutes": ["IPC_378", "NDPS_20", "Arms_Act_25"],
            "elements": ["Mens_Rea", "Actus_Reus", "Knowledge"],
            "consequences": ["Punishment", "Fine", "Bail_Restrictions"],
        },
        
        "CONTROLLED_SUBSTANCE": {
            "parent": "SUBSTANCE",
            "children": ["NARCOTIC", "PSYCHOTROPIC", "SCHEDULED_CHEMICAL"],
            "statutes": ["NDPS"],
            "related_concepts": ["POSSESSION", "TRAFFICKING", "COMMERCIAL_QUANTITY"],
            "evidence_types": ["Laboratory_Report", "Chemical_Analysis"],
        },
        
        "MINOR": {
            "parent": "PERSON_CHARACTERISTIC",
            "definition": "Person under 18 years",
            "statutes": ["POCSO", "JJ_Act", "Constitution_Article_15"],
            "legal_significance": "Increases protection, changes procedure",
            "evidence": ["Birth_Certificate", "Age_Proof"],
        },
        
        "COMMERCIAL_QUANTITY": {
            "parent": "QUANTITY_CLASSIFICATION",
            "definition": "Amount indicating trafficking intent",
            "statutes": ["NDPS_Section_37"],
            "threshold": {
                "Heroin": "1 gram",
                "Ganja": "100 grams",
                "Opium": "25 grams",
            },
            "consequences": ["Mandatory_Imprisonment", "Reduced_Bail_Eligibility"],
        }
    }
    
    def get_concept_statutes(self, concept: str) -> List[str]:
        """Get all statutes related to a concept."""
        if concept in self.concepts:
            return self.concepts[concept]["statutes"]
        return []
    
    def get_concept_hierarchy(self, concept: str) -> Graph:
        """Get parent/child concept relationships."""
        # Return ontology tree for concept
        pass
```

---

## 7. RULE ENGINE (DETERMINISTIC)

Replace LLM decision-making with a **rule engine**.

```python
class LegalRuleEngine:
    """
    Deterministic rule engine for legal reasoning.
    No hallucination, no nondeterminism.
    """
    
    rules = [
        # Rule 1: If POCSO charge, exclude IPC sexual offences
        {
            "id": "POCSO_EXCLUDES_IPC_SEXUAL",
            "condition": "primary_statute == POCSO AND victim_age < 18",
            "action": "EXCLUDE(IPC_375, IPC_376, IPC_377)",
            "severity": "MANDATORY",
            "precedent": ["Budhadev Karmaskar v. State"]
        },
        
        # Rule 2: If NDPS commercial quantity, apply Section 37
        {
            "id": "NDPS_COMMERCIAL_SECTION_37",
            "condition": "statute == NDPS AND quantity >= commercial_threshold(drug)",
            "action": "APPLY(NDPS_Section_37_Bail_Restrictions)",
            "consequence": "Presumption_Against_Bail",
            "severity": "MANDATORY",
        },
        
        # Rule 3: If IPC before BNS commencement date
        {
            "id": "IPC_TEMPORAL_RULE",
            "condition": "date_of_offence < 2023_07_01",
            "action": "PRIMARY_STATUTE = IPC; SECONDARY = BNS (reference_only)",
            "severity": "MANDATORY",
        },
        
        # Rule 4: Minor + Sexual = POCSO always
        {
            "id": "MINOR_SEXUAL_POCSO",
            "condition": "victim_age < 18 AND offence_type IN [sexual_assault, penetrative, non_penetrative]",
            "action": "PRIMARY_STATUTE = POCSO; SECONDARY = IPC (only_conspiracy)",
            "severity": "MANDATORY",
        },
        
        # Rule 5: If jurisdiction is modern BNS state
        {
            "id": "MODERN_BNS_STATE",
            "condition": "jurisdiction IN [modern_bns_states] AND date_of_offence >= 2023_07_01",
            "action": "PRIMARY = BNS; SECONDARY = IPC (reference)",
            "severity": "MANDATORY",
        },
        
        # Rule 6: PMLA + underlying crime
        {
            "id": "PMLA_REQUIRES_PREDICATE_CRIME",
            "condition": "statute == PMLA",
            "action": "REQUIRE(predicate_crime_statute IN [NDPS, Cheating, Smuggling, ...])",
            "consequence": "Both_statutes_applied",
            "severity": "MANDATORY",
        },
    ]
    
    def execute_rules(self, case: Case) -> RuleExecutionResult:
        """Execute all applicable rules against case."""
        results = []
        for rule in self.rules:
            if self.evaluate_condition(rule["condition"], case):
                result = self.execute_action(rule["action"], case)
                results.append(result)
        return RuleExecutionResult(results)
    
    def evaluate_condition(self, condition: str, case: Case) -> bool:
        """Evaluate rule condition (deterministic)."""
        # Parse and evaluate condition
        pass
    
    def execute_action(self, action: str, case: Case) -> ActionResult:
        """Execute rule action (deterministic)."""
        # Parse and execute action
        pass
```

---

## 8. VERSIONED LEGAL KNOWLEDGE

Support multiple versions of statutes over time.

```python
class VersionedStatuteRepository:
    """Repository with version support."""
    
    statutes = {
        "NDPS": {
            "2020": {
                "sections": [...],
                "commercial_quantities": {...},
                "bail_rules": [...],
            },
            "2023": {
                "sections": [...],  # Added Section 27A
                "commercial_quantities": {...},
                "bail_rules": [...],  # Amended Section 37
            },
            "2025": {
                "sections": [...],  # Amendment 2025
                "commercial_quantities": {...},  # New thresholds
                "bail_rules": [...],
            }
        },
        
        "BNS": {
            "2023": {
                "sections": [...],  # Initial
            },
            "2024": {
                "sections": [...],  # Amendment
            },
            "2025": {
                "sections": [...],  # Amendment
            }
        }
    }
    
    def get_applicable_version(
        self,
        statute: str,
        date_of_offence: datetime
    ) -> str:
        """Get statute version applicable on given date."""
        # Return version in force on that date
        pass
    
    def get_statute_at_version(
        self,
        statute: str,
        version: str
    ) -> Dict:
        """Get statute definition for specific version."""
        return self.statutes[statute][version]
```

---

## 9. LEGAL REGIME ROUTER ALGORITHM

Multi-stage legal regime construction.

```
Stage 1: Extract Legal Indicators
├─ Identify substantive facts
├─ Extract legal concepts
├─ Identify statutory terms
└─ Analyze procedural context

Stage 2: Determine Primary Statute
├─ Apply domain classification rules
├─ Score candidate statutes
├─ Select primary statute
└─ Identify legal domain

Stage 3: Build Substantive Layer
├─ Load applicable statute versions
├─ Identify offence elements
├─ Identify applicable sections
└─ Confidence: High (explicit statute matches)

Stage 4: Build Procedural Layer
├─ Map procedural statute (BNSS for criminal)
├─ Identify investigation authority
├─ Identify cognizability
├─ Identify baila
bility
└─ Confidence: High (procedural rules are deterministic)

Stage 5: Build Evidence Layer
├─ Map evidence statute (BSA for criminal)
├─ Identify key evidence types
├─ Identify admissibility rules
├─ Identify burden of proof
└─ Confidence: High (evidence rules deterministic)

Stage 6: Build Constitutional Layer
├─ Identify fundamental rights constraints
├─ Identify protection of liberty rules
├─ Identify proportionality constraints
├─ Identify due process requirements
└─ Confidence: Medium (interpretation required)

Stage 7: Build Special Restrictions Layer
├─ Apply rule engine
├─ Execute all applicable rules
├─ Identify bail restrictions
├─ Identify sentencing guidelines
└─ Confidence: High (rules are deterministic)

Stage 8: Build Judicial Guidelines Layer
├─ Identify applicable precedents
├─ Identify judicial guidelines
├─ Identify court practices
└─ Confidence: Medium (precedent interpretation needed)

Stage 9: Validate Graph Consistency
├─ Check for contradictions
├─ Check for missing requirements
├─ Check for version conflicts
├─ Check for circular dependencies
└─ Confidence: High (validation is deterministic)

Stage 10: Output Applicable Legal Graph
├─ Return complete graph
├─ Include all layers
├─ Include confidence scores
├─ Include routing decisions
└─ Ready for downstream stages
```

---

## 10. DOWNSTREAM STAGE CONTRACTS

Each downstream stage now works with a **legal graph**, not a statute.

```
Stage 3: Section Identification
├─ Input: ApplicableLegalGraph
├─ Uses: substantive_layer.applicable_sections
├─ Action: Enrich with full section texts
└─ Output: EnrichedSectionGraph

Stage 4: Statutory Verification
├─ Input: EnrichedSectionGraph
├─ Uses: All layers (substantive, procedural, evidence, constitutional)
├─ Action: Verify offence elements, evidence, procedures
└─ Output: VerificationGraph

Stage 5: Bail Reasoning
├─ Input: VerificationGraph
├─ Uses: special_restrictions_layer, constitutional_layer
├─ Action: Apply bail rules, identify restrictions
└─ Output: BailReasoningResult

Stage 6: Precedent Retrieval
├─ Input: ApplicableLegalGraph
├─ Uses: All statutes, all elements
├─ Action: Query precedent database for applicable cases
└─ Output: PrecedentSet with all layers
```

Each stage knows **which legal layer** applies and **why**.

---

## 11. CONFIDENCE SCORING FOR LEGAL GRAPHS

Confidence for entire graph, not just primary statute.

```python
class GraphConfidence:
    """Confidence calculation for legal graph."""
    
    def calculate_layer_confidence(self, layer: LegalLayer) -> float:
        """Calculate confidence for one layer."""
        statute_confidences = [s.confidence for s in layer.statutes]
        rule_confirmations = len([r for r in layer.rules if r.rule_type == "MANDATORY"])
        
        # Mandatory rules always apply (confidence 1.0)
        # Discretionary rules have lower confidence
        
        avg_confidence = sum(statute_confidences) / len(statute_confidences)
        mandatory_boost = min(rule_confirmations * 0.1, 0.2)
        
        return min(avg_confidence + mandatory_boost, 1.0)
    
    def calculate_graph_confidence(self, graph: ApplicableLegalGraph) -> float:
        """Calculate confidence for entire graph."""
        layer_confidences = {
            "substantive": self.calculate_layer_confidence(graph.substantive_layer),
            "procedural": self.calculate_layer_confidence(graph.procedural_layer),
            "evidence": self.calculate_layer_confidence(graph.evidence_layer),
            "constitutional": self.calculate_layer_confidence(graph.constitutional_layer),
            "special_restrictions": self.calculate_layer_confidence(graph.special_restrictions_layer),
            "judicial_guidelines": self.calculate_layer_confidence(graph.judicial_guidelines_layer),
        }
        
        # Graph confidence = minimum layer confidence
        # (all layers must be confident)
        return min(layer_confidences.values())
```

---

## 12. EXTENSIBILITY: ADDING NEW STATUTES

Adding a statute now means defining its **legal regime**, not just hardcoding it.

```python
# config/legal_regimes/factories_act.yaml

statute_code: "FACTORIES_ACT"
statute_name: "Factories Act, 1948"
domain: "Economic Criminal"
legal_layer: "Substantive"

substantive_rules:
  - section: 112
    offence_type: "Occupational Health & Safety"
    elements: ["Violation of Rule", "Injury/Death", "Causation"]
    
procedural_rules:
  - procedure_statute: "BNSS"
    investigation_authority: "Factory Inspector"
    cognizable: false
    
evidence_rules:
  - evidence_statute: "BSA"
    key_evidence: ["Factory Records", "Safety Audit", "Medical Report"]
    
constitutional_rules:
  - right: "Article_21"
    constraint: "Right to Safe Working Conditions"
    
special_restrictions:
  - rule_id: "FACTORIES_ACT_LIMITATION"
    text: "Prosecution within 1 year of offence"
    
dependent_statutes:
  - "BNSS_176"  # Procedural
  - "BSA_1"     # Evidence
  - "Constitution_Article_21"  # Fundamental right

version_history:
  - version: "1948"
    amendments: []
  - version: "2020"
    amendments: ["Added Section 112A"]
  - version: "2025"
    amendments: ["Amended Section 89"]
```

No code changes required. Just add a YAML file and restart.

---

## 13. COMPLETE PYDANTIC SCHEMA FOR LEGAL GRAPHS

```python
# legal_regime_routing.py

from typing import Dict, List, Optional, Any, Set
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, validator
import networkx as nx

# ============================================================================
# ENUMS
# ============================================================================

class LegalLayerType(str, Enum):
    """Types of legal layers."""
    SUBSTANTIVE = "SUBSTANTIVE"
    PROCEDURAL = "PROCEDURAL"
    EVIDENCE = "EVIDENCE"
    CONSTITUTIONAL = "CONSTITUTIONAL"
    SPECIAL_RESTRICTIONS = "SPECIAL_RESTRICTIONS"
    JUDICIAL_GUIDELINES = "JUDICIAL_GUIDELINES"

class RuleType(str, Enum):
    """Types of legal rules."""
    MANDATORY = "MANDATORY"          # Must apply
    DISCRETIONARY = "DISCRETIONARY"  # May apply
    CONDITIONAL = "CONDITIONAL"      # Applies if condition met
    PROCEDURAL = "PROCEDURAL"        # Procedural requirement

class LegalDomain(str, Enum):
    """Legal domains."""
    GENERAL_CRIMINAL = "GENERAL_CRIMINAL"
    SPECIAL_CRIMINAL = "SPECIAL_CRIMINAL"
    ECONOMIC_CRIMINAL = "ECONOMIC_CRIMINAL"
    CYBER_CRIME = "CYBER_CRIME"
    FAMILY_LAW = "FAMILY_LAW"
    JUVENILE_LAW = "JUVENILE_LAW"
    CONSTITUTIONAL_LAW = "CONSTITUTIONAL_LAW"

class ConstraintSeverity(str, Enum):
    """Constraint severity."""
    HARD = "HARD"        # Cannot be overridden
    SOFT = "SOFT"        # Can be overridden with justification

# ============================================================================
# INPUT MODELS
# ============================================================================

class LegalIndicators(BaseModel):
    """Extracted legal indicators from case."""
    substantive_facts: List[str]  # Who, what, when, where, why
    legal_concepts: List[str]     # Possession, assault, conspiracy, etc.
    statutory_terms: List[str]    # Section numbers, offence types
    procedural_context: Dict[str, Any]

class LegalRegimeRoutingInput(BaseModel):
    """Input for Legal Regime Router."""
    case_id: str
    case_context: Dict[str, Any]
    legal_indicators: LegalIndicators
    candidate_statutes: List[str]  # e.g., ["NDPS", "IPC"]

# ============================================================================
# CORE MODELS
# ============================================================================

class ApplicableStatute(BaseModel):
    """A statute applicable to this case."""
    statute_code: str
    statute_name: str
    domain: LegalDomain
    applicable_sections: List[str]
    reasons_for_applicability: List[str]
    confidence: float = Field(ge=0.0, le=1.0)
    version: str
    source_evidence: List[str]  # What in the case indicates this statute

class LegalRule(BaseModel):
    """A rule derived from applicable statutes."""
    rule_id: str
    rule_text: str
    source_statute: str
    rule_type: RuleType
    applicability_condition: Optional[str] = None
    consequences: List[str]
    severity: str  # For execution priority

class LegalConstraint(BaseModel):
    """A constraint limiting legal interpretation."""
    constraint_id: str
    constraint_source: str  # "Constitution", "Statute", "Precedent"
    constraint_text: str
    severity: ConstraintSeverity
    affected_operations: List[str]  # Which downstream operations are constrained

class Precedent(BaseModel):
    """Applicable judicial precedent."""
    case_name: str
    citation: str
    court: str
    year: int
    relevance_score: float
    relevance_reason: str

class LegalLayer(BaseModel):
    """A layer of legal framework."""
    layer_type: LegalLayerType
    statutes: List[ApplicableStatute]
    rules: List[LegalRule]
    constraints: List[LegalConstraint]
    precedents: List[Precedent]
    layer_confidence: float = Field(ge=0.0, le=1.0)

class RoutingDecision(BaseModel):
    """Record of why a statute was included."""
    statute: str
    decision_type: str  # "INCLUDED", "EXCLUDED", "CONDITIONAL"
    reasoning: str
    evidence: List[str]
    confidence: float
    timestamp: datetime

class LegalDependencyInfo(BaseModel):
    """Information about statute dependencies."""
    statute: str
    requires: List[str]  # Statutes that must be included if this is
    depends_on: List[str]  # Statutes this depends on
    conflicts_with: List[str]  # Statutes that cannot coexist
    enabled_by: List[str]  # Statutes that enable this

class ApplicableLegalGraph(BaseModel):
    """
    Complete legal regime for a case.
    This is the primary output of the Legal Regime Router.
    """
    
    # Identification
    case_id: str
    timestamp: datetime
    routing_version: str = "2.0.0"
    
    # Legal layers
    substantive_layer: LegalLayer
    procedural_layer: LegalLayer
    evidence_layer: LegalLayer
    constitutional_layer: LegalLayer
    special_restrictions_layer: LegalLayer
    judicial_guidelines_layer: LegalLayer
    
    # Graph structure
    dependency_graph: Dict[str, LegalDependencyInfo]
    
    # Confidence and validity
    graph_confidence: float = Field(ge=0.0, le=1.0)
    graph_valid: bool
    validation_errors: List[str] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)
    
    # Decision trail
    routing_decisions: List[RoutingDecision]
    
    # Manual review flags
    manual_review_required: bool
    manual_review_reason: Optional[str] = None
    manual_review_context: Optional[Dict[str, Any]] = None
    
    # Readiness for downstream stages
    stages_ready: Dict[str, bool]  # e.g., {"Stage3": True, "Stage4": True}
    
    @validator('graph_confidence')
    def validate_confidence(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
```

---

## 14. LEGAL REGIME ROUTER PUBLIC API

```python
# legal_regime_router_api.py

class LegalRegimeRouter:
    """
    Public API for the Legal Regime Router.
    
    Builds applicable legal graphs for cases.
    """
    
    def __init__(self, config_path: str = "config/legal_regimes/"):
        """Initialize router with legal regime configurations."""
        self.config_path = config_path
        self._load_legal_regimes()
        self._load_rule_engine()
        self._load_ontology()
        self._load_dependency_graph()
    
    def route(self, routing_input: LegalRegimeRoutingInput) -> ApplicableLegalGraph:
        """
        Build applicable legal graph for a case.
        
        This is the main entry point. It orchestrates all graph-building stages.
        
        Args:
            routing_input: Case data and legal indicators
            
        Returns:
            ApplicableLegalGraph with complete legal regime
            
        Raises:
            RoutingError: If routing fails
        """
        # Stage 1: Extract indicators
        # Stage 2: Determine primary statute
        # Stage 3: Build substantive layer
        # Stage 4: Build procedural layer
        # Stage 5: Build evidence layer
        # Stage 6: Build constitutional layer
        # Stage 7: Build special restrictions layer
        # Stage 8: Build judicial guidelines layer
        # Stage 9: Validate graph consistency
        # Stage 10: Return graph
        pass
    
    def build_substantive_layer(
        self,
        primary_statute: str,
        applicable_statutes: List[str],
        legal_indicators: LegalIndicators
    ) -> LegalLayer:
        """Build substantive law layer."""
        pass
    
    def build_procedural_layer(
        self,
        applicable_statutes: List[str],
        jurisdiction: str
    ) -> LegalLayer:
        """Build procedural law layer (BNSS for criminal)."""
        pass
    
    def build_evidence_layer(
        self,
        applicable_statutes: List[str]
    ) -> LegalLayer:
        """Build evidence law layer (BSA for criminal)."""
        pass
    
    def build_constitutional_layer(
        self,
        applicable_statutes: List[str],
        legal_indicators: LegalIndicators
    ) -> LegalLayer:
        """Build constitutional constraints layer."""
        pass
    
    def build_special_restrictions_layer(
        self,
        applicable_statutes: List[str],
        legal_indicators: LegalIndicators
    ) -> LegalLayer:
        """Build special restrictions layer (bail rules, sentencing, etc.)."""
        # Execute rule engine here
        pass
    
    def build_judicial_guidelines_layer(
        self,
        applicable_statutes: List[str]
    ) -> LegalLayer:
        """Build judicial guidelines layer (precedents, practices)."""
        pass
    
    def validate_graph_consistency(self, graph: ApplicableLegalGraph) -> bool:
        """Validate graph for contradictions and missing requirements."""
        pass
    
    def execute_rule_engine(
        self,
        rules: List[LegalRule],
        case_context: Dict[str, Any]
    ) -> List[RuleExecutionResult]:
        """Execute deterministic rule engine."""
        pass
    
    def add_legal_regime(
        self,
        statute_code: str,
        regime_config: Dict[str, Any]
    ) -> None:
        """Add support for new statute/legal regime."""
        pass
    
    def get_dependency_graph(self, statute: str) -> networkx.DiGraph:
        """Get dependency graph for a statute."""
        pass
    
    def explain_routing_decision(self, graph: ApplicableLegalGraph, statute: str) -> str:
        """Generate human-readable explanation for why statute was included."""
        pass
```

---

## 15. COMPARISON: OLD vs NEW ARCHITECTURE

### Old Architecture (Statute Router)

```
Input: Case facts
  ↓
Output: Primary Statute ("NDPS")
  ↓
Problem: Downstream stages must figure out:
  - Which procedural rules apply
  - Which evidence rules apply
  - Which constitutional constraints apply
  - Which bail rules apply
  - Which precedents are relevant
```

### New Architecture (Legal Regime Router)

```
Input: Case facts
  ↓
Output: ApplicableLegalGraph with:
  - Substantive Layer (NDPS Section 20)
  - Procedural Layer (BNSS Sections 176-182)
  - Evidence Layer (BSA Sections 25-26)
  - Constitutional Layer (Article 21)
  - Special Restrictions (Section 37 bail rule)
  - Judicial Guidelines (Relevant precedents)
  ↓
Benefit: Downstream stages know EXACTLY which framework applies
```

**Key Difference:** From **classification** (statute X) to **framework** (legal graph).

---

## 16. RESEARCH NOVELTY

This architecture introduces:

### 1. Applicable Legal Graph
- GraphRAG-native design
- Represents legal reasoning as **structured knowledge graph**
- Enables semantic legal reasoning

### 2. Legal Dependency Graph
- Explicit representation of statute dependencies
- Enables automatic consistency checking
- Enables automatic completeness checking

### 3. Legal Ontology
- Semantic legal concepts (Possession, Minor, Commercial Quantity)
- Concept → Statutes mapping
- Enables semantic retrieval instead of keyword matching

### 4. Rule Engine
- Deterministic legal rule execution
- No LLM hallucination
- Transparent, auditable, reproducible

### 5. Versioned Legal Knowledge
- Support for statute amendments over time
- Date-aware statute selection
- Historical reasoning capability

### 6. Multi-Layer Legal Framework
- Explicit separation of substantive, procedural, evidence, constitutional layers
- Matches how courts actually reason
- Enables layer-specific reasoning by downstream stages

---

## 17. FUTURE ROADMAP

### Phase 1: Legal Regime Router (This Document)
- Basic legal graph construction
- Rule engine for special restrictions
- Precedent mapping

### Phase 2: Semantic Legal Reasoning
- Expand ontology
- Enable semantic reasoning across layers
- Concept-based precedent retrieval

### Phase 3: Multi-Jurisdiction Support
- Support international jurisdictions
- Jurisdiction-specific legal regimes
- Cross-jurisdictional comparison

### Phase 4: Machine Learning Integration
- Train ML on routing decisions
- Learn statute patterns
- Improve confidence prediction

### Phase 5: Explainable AI
- Detailed routing explanations
- Counterfactual reasoning
- What-if analysis

---

## SUMMARY

The Legal Regime Router represents a **paradigm shift** from statute classification to legal framework construction.

### Before
- Classify → NDPS
- Reason about NDPS

### After
- Build Legal Graph → [Substantive, Procedural, Evidence, Constitutional, Special Restrictions, Judicial Guidelines]
- Reason about complete legal framework

This is **research-grade legal AI** architecture, not just statute classification.

