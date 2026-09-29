"""
Stage 1 Pydantic Schemas: Query Understanding & Legal Decomposition -> LegalQueryObject
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator

from .common import ManualReviewMixin, _sanitize_manual_review


class EntityItem(BaseModel):
    name: str = Field(description="Entity name")
    entity_type: str = Field(default="PARTY", description="Type of entity e.g. ACCUSED, VICTIM")


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
    
    @field_validator('documents', 'witnesses', mode='before')
    @classmethod
    def convert_none_to_list(cls, v):
        """Convert None to empty list for list fields"""
        if v is None:
            return []
        return v


class LegalQueryObject(ManualReviewMixin):
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
        return self.model_dump_json(indent=2)


class QueryVerificationIssue(BaseModel):
    target: str = Field(description="Target sub-query or concept with error")
    issue: str = Field(description="Description of the issue (e.g. hallucinated concept, statutory section leak, multi-issue query)")
    feedback: str = Field(description="Actionable instructions for Query Understanding Agent correction")


class QueryVerificationResult(BaseModel):
    status: str = Field(description="Verification status: 'VERIFIED' or 'RETRY'")
    issues: List[QueryVerificationIssue] = Field(default_factory=list, description="List of identified issues if status is RETRY")
    feedback: Optional[str] = Field(default=None, description="Overall verification summary feedback")
    verified_query_object: Optional[LegalQueryObject] = Field(default=None, description="The verified LegalQueryObject if status is VERIFIED")
