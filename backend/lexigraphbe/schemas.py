"""
Pydantic Schemas for Stage 0 & Stage 1: LexiGraph Backend.
Stage 0: Case Intake & Context Initialization -> CaseContextObject
Stage 1: Query Understanding & Legal Decomposition -> LegalQueryObject
"""

import datetime
from typing import Dict, List, Optional, Tuple, Union, Any
from pydantic import BaseModel, Field, field_validator

# Explicit Mandatory Fields required for Stage 1 downstream legal agents
STAGE1_MANDATORY_FIELDS = [
    "accused_identity",
    "offence_narrative",
    "requested_relief",
    "procedural_stage",
    "legal_regime",
]

# Universal Baseline Procedural Documents checklist (same for every case, zero offence-specific inferencing)
UNIVERSAL_PROCEDURAL_DOCUMENTS = [
    "FIR / Complaint Copy",
    "Bail Application Copy",
]


class LexiGraphBase(BaseModel):
    """
    Shared base class for all LexiGraph schema objects.
    Provides a universal validator that coerces any non-string entries in
    manual_review fields to strings, handling LLMs that return dicts or other
    non-string types in that field.
    """
    @field_validator("manual_review", mode="before", check_fields=False)
    @classmethod
    def coerce_manual_review_to_strings(cls, v):
        """Coerce any non-string items (e.g. dicts returned by LLM) to strings."""
        if isinstance(v, list):
            return [item if isinstance(item, str) else str(item) for item in v]
        return v


class CaseMetadata(BaseModel):
    case_id: Optional[str] = Field(default=None, description="Case ID if available")
    court: Optional[str] = Field(default=None, description="Court name (e.g. Sessions Court, High Court)")
    police_station: Optional[str] = Field(default=None, description="Police station name")
    fir_number: Optional[str] = Field(default=None, description="FIR Number (e.g. 123/2025)")
    fir_date: Optional[str] = Field(default=None, description="FIR Date")
    offence_date: Optional[str] = Field(default=None, description="Date of commission of the offence (Primary for Legal Regime precedence)")
    state: Optional[str] = Field(default=None, description="State")
    district: Optional[str] = Field(default=None, description="District")


class AccusedParty(BaseModel):
    name: str = Field(description="Name or identity of accused person (e.g. Husband, Father-in-law, A1, A2)")
    relationship: Optional[str] = Field(default=None, description="Relationship to victim/complainant (e.g. Husband, Mother-in-Law)")
    role_alleged: Optional[str] = Field(default=None, description="Role alleged in offence (e.g. Main Accused, Co-Accused, In-Law)")
    bail_status: Optional[str] = Field(default=None, description="Status regarding bail (e.g. Seeking Anticipatory Bail, Arrested, Not Arrested)")


class Parties(BaseModel):
    complainant: Union[List[str], str, None] = Field(default=None, description="Complainant name(s) or identity")
    victim: Union[List[str], str, None] = Field(default=None, description="Victim name(s) or identity")
    accused: Union[List[AccusedParty], List[str], str, None] = Field(
        default=None,
        description="Array of multiple accused persons or string identity (e.g. Husband, In-Laws, Co-Accused A1, A2)"
    )
    relationship: Optional[str] = Field(default=None, description="Relationship between parties")


class PrimaryParticipants(BaseModel):
    victim: Union[List[str], str, None] = Field(default=None, description="Victim(s) identified")
    accused: Union[List[AccusedParty], List[str], str, None] = Field(default=None, description="Accused identified (array or string)")
    witnesses: Union[List[str], str, None] = Field(default=None, description="Witnesses identified")
    investigating_officer: Optional[str] = Field(default=None, description="Investigating Officer name")
    advocate: Optional[str] = Field(default=None, description="Advocate name if mentioned")


class LowConfidenceField(BaseModel):
    field_name: str = Field(description="Name of the extracted field with confidence below threshold")
    confidence_score: float = Field(description="Confidence score returned by agent (0.0 to 1.0)")
    cutoff_threshold: float = Field(default=0.70, description="Minimum confidence cutoff threshold applied")
    extracted_value: Optional[Any] = Field(default=None, description="Value extracted for the low-confidence field")
    action_required: str = Field(
        default="Flagged for human/verifier confirmation prior to downstream legal reasoning.",
        description="Explicit action taken for this low confidence field"
    )


class CaseProfile(BaseModel):
    case_metadata: CaseMetadata = Field(default_factory=CaseMetadata)
    parties: Parties = Field(default_factory=Parties)
    procedural_stage: Optional[str] = Field(
        default="UNKNOWN",
        description="Identified procedural stage (e.g. FIR Registered, Investigation, Arrest, Anticipatory Bail, Regular Bail, Charge Sheet Filed, Trial, Appeal)"
    )
    requested_relief: Optional[str] = Field(
        default="UNKNOWN",
        description="Requested legal relief (e.g. Anticipatory Bail, Regular Bail, Quashing, Appeal, Revision)"
    )
    legal_regime: Optional[str] = Field(
        default="UNKNOWN",
        description="Applicable legal regime: 'IPC + CrPC', 'BNS + BNSS', or 'UNKNOWN'"
    )
    flag_for_confirmation: bool = Field(
        default=False,
        description="True if legal regime or any extracted field requires manual human confirmation (ambiguous regime or confidence < threshold)"
    )
    regime_notes: Optional[str] = Field(
        default=None,
        description="Explanatory notes on legal regime precedence decision (e.g. Offence committed pre-July 1 2024 -> IPC+CrPC)"
    )
    min_confidence_threshold: float = Field(
        default=0.70,
        description="Explicit cutoff threshold for field confidence scores. Fields below this cutoff are flagged."
    )
    low_confidence_fields: List[LowConfidenceField] = Field(
        default_factory=list,
        description="List of fields whose confidence score falls below min_confidence_threshold"
    )
    overall_confidence: float = Field(
        default=1.0,
        description="Average confidence score across all extracted fields"
    )
    # Stage 1 Hard Contract Status & Violations
    contract_status: str = Field(
        default="UNCHECKED",
        description="Stage 1 Hard Contract status: 'CONTRACT_PASSED', 'CONTRACT_WARNING', or 'CONTRACT_BLOCKED'"
    )
    contract_violations: List[str] = Field(
        default_factory=list,
        description="List of Stage 1 hard contract mandatory field violations"
    )
    documents: List[str] = Field(default_factory=list, description="List of uploaded/available documents")
    case_facts: Optional[str] = Field(default="", description="Complete factual narrative preserved exactly as understood")
    primary_participants: PrimaryParticipants = Field(default_factory=PrimaryParticipants)
    missing_information: List[str] = Field(default_factory=list, description="Explicit list of missing important fields/documents or confirmation warnings")
    confidence: Dict[str, float] = Field(
        default_factory=dict,
        description="Confidence scores between 0.0 and 1.0 for extracted fields"
    )

    def get_accused_list(self) -> List[str]:
        """
        Helper method returning a normalized list of string names for all accused parties.
        Supports single strings, list of strings, and list of AccusedParty objects.
        """
        raw_accused_sources = [self.parties.accused, self.primary_participants.accused]
        accused_names = []

        for src in raw_accused_sources:
            if not src:
                continue
            if isinstance(src, str):
                if src.strip():
                    accused_names.append(src.strip())
            elif isinstance(src, list):
                for item in src:
                    if isinstance(item, str) and item.strip():
                        accused_names.append(item.strip())
                    elif isinstance(item, AccusedParty):
                        accused_names.append(item.name)
                    elif isinstance(item, dict) and "name" in item:
                        accused_names.append(str(item["name"]))
            elif isinstance(src, AccusedParty):
                accused_names.append(src.name)

        # Return unique non-empty names while preserving order
        seen = set()
        result = []
        for name in accused_names:
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def check_procedural_missing_documents(self) -> List[str]:
        """
        Checks missing documents against the Universal Procedural Baseline Checklist
        without performing any premature offence-specific legal reasoning.
        """
        doc_strings_lower = [str(d).lower() for d in self.documents]
        procedural_missing = []

        # Check FIR presence
        if not any("fir" in d or "complaint" in d for d in doc_strings_lower):
            msg = "Procedural Document Missing: FIR / Complaint Copy"
            if msg not in self.missing_information:
                self.missing_information.append(msg)
                procedural_missing.append(msg)

        # Check Bail Application presence
        if not any("bail" in d or "application" in d for d in doc_strings_lower):
            msg = "Procedural Document Missing: Bail Application Copy"
            if msg not in self.missing_information:
                self.missing_information.append(msg)
                procedural_missing.append(msg)

        return procedural_missing

    def validate_stage1_contract(self) -> Tuple[str, List[str]]:
        """
        Enforces Stage 1 Hard Contract verification on the CaseProfile.
        Returns Tuple of (contract_status, contract_violations).
        """
        violations = []

        # 1. Accused Identity Check (supports multi-party array)
        accused_list = self.get_accused_list()
        if not accused_list:
            violations.append("MANDATORY FIELD MISSING: 'accused_identity' (parties.accused / primary_participants.accused is null/empty)")

        # 2. Offence Narrative Check
        if not self.case_facts or not self.case_facts.strip():
            violations.append("MANDATORY FIELD MISSING: 'offence_narrative' (case_facts is empty/blank)")

        # 3. Requested Relief Check
        if not self.requested_relief or self.requested_relief in ("UNKNOWN", "null", ""):
            violations.append("MANDATORY FIELD MISSING: 'requested_relief' (requested_relief is UNKNOWN or unstated)")

        # 4. Procedural Stage Check
        if not self.procedural_stage or self.procedural_stage in ("UNKNOWN", "null", ""):
            violations.append("MANDATORY FIELD MISSING: 'procedural_stage' (procedural_stage is UNKNOWN or unstated)")

        # 5. Legal Regime Check
        if not self.legal_regime or self.legal_regime in ("UNKNOWN", "null", ""):
            if not self.flag_for_confirmation:
                violations.append("MANDATORY FIELD UNRESOLVED: 'legal_regime' is UNKNOWN without flag_for_confirmation set")

        self.contract_violations = violations
        if not violations:
            if self.flag_for_confirmation or self.low_confidence_fields:
                self.contract_status = "CONTRACT_WARNING"
            else:
                self.contract_status = "CONTRACT_PASSED"
        else:
            self.contract_status = "CONTRACT_BLOCKED"

        return self.contract_status, self.contract_violations


class CaseContextObject(BaseModel):
    """
    Standardized Case Context Object produced by Stage 0.
    Immutable contract consumed directly by all downstream legal agents
    (LexiGraph, Prosecutor Agent, Defence Agent, Judge Agent).
    """
    schema_version: str = Field(default="1.0", description="Schema version of Case Context Object contract")
    case_profile: CaseProfile = Field(description="Validated structured case profile from Stage 0")
    contract_status: str = Field(description="Stage 1 contract status: CONTRACT_PASSED, CONTRACT_WARNING, CONTRACT_BLOCKED")
    contract_violations: List[str] = Field(default_factory=list, description="List of contract violations if blocked/warning")
    verification_status: str = Field(description="Tier 1 verification status: VERIFIED or NEEDS_CORRECTION")
    active_parties: List[str] = Field(default_factory=list, description="Normalized list of accused party names for downstream routing")
    system_metadata: Dict[str, Any] = Field(default_factory=dict, description="System metadata including intake timestamp, overall confidence score")

    def to_downstream_json(self) -> str:
        """Serializes the exact standardized Case Context Object to JSON string for downstream agents."""
        return self.model_dump_json(indent=2)

    @property
    def legal_regime(self) -> str:
        """Convenience accessor for legal_regime from underlying CaseProfile."""
        if self.case_profile:
            return self.case_profile.legal_regime or "IPC + CrPC"
        return "IPC + CrPC"


class VerificationIssue(BaseModel):
    field: str = Field(description="Target field with issue")
    issue: str = Field(description="Description of the issue or discrepancy")
    feedback: str = Field(description="Actionable feedback for intake agent correction")


class VerificationResult(BaseModel):
    status: str = Field(description="Verification status: 'VERIFIED' or 'NEEDS_CORRECTION'")
    contract_status: str = Field(default="UNCHECKED", description="Stage 1 Hard Contract status: 'CONTRACT_PASSED', 'CONTRACT_WARNING', 'CONTRACT_BLOCKED'")
    issues: List[VerificationIssue] = Field(default_factory=list, description="List of identified issues if status is NEEDS_CORRECTION")
    feedback: Optional[str] = Field(default=None, description="Overall verification feedback summary")
    verified_case_profile: Optional[CaseProfile] = Field(default=None, description="The verified CaseProfile if status is VERIFIED")

    def export_case_context_object(self) -> CaseContextObject:
        """
        Exports the verified CaseProfile as an immutable, standardized CaseContextObject for downstream legal agents.
        """
        profile = self.verified_case_profile or CaseProfile()
        status, violations = profile.validate_stage1_contract()

        return CaseContextObject(
            schema_version="1.0",
            case_profile=profile,
            contract_status=status,
            contract_violations=violations,
            verification_status=self.status,
            active_parties=profile.get_accused_list(),
            system_metadata={
                "intake_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "overall_confidence": profile.overall_confidence,
                "low_confidence_count": len(profile.low_confidence_fields),
                "flag_for_confirmation": profile.flag_for_confirmation,
            }
        )


class IntakeInput(BaseModel):
    documents_text: Optional[str] = Field(default="", description="Raw text extracted from case documents (FIR, Complaint, etc.)")
    user_query: Optional[str] = Field(default="", description="User query or special instructions")
    role: Optional[str] = Field(default=None, description="User role: Prosecutor / Defence / Judge")
    court_type: Optional[str] = Field(default=None, description="Court type: Sessions Court / High Court")
    legal_regime_override: Optional[str] = Field(default=None, description="User supplied legal regime if specified")
    min_confidence_threshold: float = Field(default=0.70, description="Cutoff threshold for field confidence score actions")


# ==============================================================================
# STAGE 1 SCHEMAS — QUERY UNDERSTANDING & LEGAL DECOMPOSITION (LegalQueryObject)
# ==============================================================================

class LegalConceptItem(BaseModel):
    concept: str = Field(description="Name of identified independent legal concept (e.g. Dowry Demand, Criminal Intimidation)")
    confidence: float = Field(description="Confidence score for this legal concept (0.0 to 1.0)")


class SubQueryItem(BaseModel):
    id: str = Field(description="Unique sub-query identifier (e.g. SQ1, SQ2)")
    query: str = Field(description="Single-issue legal sub-query string without statutory section numbers")
    concept: str = Field(description="Corresponding legal concept associated with this sub-query")
    target_parties: List[str] = Field(
        default_factory=list,
        description="Explicit list of target accused or party names/roles this sub-query pertains to (e.g. ['Husband'], ['Father-in-law'])"
    )
    role_alleged: Optional[str] = Field(
        default=None,
        description="Alleged role or act attribution for target party (e.g. Direct Physical Assault, Abetment, Financial Demand)"
    )


class ImportantFacts(BaseModel):
    money: Optional[Union[str, List[str]]] = Field(default=None, description="Financial transaction/dowry/entrustment monetary details")
    location: Optional[Union[str, List[str]]] = Field(default=None, description="Offence or procedural location details")
    dates: Optional[Union[str, List[str]]] = Field(default=None, description="Key dates mentioned in factual narrative")
    weapon: Optional[Union[str, List[str]]] = Field(default=None, description="Weapon or instrument details if mentioned")
    medical_injury: Optional[Union[str, List[str]]] = Field(default=None, description="Medical injury details if mentioned")
    electronic_evidence: Optional[Union[str, List[str]]] = Field(default=None, description="Electronic evidence details if mentioned")
    documents: List[str] = Field(default_factory=list, description="Documents mentioned or available")
    witnesses: List[str] = Field(default_factory=list, description="Witnesses identified in factual narrative")


class LegalQueryObject(LexiGraphBase):
    """
    Standardized Stage 1 LegalQueryObject produced by Query Understanding Agent.
    Independent of any IPC/BNS section numbers or chapter titles.
    Consumed by Stage 2 Retrieval Pipeline.
    """
    schema_version: str = Field(default="1.0", description="Schema version of LegalQueryObject contract")
    case_type: str = Field(default="Anticipatory Bail", description="Case procedural type or requested relief")
    entities: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Categorized entities identified (e.g. victim: ['Wife'], accused: ['Husband', 'Father-in-law'])"
    )
    relationship: List[str] = Field(
        default_factory=list,
        description="Identified relationships between parties (e.g. ['Husband-Wife', 'In-laws'])"
    )
    legal_concepts: List[LegalConceptItem] = Field(
        default_factory=list,
        description="List of extracted independent legal concepts with confidence scores"
    )
    sub_queries: List[SubQueryItem] = Field(
        default_factory=list,
        description="List of single-issue legal sub-queries"
    )
    procedural_events: List[str] = Field(
        default_factory=list,
        description="List of procedural events identified (e.g. Marriage, FIR Registered, Anticipatory Bail Application)"
    )
    important_facts: ImportantFacts = Field(default_factory=ImportantFacts)
    manual_review: List[str] = Field(
        default_factory=list,
        description="List of legal concepts or sub-queries flagged for manual review (confidence < 0.70 threshold)"
    )
    # Passthrough fields from Stage 0 CaseContextObject (never re-derived)
    legal_regime: Optional[str] = Field(
        default="UNKNOWN",
        description="Legal regime passed through unchanged from Stage 0 CaseContextObject ('IPC + CrPC' or 'BNS + BNSS')"
    )
    flag_for_confirmation: bool = Field(
        default=False,
        description="Flag for confirmation passed through unchanged from Stage 0"
    )
    regime_notes: Optional[str] = Field(
        default=None,
        description="Regime notes passed through unchanged from Stage 0"
    )
    verification_status: str = Field(
        default="PENDING",
        description="Verification status: PENDING, VERIFIED, or RETRY"
    )

    def to_downstream_json(self) -> str:
        """Serializes the exact LegalQueryObject to JSON string for Stage 2 retrieval."""
        return self.model_dump_json(indent=2)


# ==============================================================================
# STAGE 2 SCHEMAS (Sub-Query to Chapter Candidate Batched Mapping)
# ==============================================================================

class Stage2VerificationIssue(BaseModel):
    target: str = Field(description="Target sub-query ID or legal concept")
    issue: str = Field(description="Detailed explanation of Stage 2 mapping verification issue")
    feedback: str = Field(description="Actionable feedback for Stage 2 mapping agent correction")


class Stage2VerificationResult(BaseModel):
    status: str = Field(description="Status: 'VERIFIED' or 'RETRY'")
    issues: List[Stage2VerificationIssue] = Field(default_factory=list, description="List of mapping audit issues")
    feedback: str = Field(default="Stage 2 sub-query mapping audit complete.", description="Overall summary feedback")
    batched_mapping_response: Optional[Any] = Field(default=None, description="Verified Stage2BatchedMappingResponse")


# ==============================================================================
# STAGE 3 SCHEMAS (Chapter & Section Title Identification)
# ==============================================================================

class ChapterCandidateItem(BaseModel):
    concept: str = Field(description="Legal concept from Stage 1 (e.g. 'Dowry Demand')")
    chapter_number: str = Field(description="Chapter number (e.g. 'XXA', 'XXII')")
    chapter_name: str = Field(description="Chapter name (e.g. 'Of Cruelty by Husband or Relatives')")
    confidence: float = Field(description="Confidence score for chapter relevance (0.0 to 1.0)")


class SectionCandidateItem(BaseModel):
    concept: str = Field(description="Matching legal concept from Stage 1")
    section_number: str = Field(description="Section number (e.g. '498A', '506')")
    section_title: str = Field(description="Section title (e.g. 'Cruelty by Husband or Relatives')")
    confidence: float = Field(description="Confidence score for section candidate (0.0 to 1.0)")


class ChapterIdentificationObject(LexiGraphBase):
    """
    Standardized Stage 3 ChapterIdentificationObject contract.
    Contains candidate chapters and candidate section titles identified from lightweight index.
    Zero statutory body text (no explanations, illustrations, punishments, exceptions, or provisos).
    """
    schema_version: str = Field(default="1.0", description="Schema version of ChapterIdentificationObject contract")
    chapter_candidates: List[ChapterCandidateItem] = Field(
        default_factory=list,
        description="List of shortlisted candidate chapters per legal concept"
    )
    section_candidates: List[SectionCandidateItem] = Field(
        default_factory=list,
        description="List of shortlisted candidate section titles ranked by confidence"
    )
    legal_regime: Optional[str] = Field(
        default="UNKNOWN",
        description="Legal regime passed through unchanged from Stage 1 ('IPC + CrPC' or 'BNS + BNSS')"
    )
    manual_review: List[str] = Field(
        default_factory=list,
        description="Candidates or concepts with confidence < 0.70 flagged for manual review"
    )

    verification_status: str = Field(
        default="PENDING",
        description="Verification status: PENDING, VERIFIED, or RETRY"
    )

    def to_downstream_json(self) -> str:
        """Serializes ChapterIdentificationObject to JSON string for Stage 4 verification."""
        return self.model_dump_json(indent=2)


class ChapterVerificationIssue(BaseModel):
    target: str = Field(description="Target chapter or section candidate ID/name")
    issue: str = Field(description="Detailed explanation of verification issue found")
    feedback: str = Field(description="Actionable feedback for correction")


class ChapterVerificationResult(BaseModel):
    status: str = Field(description="Status: 'VERIFIED' or 'RETRY'")
    issues: List[ChapterVerificationIssue] = Field(default_factory=list, description="List of issues identified")
    feedback: str = Field(default="Verification complete.", description="Overall summary feedback")
    verified_chapter_object: Optional[ChapterIdentificationObject] = Field(default=None, description="Verified ChapterIdentificationObject")


# ==============================================================================
# STAGE 4 SCHEMAS (Full Statutory Verification & Ingredient Matching)
# ==============================================================================

class StatutoryIngredientItem(BaseModel):
    ingredient: str = Field(description="Essential statutory legal ingredient or statutory clause")
    logical_operator: str = Field(
        default="MANDATORY",
        description="Logical operator: 'MANDATORY' (or 'AND') for mandatory elements, 'OR' for disjunctive statutory branches"
    )
    condition_group: Optional[str] = Field(
        default="default",
        description="Grouping identifier for disjunctive OR conditions (e.g. 'Cruelty_Disjunctive_Branches')"
    )
    status: str = Field(description="Status of ingredient: 'Satisfied', 'Not Satisfied', or 'Insufficient Evidence'")
    reason: str = Field(description="Reasoning grounded strictly in available case facts")


class VerifiedSectionItem(BaseModel):
    section_number: str = Field(description="Section number (e.g. '498A', '506', '85')")
    section_title: str = Field(description="Section title (e.g. 'Cruelty by Husband or Relatives')")
    punishment_text: Optional[str] = Field(
        default=None,
        description="Extracted punishment text (e.g. 'Imprisonment up to 3 years and fine')"
    )
    max_imprisonment_years: Optional[float] = Field(
        default=None,
        description="Maximum term of imprisonment in years (e.g. 3.0, 7.0, 10.0)"
    )
    arnesh_kumar_threshold_exceeded: bool = Field(
        default=False,
        description="True if max imprisonment > 7 years (Arnesh Kumar threshold exceeded), False if <= 7 years"
    )
    ingredients: List[StatutoryIngredientItem] = Field(
        default_factory=list,
        description="List of essential statutory ingredients evaluated against case facts"
    )
    disjunctive_clause_applied: Optional[str] = Field(
        default=None,
        description="Applied disjunctive clause for OR statutes (e.g. 'Satisfied via Clause (a) Willful Conduct / Grave Injury')"
    )
    overall_confidence: float = Field(description="Overall applicability confidence score (0.0 to 1.0)")

    def is_statutorily_satisfied(self) -> bool:
        """
        Evaluates whether the section is statutorily satisfied taking disjunctive OR branches into account.
        - All MANDATORY / AND ingredients must be 'Satisfied'.
        - For each condition_group with 'OR' operators, AT LEAST ONE ingredient in that group must be 'Satisfied'.
        """
        if not self.ingredients:
            return False

        mandatory_items = [ing for ing in self.ingredients if ing.logical_operator in ("MANDATORY", "AND")]
        or_groups: Dict[str, List[StatutoryIngredientItem]] = {}
        for ing in self.ingredients:
            if ing.logical_operator == "OR":
                group_key = ing.condition_group or "default_or_group"
                if group_key not in or_groups:
                    or_groups[group_key] = []
                or_groups[group_key].append(ing)

        all_mandatory_ok = all(ing.status == "Satisfied" for ing in mandatory_items)
        if not all_mandatory_ok:
            return False

        for group_key, items in or_groups.items():
            if not any(ing.status == "Satisfied" for ing in items):
                return False

        return True


class StatutoryVerificationObject(LexiGraphBase):
    """
    Standardized Stage 4 StatutoryVerificationObject contract.
    Contains verified statutory sections with evaluated legal ingredients and applicability confidence scores.
    Zero hallucinated facts, zero guilt determination, zero bail recommendations.
    """
    schema_version: str = Field(default="1.0", description="Schema version of StatutoryVerificationObject contract")
    verified_sections: List[VerifiedSectionItem] = Field(
        default_factory=list,
        description="List of verified statutory sections ranked by overall confidence score"
    )
    legal_regime: Optional[str] = Field(
        default="UNKNOWN",
        description="Legal regime passed through unchanged from Stage 3 ('IPC + CrPC' or 'BNS + BNSS')"
    )
    manual_review: List[str] = Field(
        default_factory=list,
        description="Sections or ingredients with confidence < 0.70 flagged for manual review"
    )
    verification_status: str = Field(
        default="PENDING",
        description="Verification status: PENDING, VERIFIED, or RETRY"
    )

    def to_downstream_json(self) -> str:
        """Serializes StatutoryVerificationObject to JSON string for downstream argument synthesis engines."""
        return self.model_dump_json(indent=2)


class StatutoryVerificationIssue(BaseModel):
    target: str = Field(description="Target section number or ingredient with error")
    issue: str = Field(description="Detailed description of statutory verification audit issue")
    feedback: str = Field(description="Actionable instructions for statutory verification agent correction")


class StatutoryVerificationResult(BaseModel):
    status: str = Field(description="Status: 'VERIFIED' or 'RETRY'")
    issues: List[StatutoryVerificationIssue] = Field(default_factory=list, description="List of audit issues identified")
    feedback: str = Field(default="Statutory verification audit complete.", description="Overall summary feedback")
    verified_statutory_object: Optional[StatutoryVerificationObject] = Field(default=None, description="Verified StatutoryVerificationObject")


# ==============================================================================
# STAGE 5 SCHEMAS (Anticipatory Bail Reasoning Engine)
# ==============================================================================

class BailFactorEvaluationItem(BaseModel):
    value: str = Field(description="Evaluated factor value e.g. 'High', 'Medium', 'Low', 'Required', 'Not Required', 'Strong', 'Weak', 'None', 'Cooperative'")
    reason: Optional[str] = Field(default=None, description="Factual justification grounded strictly in available case facts")


class BailEvaluationMap(BaseModel):
    gravity_of_offence: BailFactorEvaluationItem = Field(description="Gravity of accusation evaluation")
    prima_facie_case: BailFactorEvaluationItem = Field(description="Prima facie case evaluation based on Stage 4 verified statutory ingredients")
    custodial_interrogation: BailFactorEvaluationItem = Field(description="Custodial interrogation requirement assessment")
    witness_tampering: BailFactorEvaluationItem = Field(description="Witness tampering / intimidation risk assessment")
    evidence_tampering: BailFactorEvaluationItem = Field(description="Evidence tampering risk assessment")
    flight_risk: BailFactorEvaluationItem = Field(description="Flight risk assessment")
    criminal_antecedents: BailFactorEvaluationItem = Field(description="Criminal antecedents assessment")
    cooperation: BailFactorEvaluationItem = Field(description="Cooperation with investigation assessment")


class OverallBailRecommendation(BaseModel):
    decision: str = Field(description="Bail decision: 'Recommend Grant Anticipatory Bail', 'Recommend Reject Anticipatory Bail', or 'Recommend Conditional Anticipatory Bail'")
    confidence: float = Field(description="Overall decision confidence score (0.0 to 1.0)")
    summary_reasoning: Optional[str] = Field(default=None, description="Judicial reasoning summary supporting the bail decision")


class BailReasoningObject(LexiGraphBase):
    """
    Standardized Stage 5 BailReasoningObject contract.
    Contains judicial anticipatory bail evaluations under Sec 438 CrPC / Sec 482 BNSS without guilt determination.
    """
    schema_version: str = Field(default="1.0", description="Schema version of BailReasoningObject contract")
    bail_provision_applied: str = Field(default="Section 438 CrPC", description="Statutory bail provision applied ('Section 438 CrPC' or 'Section 482 BNSS')")
    legal_regime: Optional[str] = Field(default="UNKNOWN", description="Legal regime passed through unchanged ('IPC + CrPC' or 'BNS + BNSS')")
    bail_evaluation: BailEvaluationMap = Field(description="Structured evaluation of 8 judicially developed anticipatory bail factors")
    overall_recommendation: OverallBailRecommendation = Field(description="Overall judicial anticipatory bail recommendation")
    manual_review: List[str] = Field(default_factory=list, description="Bail factors or recommendations with confidence < 0.70 flagged for manual review")
    verification_status: str = Field(default="PENDING", description="Verification status: PENDING, VERIFIED, or RETRY")

    def to_downstream_json(self) -> str:
        """Serializes BailReasoningObject to JSON string."""
        return self.model_dump_json(indent=2)


class BailVerificationIssue(BaseModel):
    target: str = Field(description="Target bail factor or recommendation item with audit error")
    issue: str = Field(description="Detailed description of bail reasoning audit issue")
    feedback: str = Field(description="Actionable instructions for bail reasoning agent correction")


class BailVerificationResult(BaseModel):
    status: str = Field(description="Status: 'VERIFIED' or 'RETRY'")
    issues: List[BailVerificationIssue] = Field(default_factory=list, description="List of audit issues identified")
    feedback: str = Field(default="Bail reasoning verification audit complete.", description="Overall summary feedback")
    verified_bail_object: Optional[BailReasoningObject] = Field(default=None, description="Verified BailReasoningObject")


# ==============================================================================
# STAGE 6 SCHEMAS (Judicial Precedent Retrieval Engine)
# ==============================================================================

class PrecedentItem(BaseModel):
    case_name: str = Field(description="Name of precedent case (e.g. 'Arnesh Kumar v. State of Bihar')")
    court: str = Field(description="Court issuing judgment (e.g. 'Supreme Court' or 'High Court of Delhi')")
    citation: str = Field(description="Official legal citation (e.g. '(2014) 8 SCC 273')")
    facts: str = Field(description="Factual summary of precedent case")
    verified_offences: List[str] = Field(default_factory=list, description="Offences cited or evaluated in precedent (e.g. ['498A IPC', '506 IPC'])")
    bail_outcome: str = Field(description="Bail outcome granted in precedent (e.g. 'Anticipatory Bail Principles Applied', 'Conditional Bail Modified')")
    ratio_decidendi: str = Field(description="Binding ratio decidendi / legal principle established by court")
    similarity_score: float = Field(description="Relevance similarity score (0.0 to 1.0) compared to current case")


class PrecedentRetrievalObject(LexiGraphBase):
    """
    Standardized Stage 6 PrecedentRetrievalObject contract.
    Contains ranked judicial precedents with ratio decidendi, citations, and similarity scores.
    """
    schema_version: str = Field(default="1.0", description="Schema version of PrecedentRetrievalObject contract")
    precedents: List[PrecedentItem] = Field(default_factory=list, description="List of retrieved judicial precedents ranked by similarity score descending")
    manual_review: List[str] = Field(default_factory=list, description="Precedents with similarity_score < 0.70 flagged for manual review")
    verification_status: str = Field(default="PENDING", description="Verification status: PENDING, VERIFIED, or RETRY")

    def to_downstream_json(self) -> str:
        """Serializes PrecedentRetrievalObject to JSON string."""
        return self.model_dump_json(indent=2)


class PrecedentVerificationIssue(BaseModel):
    target: str = Field(description="Target precedent case name or property with audit issue")
    issue: str = Field(description="Detailed description of precedent retrieval verification issue")
    feedback: str = Field(description="Actionable instructions for Precedent Retrieval Agent correction")


class PrecedentVerificationResult(BaseModel):
    status: str = Field(description="Status: 'VERIFIED' or 'RETRY'")
    issues: List[PrecedentVerificationIssue] = Field(default_factory=list, description="List of audit issues identified")
    feedback: str = Field(default="Precedent retrieval verification audit complete.", description="Overall summary feedback")
    verified_precedent_object: Optional[PrecedentRetrievalObject] = Field(default=None, description="Verified PrecedentRetrievalObject")


# ==============================================================================
# STAGE 7 SCHEMAS (Role-Specific Argument Generation Engine)
# ==============================================================================

class ProsecutorArguments(BaseModel):
    verified_sections: List[str] = Field(default_factory=list, description="Verified statutory IPC/BNS section numbers")
    arguments: List[str] = Field(default_factory=list, description="Substantive prosecution arguments for rejection of anticipatory bail")
    precedents: List[str] = Field(default_factory=list, description="Citations of retrieved precedents supporting prosecution")
    prayer: str = Field(default="Reject anticipatory bail.", description="Formal prosecution prayer")


class DefenceArguments(BaseModel):
    arguments: List[str] = Field(default_factory=list, description="Substantive defence arguments for grant of anticipatory bail")
    precedents: List[str] = Field(default_factory=list, description="Citations of retrieved precedents supporting defence")
    prayer: str = Field(default="Grant anticipatory bail.", description="Formal defence prayer")


class JudgeOrder(BaseModel):
    issues: List[str] = Field(default_factory=list, description="Issues for determination before the court")
    facts_considered: List[str] = Field(default_factory=list, description="Verified facts considered")
    applicable_law: List[str] = Field(default_factory=list, description="Applicable statutory provisions and bail sections")
    statutory_analysis: str = Field(description="Judicial analysis of statutory ingredients satisfied/unsatisfied")
    bail_factor_analysis: str = Field(description="Judicial evaluation of 8 judicially developed bail factors")
    precedents: List[str] = Field(default_factory=list, description="Judicial precedents applied in order")
    reasoning: str = Field(description="Detailed impartial judicial reasoning leading to decision")
    decision: str = Field(description="Judicial decision: 'Grant' or 'Reject'")
    conditions: List[str] = Field(default_factory=list, description="Recommended bail conditions if granted, or N/A if rejected")


class RoleArgumentObject(LexiGraphBase):
    """
    Standardized Stage 7 RoleArgumentObject contract.
    Contains role-specific submissions for Prosecutor, Defence, and Judge.
    """
    schema_version: str = Field(default="1.0", description="Schema version of RoleArgumentObject contract")
    prosecutor_arguments: ProsecutorArguments = Field(description="Prosecution arguments supporting rejection of anticipatory bail")
    defence_arguments: DefenceArguments = Field(description="Defence arguments supporting grant of anticipatory bail")
    judge_order: JudgeOrder = Field(description="Judicial order containing issues, analysis, reasoning, decision, and conditions")
    manual_review: List[str] = Field(default_factory=list, description="Flagged argument items or conditions for manual review")
    verification_status: str = Field(default="PENDING", description="Verification status: PENDING, VERIFIED, or RETRY")

    def to_downstream_json(self) -> str:
        """Serializes RoleArgumentObject to JSON string."""
        return self.model_dump_json(indent=2)


class RoleArgumentVerificationIssue(BaseModel):
    target: str = Field(description="Target argument, precedent, or order section with audit error")
    issue: str = Field(description="Detailed description of argument verification audit issue")
    feedback: str = Field(description="Actionable instructions for Argument Generation Agent correction")


class RoleArgumentVerificationResult(BaseModel):
    status: str = Field(description="Status: 'VERIFIED' or 'RETRY'")
    issues: List[RoleArgumentVerificationIssue] = Field(default_factory=list, description="List of audit issues identified")
    feedback: str = Field(default="Argument verification audit complete.", description="Overall summary feedback")
    verified_role_argument_object: Optional[RoleArgumentObject] = Field(default=None, description="Verified RoleArgumentObject")


class QueryVerificationIssue(BaseModel):
    target: str = Field(description="Target sub-query or concept with error")
    issue: str = Field(description="Description of the issue (e.g. hallucinated concept, statutory section leak, multi-issue query)")
    feedback: str = Field(description="Actionable instructions for Query Understanding Agent correction")


class QueryVerificationResult(BaseModel):
    status: str = Field(description="Verification status: 'VERIFIED' or 'RETRY'")
    issues: List[QueryVerificationIssue] = Field(default_factory=list, description="List of identified issues if status is RETRY")
    feedback: Optional[str] = Field(default=None, description="Overall verification summary feedback")
    verified_query_object: Optional[LegalQueryObject] = Field(default=None, description="The verified LegalQueryObject if status is VERIFIED")
