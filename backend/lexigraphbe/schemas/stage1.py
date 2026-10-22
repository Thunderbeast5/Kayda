"""
Stage 1 Pydantic Schemas: Query Understanding & Legal Decomposition -> LegalQueryObject
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator

from .common import ManualReviewMixin, _sanitize_manual_review


class EntityItem(BaseModel):
    name: str = Field(description="Entity name")
    entity_type: str = Field(default="PARTY", description="Type of entity e.g. ACCUSED, VICTIM")


class FactualAllegation(BaseModel):
    """Atomic, source-grounded factual unit; not a legal conclusion."""
    fact_id: str = Field(description="Stable identifier such as F1")
    description: str
    actor: Optional[str] = None
    affected_party_or_object: Optional[str] = None
    conduct_type: str = Field(description="ACT, OMISSION, RESULT, STATEMENT, or CONDITION")
    chronology: Optional[str] = None
    factual_status: str = Field(default="ALLEGED", description="ALLEGED, ADMITTED, DISPUTED, or UNKNOWN")
    verbatim_quote: Optional[str] = Field(default=None, description="Exact span quote from source narrative")
    start_char: Optional[int] = Field(default=None, description="Character start offset in narrative")
    end_char: Optional[int] = Field(default=None, description="Character end offset in narrative")

    @field_validator("actor", "affected_party_or_object", mode="before")
    @classmethod
    def coerce_to_string(cls, value):
        """Coerce list to comma-separated string for actor and affected_party_or_object fields."""
        if value is None:
            return None
        if isinstance(value, list):
            # Join list items with comma-space
            return ", ".join(str(v) for v in value if v)
        return str(value) if value else None

    @field_validator("conduct_type")
    @classmethod
    def validate_conduct_type(cls, value):
        allowed = {"ACT", "OMISSION", "RESULT", "STATEMENT", "CONDITION"}
        norm = (value or "").strip().upper()
        if norm in allowed:
            return norm
        for candidate in ["OMISSION", "STATEMENT", "CONDITION", "RESULT", "ACT"]:
            if candidate in norm:
                return candidate
        return "ACT"

    @field_validator("factual_status")
    @classmethod
    def validate_factual_status(cls, value):
        allowed = {"ALLEGED", "ADMITTED", "DISPUTED", "UNKNOWN"}
        norm = (value or "").strip().upper()
        if norm in allowed:
            return norm
        for candidate in allowed:
            if candidate in norm:
                return candidate
        return "ALLEGED"


class LegalConceptItem(BaseModel):
    concept_id: str = Field(default="", description="Stable identifier such as LC1")
    concept: str = Field(description="Provisional legal issue/concept grounded in facts")
    description: str = Field(default="", description="Why this issue arises from the alleged facts")
    supporting_fact_ids: List[str] = Field(default_factory=list)
    classification_status: str = Field(default="PROVISIONAL", description="PROVISIONAL, UNCERTAIN, or FACTUAL_ISSUE")
    confidence: float = Field(ge=0.0, le=1.0)


    @field_validator("supporting_fact_ids", mode="before")
    @classmethod
    def _coerce_fact_ids(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v


class SubQueryItem(BaseModel):
    id: str
    query: str
    concept: str = Field(description="Stage 2-compatible concept label")
    concept_id: str = Field(default="", description="Reference to legal_concepts.concept_id")
    tier: str = Field(default="PRIMARY", description="PRIMARY (grounded in alleged facts), SECONDARY (inferable) or CONDITIONAL (needs further facts)")
    fact_ids: List[str] = Field(default_factory=list, description="Source fact IDs supporting this query")
    target_parties: List[str] = Field(default_factory=list)
    role_alleged: Optional[str] = None
    conduct_type: str = Field(default="MULTI_ACT_PATTERN", description="ACT, OMISSION, RESULT, STATEMENT, CONDITION, or MULTI_ACT_PATTERN")
    unresolved_elements: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)

    @field_validator("concept_id", mode="before")
    @classmethod
    def _coerce_concept_id(cls, v):
        """Convert None to empty string for concept_id"""
        if v is None:
            return ""
        return v

    @field_validator("fact_ids", mode="before")
    @classmethod
    def _coerce_fact_ids(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @field_validator("target_parties", mode="before")
    @classmethod
    def _coerce_target_parties(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, (list, tuple)):
            res = []
            for item in v:
                if isinstance(item, dict):
                    val = item.get("name") or item.get("party") or item.get("role") or str(item)
                    res.append(str(val))
                else:
                    res.append(str(item))
            return res
        return v

    @field_validator("role_alleged", mode="before")
    @classmethod
    def _coerce_role_alleged(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        if isinstance(v, dict):
            return str(v.get("role") or v.get("name") or v)
        return str(v)

    @field_validator("conduct_type")
    @classmethod
    def validate_query_conduct_type(cls, value):
        allowed = {"ACT", "OMISSION", "RESULT", "MULTI_ACT_PATTERN", "STATEMENT", "CONDITION"}
        norm = (value or "").strip().upper()
        if norm in allowed:
            return norm
        if ("ACT" in norm and "OMISSION" in norm) or "MULTI" in norm:
            return "MULTI_ACT_PATTERN"
        for candidate in ["STATEMENT", "CONDITION", "OMISSION", "RESULT", "MULTI_ACT_PATTERN", "ACT"]:
            if candidate in norm:
                return candidate
        return "ACT"


class ImportantFacts(BaseModel):
    money: Optional[Union[str, List[str]]] = Field(default=None, description="Financial transaction/dowry/entrustment monetary details")
    location: Optional[Union[str, List[str]]] = Field(default=None, description="Offence or procedural location details")
    dates: Optional[Union[str, List[str]]] = Field(default=None, description="Key dates mentioned in factual narrative")
    weapon: Optional[Union[str, List[str]]] = Field(default=None, description="Weapon or instrument details if mentioned")
    medical_injury: Optional[Union[str, List[str]]] = Field(default=None, description="Medical injury details if mentioned")
    electronic_evidence: Optional[Union[str, List[str]]] = Field(default=None, description="Electronic evidence details if mentioned")
    documents: Optional[Union[str, List[str]]] = Field(default_factory=list, description="Documents mentioned or available")
    witnesses: Optional[Union[str, List[str]]] = Field(default_factory=list, description="Witnesses identified in factual narrative")

    @field_validator("documents", "witnesses", mode="before")
    @classmethod
    def _coerce_to_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return v


class OffenceFamilyItem(BaseModel):
    """A closed-list offence family (lexigraphbe.family_retrieval.OFFENCE_FAMILIES) tagged on quoted facts."""
    family: str = Field(description="Family code from the closed list, e.g. HOMICIDE, FORGERY")
    fact_ids: List[str] = Field(default_factory=list, description="Fact IDs whose quotes support this family")
    tier: str = Field(default="PRIMARY", description="PRIMARY, SECONDARY or CONDITIONAL")
    conduct_phrase: str = Field(default="", description="Short statutory-language description of the conduct; used only to rank sections within the family")
    fault_mode: str = Field(default="UNSTATED", description="Alleged fault element: INTENTIONAL, KNOWING, RASH_OR_NEGLIGENT or UNSTATED")
    unresolved_elements: List[str] = Field(default_factory=list, description="Elements not yet established on the facts")

    @field_validator("family", mode="before")
    @classmethod
    def _upper(cls, v):
        return str(v or "").strip().upper()

    @field_validator("fact_ids", mode="before")
    @classmethod
    def _coerce_ids(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @field_validator("tier", mode="before")
    @classmethod
    def _tier(cls, v):
        t = str(v or "PRIMARY").strip().upper()
        return t if t in {"PRIMARY", "SECONDARY", "CONDITIONAL"} else "PRIMARY"


class LegalQueryObject(ManualReviewMixin):
    schema_version: str = Field(default="2.0", description="Schema version of LegalQueryObject contract")
    case_type: str = Field(default="Anticipatory Bail", description="Case procedural type or requested relief")
    case_facts: str = Field(default="", description="The complete factual narrative of the case (Issue S-3)")
    case_summary: Optional[str] = Field(default=None, description="Concise summary of the factual narrative")
    legal_regime: Optional[str] = Field(default=None, description="Applicable legal regime (e.g. IPC + CrPC or BNS + BNSS)")
    entities: Dict[str, List[Union[str, Dict[str, Any]]]] = Field(
        default_factory=dict,
        description="Categorized entities identified (e.g. victim: ['Wife'], accused: ['Husband', 'Father-in-law'])"
    )
    relationship: List[str] = Field(
        default_factory=list,
        description="Identified relationships between parties (e.g. ['Husband-Wife', 'In-laws'])"
    )
    factual_allegations: List[FactualAllegation] = Field(default_factory=list, description="Atomic factual allegations extracted before legal classification")
    legal_concepts: List[LegalConceptItem] = Field(
        default_factory=list,
        description="List of extracted independent legal concepts with confidence scores"
    )
    sub_queries: List[SubQueryItem] = Field(
        default_factory=list,
        description="List of single-issue legal sub-queries"
    )
    offence_families: List[OffenceFamilyItem] = Field(
        default_factory=list,
        description="Closed-list offence families tagged on quoted facts; drives family-constrained retrieval in Stage 2"
    )
    procedural_events: List[Union[str, Dict[str, Any]]] = Field(
        default_factory=list,
        description="List of procedural events identified (e.g. Marriage, FIR Registered, Anticipatory Bail Application)"
    )
    important_facts: ImportantFacts = Field(default_factory=ImportantFacts)

    @field_validator("entities", mode="before")
    @classmethod
    def _coerce_entities(cls, v):
        if v is None:
            return {}
        if isinstance(v, list):
            coerced: Dict[str, List[Any]] = {}
            for item in v:
                if isinstance(item, dict):
                    etype = str(item.get("entity_type") or item.get("type") or "party").lower()
                    name = item.get("name") or item.get("entity") or item
                    coerced.setdefault(etype, []).append(name)
                elif isinstance(item, str):
                    coerced.setdefault("party", []).append(item)
            return coerced
        if isinstance(v, dict):
            coerced = {}
            for k, val in v.items():
                if val is None:
                    continue
                k_str = str(k)
                if isinstance(val, list):
                    coerced[k_str] = [
                        (item.get("name") or item.get("entity") or item) if isinstance(item, dict) else item
                        for item in val
                    ]
                elif isinstance(val, dict):
                    coerced[k_str] = [val.get("name") or val.get("entity") or val]
                elif isinstance(val, str):
                    coerced[k_str] = [val]
                else:
                    coerced[k_str] = [str(val)]
            return coerced
        return v

    @field_validator("relationship", mode="before")
    @classmethod
    def _coerce_relationship(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, (list, tuple)):
            res = []
            for item in v:
                if isinstance(item, dict):
                    val = item.get("relationship") or item.get("type") or item.get("name") or str(item)
                    res.append(str(val))
                else:
                    res.append(str(item))
            return res
        return v

    legal_regime: Optional[str] = Field(
        default="IPC + CrPC",
        description="Legal regime passed through unchanged from Stage 0 CaseContextObject ('IPC + CrPC')"
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

    @model_validator(mode="after")
    def validate_references(self):
        # Fill stable IDs for backward-compatible model outputs that omit them.
        concept_by_name = {}
        for index, concept in enumerate(self.legal_concepts, start=1):
            if not concept.concept_id:
                concept.concept_id = f"LC{index}"
            concept_by_name[concept.concept.strip().casefold()] = concept
        for sq in self.sub_queries:
            if not sq.concept_id and sq.concept.strip().casefold() in concept_by_name:
                sq.concept_id = concept_by_name[sq.concept.strip().casefold()].concept_id
        fact_ids = {fact.fact_id for fact in self.factual_allegations}
        if len(fact_ids) != len(self.factual_allegations):
            raise ValueError("factual_allegations contains duplicate fact_id values")
        # Broad tiered decomposition produces many ids; repair dangling references
        # instead of failing the whole stage.
        for concept in self.legal_concepts:
            concept.supporting_fact_ids = [f for f in concept.supporting_fact_ids if f in fact_ids] if fact_ids else concept.supporting_fact_ids
        concept_ids = {concept.concept_id for concept in self.legal_concepts}
        for sq in self.sub_queries:
            if fact_ids:
                sq.fact_ids = [f for f in sq.fact_ids if f in fact_ids]
            if sq.concept_id and sq.concept_id not in concept_ids:
                match = concept_by_name.get(sq.concept.strip().casefold())
                if match is None:
                    match = LegalConceptItem(
                        concept_id=sq.concept_id,
                        concept=sq.concept,
                        description=sq.query,
                        supporting_fact_ids=list(sq.fact_ids),
                        confidence=sq.confidence,
                    )
                    self.legal_concepts.append(match)
                    concept_by_name[sq.concept.strip().casefold()] = match
                    concept_ids.add(match.concept_id)
                else:
                    sq.concept_id = match.concept_id
        return self

    def to_downstream_json(self) -> str:
        return self.model_dump_json(indent=2)


class QueryVerificationIssue(BaseModel):
    target: str = Field(description="Target sub-query or concept with error")
    issue: str = Field(description="Description of the issue (e.g. hallucinated concept, statutory section leak, multi-issue query)")
    feedback: str = Field(description="Actionable instructions for Query Understanding Agent correction")


class QueryVerificationResult(BaseModel):
    status: str = Field(description="Verification status: VERIFIED, RETRY, or MANUAL_REVIEW")
    issues: List[QueryVerificationIssue] = Field(default_factory=list, description="List of identified issues if status is RETRY")
    feedback: Optional[str] = Field(default=None, description="Overall verification summary feedback")
    verified_query_object: Optional[LegalQueryObject] = Field(default=None, description="Only populated when status is VERIFIED")
    candidate_query_object: Optional[LegalQueryObject] = Field(default=None, description="Unverified candidate retained for human review; never send to Stage 2")
