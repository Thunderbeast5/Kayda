"""
Stage 5 Precedent Retrieval Pydantic Schemas: Role-Specific Precedent Analysis

This replaces the old Stage 5 (Bail Reasoning) and Stage 6 (Precedent Retrieval)
with a unified precedent retrieval system that produces separate prosecution and
defense precedent lists based on role-specific relevance evaluation.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .common import ManualReviewMixin


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
        description="Type of relevance: 'strongly_supporting', 'supporting', 'distinguishable', 'contradictory', 'not_relevant'"
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
    # Case identification
    case_id: str = Field(description="Unique case identifier")
    case_name: str = Field(description="Full case name")
    court: str = Field(description="Court name (e.g., 'Supreme Court of India')")
    decided_on: str = Field(description="Decision date (ISO format)")
    citation: Optional[str] = Field(default=None, description="Case citation if available")
    
    # Case metadata
    procedural_stage: str = Field(
        description="Procedural stage: 'pre_arrest', 'post_arrest_bail', 'quashing', 'appeal', etc."
    )
    disposition: str = Field(description="Final disposition/outcome of the case")
    
    # Statutory matching (from deterministic retrieval)
    matched_statutes: List[MatchedStatuteItem] = Field(
        description="Statutes that matched between input case and this precedent"
    )
    match_score: float = Field(
        description="Statutory match score from deterministic retrieval"
    )
    
    # Case content
    abstract_facts: str = Field(description="Abstract summary of case facts")
    all_statutes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="All statutes referenced in the judgment"
    )
    propositions: List[PropositionItem] = Field(
        default_factory=list,
        description="Legal propositions extracted from the judgment"
    )
    
    # Role-specific evaluation (from LLM)
    relevance_evaluation: RoleSpecificRelevanceEvaluation = Field(
        description="Role-specific relevance evaluation by LLM"
    )
    
    # Ranking
    final_relevance_score: float = Field(
        ge=0.0,
        description="Final relevance score combining statutory match and LLM evaluation"
    )


class RoleSpecificPrecedentRetrievalObject(ManualReviewMixin):
    """
    Complete Stage 5 output with separate prosecution and defense precedent lists.
    
    Each role gets its own ranked list of precedents based on:
    1. Deterministic statutory matching (OR logic)
    2. LLM-based relevance evaluation specific to that role's argument position
    """
    schema_version: str = Field(
        default="5.0-precedent",
        description="Schema version for precedent retrieval object"
    )
    
    # Input context
    input_case_summary: str = Field(
        description="Brief summary of input case for audit trail"
    )
    input_statutes: List[Dict[str, str]] = Field(
        description="Statutes from Stage 4 that were used for matching"
    )
    
    # Retrieval statistics
    total_judgments_scanned: int = Field(
        description="Total number of judgments scanned"
    )
    candidates_after_statutory_match: int = Field(
        description="Number of candidates after deterministic statutory matching"
    )
    
    # Role-specific precedent lists
    prosecution_precedents: List[RoleSpecificPrecedentItem] = Field(
        default_factory=list,
        description="Precedents relevant to prosecution's position, ranked by relevance"
    )
    defense_precedents: List[RoleSpecificPrecedentItem] = Field(
        default_factory=list,
        description="Precedents relevant to defense's position, ranked by relevance"
    )
    
    # Shared precedents (relevant to both sides)
    shared_precedents: List[str] = Field(
        default_factory=list,
        description="Case IDs of precedents that appear in both prosecution and defense lists"
    )
    
    # Verification status
    verification_status: str = Field(
        default="VERIFIED",
        description="Verification status: PENDING, VERIFIED, or RETRY"
    )
    
    # Audit trail
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


# Export schemas
__all__ = [
    "MatchedStatuteItem",
    "PropositionItem",
    "RoleSpecificRelevanceEvaluation",
    "RoleSpecificPrecedentItem",
    "RoleSpecificPrecedentRetrievalObject",
    "PrecedentRetrievalIssue",
    "PrecedentRetrievalResult",
]
