"""
Stage 0 Pydantic Schemas: Case Intake & Context Initialization -> CaseContextObject
"""

import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field

from .common import UNIVERSAL_PROCEDURAL_DOCUMENTS, STAGE1_MANDATORY_FIELDS


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
    name: Optional[str] = Field(default="Unknown", description="Name or identity of accused person (e.g. Husband, Father-in-law, A1, A2)")
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
        default="IPC + CrPC",
        description="Applicable legal regime: 'IPC + CrPC' (default) or 'UNKNOWN'"
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
    confidence: Dict[str, Any] = Field(
        default_factory=dict,
        description="Confidence scores between 0.0 and 1.0 for extracted fields"
    )

    def get_accused_list(self) -> List[str]:
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
                        if item.name:
                            accused_names.append(item.name)
                    elif isinstance(item, dict) and "name" in item:
                        if item.get("name"):
                            accused_names.append(str(item["name"]))
            elif isinstance(src, AccusedParty):
                if src.name:
                    accused_names.append(src.name)

        seen = set()
        result = []
        for name in accused_names:
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def check_procedural_missing_documents(self) -> List[str]:
        doc_strings_lower = [str(d).lower() for d in self.documents]
        procedural_missing = []

        if not any("fir" in d or "complaint" in d for d in doc_strings_lower):
            msg = "Procedural Document Missing: FIR / Complaint Copy"
            if msg not in self.missing_information:
                self.missing_information.append(msg)
                procedural_missing.append(msg)

        if not any("bail" in d or "application" in d for d in doc_strings_lower):
            msg = "Procedural Document Missing: Bail Application Copy"
            if msg not in self.missing_information:
                self.missing_information.append(msg)
                procedural_missing.append(msg)

        return procedural_missing

    def validate_stage1_contract(self) -> Tuple[str, List[str]]:
        violations = []
        accused_list = self.get_accused_list()
        if not accused_list:
            violations.append("MANDATORY FIELD MISSING: 'accused_identity' (parties.accused / primary_participants.accused is null/empty)")

        if not self.case_facts or not self.case_facts.strip():
            violations.append("MANDATORY FIELD MISSING: 'offence_narrative' (case_facts is empty/blank)")

        if not self.requested_relief or self.requested_relief in ("UNKNOWN", "null", ""):
            violations.append("MANDATORY FIELD MISSING: 'requested_relief' (requested_relief is UNKNOWN or unstated)")

        if not self.procedural_stage or self.procedural_stage in ("UNKNOWN", "null", ""):
            violations.append("MANDATORY FIELD MISSING: 'procedural_stage' (procedural_stage is UNKNOWN or unstated)")

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
    schema_version: str = Field(default="1.0", description="Schema version of Case Context Object contract")
    case_profile: CaseProfile = Field(description="Validated structured case profile from Stage 0")
    contract_status: str = Field(description="Stage 1 contract status: CONTRACT_PASSED, CONTRACT_WARNING, CONTRACT_BLOCKED")
    contract_violations: List[str] = Field(default_factory=list, description="List of contract violations if blocked/warning")
    verification_status: str = Field(description="Tier 1 verification status: VERIFIED or NEEDS_CORRECTION")
    active_parties: List[str] = Field(default_factory=list, description="Normalized list of accused party names for downstream routing")
    system_metadata: Dict[str, Any] = Field(default_factory=dict, description="System metadata including intake timestamp, overall confidence score")

    def to_downstream_json(self) -> str:
        return self.model_dump_json(indent=2)

    @property
    def legal_regime(self) -> str:
        if self.case_profile:
            return self.case_profile.legal_regime or "IPC + CrPC"
        return "IPC + CrPC"


class IntakeInput(BaseModel):
    documents_text: Optional[str] = Field(default="", description="Raw text extracted from case documents (FIR, Complaint, etc.)")
    user_query: Optional[str] = Field(default="", description="User query or special instructions")
    role: Optional[str] = Field(default=None, description="User role: Prosecutor / Defence / Judge")
    court_type: Optional[str] = Field(default=None, description="Court type: Sessions Court / High Court")
    legal_regime_override: Optional[str] = Field(default=None, description="User supplied legal regime if specified")
    min_confidence_threshold: float = Field(default=0.70, description="Cutoff threshold for field confidence score actions")


class IntakeVerificationIssue(BaseModel):
    field: str = Field(description="Target field with issue")
    issue: str = Field(description="Description of issue")
    feedback: str = Field(description="Actionable feedback for correction")


class IntakeVerificationResult(BaseModel):
    status: str = Field(description="Verification status: 'VERIFIED' or 'NEEDS_CORRECTION'")
    contract_status: str = Field(default="UNCHECKED", description="Stage 1 Hard Contract status")
    issues: List[IntakeVerificationIssue] = Field(default_factory=list, description="List of issues")
    feedback: Optional[str] = Field(default=None, description="Overall summary feedback")
    verified_case_profile: Optional[CaseProfile] = Field(default=None, description="Verified CaseProfile")

    def export_case_context_object(self) -> CaseContextObject:
        profile = self.verified_case_profile or CaseProfile()
        status, violations = profile.validate_stage1_contract()
        accused_names = profile.get_accused_list()
        return CaseContextObject(
            schema_version="1.0",
            case_profile=profile,
            contract_status=status,
            contract_violations=violations,
            verification_status=self.status,
            active_parties=accused_names,
            system_metadata={
                "intake_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "overall_confidence": profile.overall_confidence,
                "low_confidence_count": len(profile.low_confidence_fields),
                "flag_for_confirmation": profile.flag_for_confirmation,
            }
        )
