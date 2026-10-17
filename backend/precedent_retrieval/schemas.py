"""
Precedent Retrieval Pydantic Schemas: Role-Specific and General Precedent Analysis.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from lexigraphbe.schemas.common import ManualReviewMixin


class MatchedStatuteItem(BaseModel):
    """Details of a matched statute between input case and precedent."""
    judgment_act: str = Field(description="Act in the judgment (e.g., 'IPC', 'CrPC')")
    judgment_section: str = Field(description="Section in the judgment (e.g., '498A', '438')")
    matched_via_act: str = Field(description="Act used for matching (handles equivalents)")
    matched_via_section: str = Field(description="Section used for matching")
    match_type: str = Field(
        default="exact",
        description="Type of match: 'exact' for exact section match, 'parent_match' for parent-subsection match"
    )
    how_used: str = Field(default="", description="How the statute was used in judgment (charged, interpreted, discussed)")
    note: Optional[str] = Field(default=None, description="Additional notes about statute usage")


class PropositionItem(BaseModel):
    """Legal proposition from a precedent case."""
    id: str = Field(description="Proposition identifier (e.g., 'p1', 'p2')")
    text: str = Field(description="Full text of the legal proposition")
    favors: str = Field(
        description="Which side the proposition favors: 'accused', 'prosecution', or 'neutral'"
    )
    speaker: Optional[str] = Field(default=None, description="Who stated this proposition (e.g., 'supreme_court')")
    kind: Optional[str] = Field(default=None, description="Type of proposition: 'ratio', 'obiter', etc.")
    is_holding: Optional[bool] = Field(default=None, description="Whether this is a binding holding")
    binding_level: Optional[str] = Field(default=None, description="Binding level: 'binding', 'persuasive'")


class CaseRetrievalProfile(BaseModel):
    """Structured case retrieval profile constructed prior to precedent search."""
    procedural_stage: str = Field(description="Procedural stage, e.g. 'anticipatory_bail' or 'regular_bail'")
    legal_regime: str = Field(default="IPC + CrPC", description="Legal regime, e.g. 'IPC + CrPC' or 'BNS + BNSS'")
    offences: List[str] = Field(default_factory=list, description="Offence sections, e.g. ['420', '468']")
    fact_patterns: List[str] = Field(default_factory=list, description="Key factual patterns/facets")
    defence_themes: List[str] = Field(default_factory=list, description="Thematic arguments for defense")
    prosecution_themes: List[str] = Field(default_factory=list, description="Thematic arguments for prosecution")


class CompactPrecedentSummary(BaseModel):
    """
    Compact 'why this case matters' summary structure for downstream agents.
    Prevents downstream agents from having to re-read and re-parse giant case objects.
    """
    case_id: str = Field(description="Unique case identifier")
    case_name: str = Field(description="Full case name")
    procedural_match: str = Field(description="HIGH, MODERATE, or LOW")
    factual_match: str = Field(description="HIGH, MODERATE, or LOW")
    statutory_match: List[str] = Field(default_factory=list, description="Matched statute section numbers")
    role: str = Field(description="DEFENSE or PROSECUTION")
    supports_role: bool = Field(description="Whether this case supports this role's position")
    use_for: List[str] = Field(default_factory=list, description="Key arguments to make using this precedent")
    against_role: List[str] = Field(default_factory=list, description="Vulnerabilities or points against this role")
    binding_level: str = Field(default="binding", description="Binding authority level: 'binding' or 'persuasive'")
    relevance_score: float = Field(ge=0.0, le=10.0, description="Calibrated score on 0.0 to 10.0 scale")


class RoleSpecificRelevanceEvaluation(BaseModel):
    """
    LLM evaluation of a precedent's relevance to a specific role (prosecution or defense).
    """
    case_id: str = Field(description="Precedent case identifier")
    case_name: str = Field(description="Precedent case name")
    
    # Relevance assessment
    is_relevant: bool = Field(
        description="Whether this precedent is relevant to this role's argument"
    )
    relevance_type: str = Field(
        description="Type of relevance: 'DIRECTLY_SUPPORTING', 'DIRECTLY_OPPOSING', 'STRONGLY_SUPPORTING', 'STRONGLY_OPPOSING', 'DISTINGUISHABLE', 'BACKGROUND', 'LOW_RELEVANCE'"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in relevance assessment (0.0 to 1.0)"
    )
    
    # Detailed reasoning
    factual_similarity: str = Field(
        description="Assessment of factual similarity between input case and precedent"
    )
    legal_principle_alignment: str = Field(
        description="How the legal principles in the precedent align with this role's position"
    )
    statutory_interpretation_value: str = Field(
        description="Value of the precedent's statutory interpretation for this role"
    )
    procedural_relevance: str = Field(
        description="Relevance of procedural aspects (bail hearing, quashing, etc.)"
    )
    
    # Supporting evidence
    supporting_propositions: List[str] = Field(
        default_factory=list,
        description="List of proposition IDs that support this role's position"
    )
    contradicting_propositions: List[str] = Field(
        default_factory=list,
        description="List of proposition IDs that contradict this role's position"
    )
    
    # Usage recommendation
    usage_recommendation: str = Field(
        description="How this role should use this precedent in argument"
    )
    key_quotes: List[str] = Field(
        default_factory=list,
        description="Key quotes or propositions to cite"
    )
    
    # Distinguishing factors (if not fully applicable)
    distinguishing_factors: List[str] = Field(
        default_factory=list,
        description="Factors that distinguish this precedent from the input case"
    )


class RoleSpecificPrecedentItem(BaseModel):
    """
    A precedent case with role-specific relevance evaluation.
    Contains full case details plus prosecution or defense specific analysis.
    """
    case_id: str = Field(description="Unique case identifier")
    case_name: str = Field(description="Full case name")
    court: str = Field(description="Court name (e.g., 'Supreme Court of India')")
    decided_on: str = Field(description="Decision date (ISO format)")
    citation: Optional[str] = Field(default=None, description="Case citation if available")
    
    procedural_stage: str = Field(
        description="Procedural stage: 'pre_arrest', 'post_arrest_bail', 'quashing', 'appeal', etc."
    )
    disposition: str = Field(description="Final disposition/outcome of the case")
    
    matched_statutes: List[MatchedStatuteItem] = Field(
        description="Statutes that matched between input case and this precedent"
    )
    match_score: float = Field(
        description="Statutory match score from deterministic retrieval"
    )
    
    abstract_facts: str = Field(description="Abstract summary of case facts")
    all_statutes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="All statutes referenced in the judgment"
    )
    propositions: List[PropositionItem] = Field(
        default_factory=list,
        description="Legal propositions extracted from the judgment"
    )
    
    relevance_evaluation: RoleSpecificRelevanceEvaluation = Field(
        description="Role-specific relevance evaluation by LLM"
    )
    
    final_relevance_score: float = Field(
        ge=0.0,
        le=10.0,
        description="Final relevance score combining stage, facts, statutory match, principle, and LLM evaluation (0.0 to 10.0)"
    )

    compact_summary: Optional[CompactPrecedentSummary] = Field(
        default=None,
        description="Compact summary for quick role-agent consumption"
    )


class RoleSpecificPrecedentRetrievalObject(ManualReviewMixin):
    """
    Complete Precedent Retrieval output with separate prosecution and defense precedent lists.
    """
    schema_version: str = Field(
        default="5.0-precedent",
        description="Schema version for precedent retrieval object"
    )
    
    input_case_summary: str = Field(
        description="Brief summary of input case for audit trail"
    )
    input_statutes: List[Dict[str, str]] = Field(
        description="Statutes from Stage 4 that were used for matching"
    )
    case_retrieval_profile: Optional[CaseRetrievalProfile] = Field(
        default=None,
        description="Structured profile used to drive retrieval"
    )
    
    total_judgments_scanned: int = Field(
        description="Total number of judgments scanned"
    )
    candidates_after_statutory_match: int = Field(
        description="Number of candidates after deterministic statutory matching"
    )
    
    prosecution_precedents: List[RoleSpecificPrecedentItem] = Field(
        default_factory=list,
        description="Top precedents relevant to prosecution's position, ranked by relevance"
    )
    defense_precedents: List[RoleSpecificPrecedentItem] = Field(
        default_factory=list,
        description="Top precedents relevant to defense's position, ranked by relevance"
    )
    
    compact_prosecution_summaries: List[CompactPrecedentSummary] = Field(
        default_factory=list,
        description="Compact summaries for prosecution precedents"
    )
    compact_defense_summaries: List[CompactPrecedentSummary] = Field(
        default_factory=list,
        description="Compact summaries for defense precedents"
    )
    
    shared_precedents: List[str] = Field(
        default_factory=list,
        description="Case IDs of precedents that appear in both prosecution and defense lists"
    )
    
    verification_status: str = Field(
        default="VERIFIED",
        description="Verification status: PENDING, VERIFIED, or RETRY"
    )
    
    retrieval_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Metadata about retrieval process (timing, model used, etc.)"
    )


class PrecedentRetrievalIssue(BaseModel):
    """Issue identified during precedent retrieval verification."""
    target: str = Field(description="Target precedent or aspect with issue")
    issue: str = Field(description="Description of the issue")
    feedback: str = Field(description="Actionable feedback for correction")


class PrecedentRetrievalResult(BaseModel):
    """Result of precedent retrieval pipeline execution."""
    status: str = Field(
        description="Execution status: 'VERIFIED' or 'RETRY'"
    )
    issues: List[PrecedentRetrievalIssue] = Field(
        default_factory=list,
        description="Issues identified during retrieval or verification"
    )
    feedback: str = Field(
        default="Precedent retrieval complete.",
        description="Overall feedback message"
    )
    verified_precedent_object: Optional[RoleSpecificPrecedentRetrievalObject] = Field(
        default=None,
        description="Final verified precedent retrieval object"
    )


# Legacy schemas for backward compatibility
class PrecedentItem(BaseModel):
    case_name: str = Field(description="Name of precedent case")
    court: str = Field(description="Court issuing judgment")
    citation: str = Field(description="Official legal citation")
    facts: str = Field(description="Factual summary of precedent case")
    verified_offences: List[str] = Field(default_factory=list, description="Offences cited or evaluated")
    bail_outcome: str = Field(description="Bail outcome granted in precedent")
    ratio_decidendi: str = Field(description="Binding ratio decidendi / legal principle established by court")
    similarity_score: float = Field(description="Relevance similarity score (0.0 to 1.0)")


class PrecedentRetrievalObject(ManualReviewMixin):
    schema_version: str = Field(default="1.0", description="Schema version of PrecedentRetrievalObject contract")
    precedents: List[PrecedentItem] = Field(default_factory=list, description="List of retrieved judicial precedents")
    verification_status: str = Field(default="PENDING", description="Verification status: PENDING, VERIFIED, or RETRY")

    def to_downstream_json(self) -> str:
        return self.model_dump_json(indent=2)


class PrecedentVerificationIssue(BaseModel):
    target: str = Field(description="Target precedent case name or property with audit issue")
    issue: str = Field(description="Detailed description of precedent retrieval verification issue")
    feedback: str = Field(description="Actionable instructions for Precedent Retrieval Agent correction")


class PrecedentVerificationResult(BaseModel):
    status: str = Field(description="Status: 'VERIFIED' or 'RETRY'")
    issues: List[PrecedentVerificationIssue] = Field(default_factory=list, description="List of audit issues identified")
    feedback: str = Field(default="Precedent verification audit complete.", description="Overall summary feedback")
    verified_precedent_object: Optional[PrecedentRetrievalObject] = Field(default=None, description="Verified PrecedentRetrievalObject")
