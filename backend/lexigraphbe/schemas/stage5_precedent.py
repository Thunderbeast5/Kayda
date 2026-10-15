"""
Stage 5 Precedent Retrieval Pydantic Schemas: Role-Specific Precedent Analysis

Optimized schema with:
1. Deduplicated cases dictionary keyed by case_id (stored once).
2. Prosecution and defense lists holding only {case_id, role_fit, score}.
3. Five overlapping prose fields replaced with a single 1-2 sentence analysis field,
   plus structured use_for, against, and distinguish lists.
4. Statutes limited strictly to those overlapping with the input case.
5. Compact view generation for Stage 8 / downstream argument stages.
"""

from pathlib import Path
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

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
    how_used: str = Field(default="", description="How the statute was used in judgment (procedure, charged, interpreted)")
    dual_citation: Optional[str] = Field(default=None, description="Dual citation e.g. 'IPC 420 / BNS 318(4)'")
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


class PrecedentRoleRef(BaseModel):
    """
    Lightweight reference for a role list holding only case_id, role_fit, and score.
    Prevents repeating full case records across prosecution and defense lists.
    Explicitly tags whether the authority supports the role or is an adverse authority to rebut.
    """
    case_id: str = Field(description="Unique precedent case identifier")
    role_fit: str = Field(description="Relevance type: DIRECTLY_SUPPORTING, STRONGLY_SUPPORTING, DISTINGUISHABLE, etc.")
    score: float = Field(ge=0.0, le=10.0, description="Calibrated relevance score (0.0 to 10.0 scale)")
    case_name: Optional[str] = Field(default=None, description="Full case title for readable display")
    supports_role: bool = Field(default=True, description="True if this authority supports the role's position")
    is_adverse: bool = Field(default=False, description="True if authority cuts against role and must be distinguished/rebutted")
    distinguishing_note: Optional[str] = Field(default=None, description="Key distinguishing note if adverse")



class PrecedentRoleEvaluation(BaseModel):
    """
    Concise role evaluation. Replaces 5 overlapping prose fields with:
    - analysis: at most 2 sentences explaining relevance and tactical application
    - structured use_for, against, and distinguish lists
    """
    role_fit: str = Field(description="Relevance classification")
    score: float = Field(ge=0.0, le=10.0, description="Calibrated relevance score")
    analysis: str = Field(
        description="At most 2 sentences explaining relevance and tactical application for this role"
    )
    use_for: List[str] = Field(default_factory=list, description="Key arguments to make using this precedent")
    against: List[str] = Field(default_factory=list, description="Vulnerabilities or points against this role")
    distinguish: List[str] = Field(default_factory=list, description="Material factors distinguishing this precedent")
    supporting_propositions: List[str] = Field(default_factory=list, description="Proposition IDs supporting role")
    contradicting_propositions: List[str] = Field(default_factory=list, description="Proposition IDs contradicting role")


class PrecedentCaseDetail(BaseModel):
    """
    Precedent case details stored ONCE, keyed by case_id.
    Includes ONLY statutes that overlap with the input case (no CrPC 82/83 / irrelevant statutes).
    """
    case_id: str = Field(description="Unique case identifier")
    case_name: str = Field(description="Full case name")
    court: str = Field(description="Court name")
    decided_on: str = Field(description="Decision date (ISO format)")
    citation: Optional[str] = Field(default=None, description="Case citation if available")
    procedural_stage: str = Field(description="Procedural stage")
    disposition: str = Field(description="Final disposition/outcome")
    procedural_match: Optional[str] = Field(default="MODERATE", description="HIGH, MODERATE, or LOW")
    factual_match: Optional[str] = Field(default="MODERATE", description="HIGH, MODERATE, or LOW")
    matched_statutes: List[MatchedStatuteItem] = Field(
        default_factory=list,
        description="ONLY statutes overlapping with the input case"
    )
    match_score: float = Field(default=0.0, description="Statutory match score")
    abstract_facts: str = Field(description="Abstract summary of case facts")
    propositions: List[PropositionItem] = Field(
        default_factory=list,
        description="Legal propositions extracted from judgment"
    )
    evaluations: Dict[str, PrecedentRoleEvaluation] = Field(
        default_factory=dict,
        description="Role-specific evaluations keyed by 'prosecution' or 'defense'"
    )


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
    Replaces 5 overlapping prose fields with 1 concise analysis field (<= 2 sentences)
    plus structured use_for, against, and distinguish lists.
    """
    case_id: str = Field(description="Precedent case identifier")
    case_name: str = Field(description="Precedent case name")
    is_relevant: bool = Field(default=True, description="Whether this precedent is relevant")
    relevance_type: str = Field(
        description="Type of relevance: 'DIRECTLY_SUPPORTING', 'DIRECTLY_OPPOSING', 'STRONGLY_SUPPORTING', 'STRONGLY_OPPOSING', 'DISTINGUISHABLE', 'BACKGROUND', 'LOW_RELEVANCE'"
    )
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence in assessment (0.0 to 1.0)")
    
    # Concise analysis field (at most 2 sentences) replacing the 5 prose fields
    analysis: str = Field(
        default="",
        description="At most 2 sentences explaining relevance and tactical application for this role"
    )
    
    # Structured lists
    use_for: List[str] = Field(default_factory=list, description="Key arguments to make using this precedent")
    against: List[str] = Field(default_factory=list, description="Vulnerabilities or points against this role")
    distinguish: List[str] = Field(default_factory=list, description="Factors distinguishing this precedent")
    
    supporting_propositions: List[str] = Field(default_factory=list, description="Supporting proposition IDs")
    contradicting_propositions: List[str] = Field(default_factory=list, description="Contradicting proposition IDs")

    # Backward compatibility fields (optional, auto-synced)
    factual_similarity: Optional[str] = None
    legal_principle_alignment: Optional[str] = None
    statutory_interpretation_value: Optional[str] = None
    procedural_relevance: Optional[str] = None
    usage_recommendation: Optional[str] = None
    key_propositions: Optional[List[str]] = None
    key_quotes: Optional[List[str]] = None
    distinguishing_factors: Optional[List[str]] = None
    against_role: Optional[List[str]] = None

    @model_validator(mode="after")
    def sync_backward_compatibility_fields(self) -> "RoleSpecificRelevanceEvaluation":
        # If analysis was given, populate legacy prose fields to preserve backward compatibility
        text = self.analysis or self.factual_similarity or ""
        if not self.analysis and self.factual_similarity:
            self.analysis = self.factual_similarity
        if not self.factual_similarity:
            self.factual_similarity = text
        if not self.legal_principle_alignment:
            self.legal_principle_alignment = text
        if not self.statutory_interpretation_value:
            self.statutory_interpretation_value = text
        if not self.procedural_relevance:
            self.procedural_relevance = text
        if not self.usage_recommendation:
            self.usage_recommendation = "; ".join(self.use_for) if self.use_for else text
        if not self.distinguishing_factors:
            self.distinguishing_factors = self.distinguish
        if not self.distinguish and self.distinguishing_factors:
            self.distinguish = self.distinguishing_factors
        if not self.against_role:
            self.against_role = self.against
        if not self.against and self.against_role:
            self.against = self.against_role
        if not self.key_propositions and self.key_quotes:
            self.key_propositions = self.key_quotes
        if not self.key_quotes and self.key_propositions:
            self.key_quotes = self.key_propositions
        return self


class RoleSpecificPrecedentItem(BaseModel):
    """
    A precedent case with role-specific relevance evaluation.
    Contains case details plus role-specific analysis.
    """
    case_id: str = Field(description="Unique case identifier")
    case_name: str = Field(description="Full case name")
    court: str = Field(description="Court name")
    decided_on: str = Field(description="Decision date (ISO format)")
    citation: Optional[str] = Field(default=None, description="Case citation if available")
    procedural_stage: str = Field(description="Procedural stage")
    disposition: str = Field(description="Final disposition/outcome")
    
    # Statutory matching (only overlapping statutes)
    matched_statutes: List[MatchedStatuteItem] = Field(
        description="Statutes that matched between input case and this precedent"
    )
    match_score: float = Field(description="Statutory match score from deterministic retrieval")
    
    # Case content
    abstract_facts: str = Field(description="Abstract summary of case facts")
    all_statutes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Statutes list (now filtered to avoid bloat)"
    )
    propositions: List[PropositionItem] = Field(
        default_factory=list,
        description="Legal propositions extracted from judgment"
    )
    
    # Role-specific evaluation
    relevance_evaluation: RoleSpecificRelevanceEvaluation = Field(
        description="Role-specific relevance evaluation by LLM"
    )
    final_relevance_score: float = Field(
        ge=0.0,
        le=10.0,
        description="Final relevance score (0.0 to 10.0)"
    )
    compact_summary: Optional[CompactPrecedentSummary] = Field(
        default=None,
        description="Compact summary for quick role-agent consumption"
    )


class RoleSpecificPrecedentRetrievalObject(ManualReviewMixin):
    """
    Complete Stage 5 output with deduplicated cases dictionary and
    separate prosecution and defense precedent lists.
    
    1. Deduplicated cases: stored ONCE in 'cases' dict keyed by case_id.
    2. 'prosecution' and 'defense' lists hold only {case_id, role_fit, score}.
    3. Overlapping statutes only; 5 prose fields replaced with 2-sentence analysis.
    4. Compact view provided for Stage 8 / downstream argument stage.
    """
    schema_version: str = Field(
        default="5.0-compact",
        description="Schema version for precedent retrieval object"
    )
    
    # Input context
    input_case_summary: str = Field(description="Brief summary of input case")
    input_statutes: List[Dict[str, str]] = Field(description="Statutes used for matching")
    case_retrieval_profile: Optional[CaseRetrievalProfile] = Field(
        default=None,
        description="Structured profile used to drive retrieval"
    )
    
    # Retrieval statistics
    total_judgments_scanned: int = Field(default=0, description="Total judgments scanned")
    candidates_after_statutory_match: int = Field(default=0, description="Candidates after matching")
    
    # Deduplicated cases dictionary keyed by ID (stored ONCE)
    cases: Dict[str, PrecedentCaseDetail] = Field(
        default_factory=dict,
        description="Precedent cases keyed by ID, stored once"
    )
    
    # Lightweight role reference lists: hold only {case_id, role_fit, score}
    prosecution: List[PrecedentRoleRef] = Field(
        default_factory=list,
        description="Prosecution precedent references holding {case_id, role_fit, score}"
    )
    defense: List[PrecedentRoleRef] = Field(
        default_factory=list,
        description="Defense precedent references holding {case_id, role_fit, score}"
    )

    # Role-aware partitioned lists: supporting authorities vs adverse authorities to rebut
    prosecution_supporting: List[PrecedentRoleRef] = Field(
        default_factory=list,
        description="Authorities supporting prosecution position"
    )
    prosecution_adverse: List[PrecedentRoleRef] = Field(
        default_factory=list,
        description="Adverse authorities prosecution must distinguish or rebut"
    )
    defense_supporting: List[PrecedentRoleRef] = Field(
        default_factory=list,
        description="Authorities supporting defense position"
    )
    defense_adverse: List[PrecedentRoleRef] = Field(
        default_factory=list,
        description="Adverse authorities defense must distinguish or rebut"
    )
    
    # Shared precedents
    shared_precedents: List[str] = Field(
        default_factory=list,
        description="Case IDs of precedents appearing in both prosecution and defense lists"
    )
    
    # Verification status
    verification_status: str = Field(default="VERIFIED", description="Verification status")
    retrieval_metadata: Optional[Dict[str, Any]] = Field(default=None, description="Metadata")
    
    # Legacy lists maintained for backward compatibility with older callers
    prosecution_precedents: List[RoleSpecificPrecedentItem] = Field(
        default_factory=list,
        description="Legacy full list for backward compatibility"
    )
    defense_precedents: List[RoleSpecificPrecedentItem] = Field(
        default_factory=list,
        description="Legacy full list for backward compatibility"
    )
    compact_prosecution_summaries: List[CompactPrecedentSummary] = Field(
        default_factory=list,
        description="Legacy compact summaries"
    )
    compact_defense_summaries: List[CompactPrecedentSummary] = Field(
        default_factory=list,
        description="Legacy compact summaries"
    )

    def to_compact_dict(self) -> Dict[str, Any]:
        """
        Returns the compact view for Stage 8 and downstream argument stages.
        Deduplicated cases dictionary keyed by ID, with prosecution and defense holding only {case_id, role_fit, score}.
        Statutes contain only overlap with input case, prose fields replaced with 2-sentence analysis.
        Separates supporting authorities from adverse authorities to rebut for clean legal advocacy.
        """
        return {
            "schema_version": "5.0-compact",
            "input_case_summary": self.input_case_summary,
            "input_statutes": self.input_statutes,
            "total_judgments_scanned": self.total_judgments_scanned,
            "candidates_after_statutory_match": self.candidates_after_statutory_match,
            "prosecution": [p.model_dump() for p in self.prosecution],
            "defense": [d.model_dump() for d in self.defense],
            "prosecution_supporting": [p.model_dump() for p in self.prosecution_supporting],
            "prosecution_adverse": [p.model_dump() for p in self.prosecution_adverse],
            "defense_supporting": [d.model_dump() for d in self.defense_supporting],
            "defense_adverse": [d.model_dump() for d in self.defense_adverse],
            "shared_precedents": self.shared_precedents,
            "cases": {cid: case.model_dump(exclude_none=True) for cid, case in self.cases.items()},
            "verification_status": self.verification_status,
            # Compact aliases for downstream consumers
            "prosecution_precedents": [p.model_dump() for p in self.prosecution],
            "defense_precedents": [d.model_dump() for d in self.defense],
        }


    def save_debug_file(self, filepath: Path) -> None:
        """Save complete evaluation with full audit detail to a debug file."""
        try:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.model_dump(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[RoleSpecificPrecedentRetrievalObject] Error saving debug file to {filepath}: {e}")


class PrecedentRetrievalIssue(BaseModel):
    """Issue identified during precedent retrieval verification."""
    target: str = Field(description="Target precedent or aspect with issue")
    issue: str = Field(description="Description of the issue")
    feedback: str = Field(description="Actionable feedback for correction")


class PrecedentRetrievalResult(BaseModel):
    """Result of precedent retrieval pipeline execution."""
    status: str = Field(description="Execution status: 'VERIFIED' or 'RETRY'")
    issues: List[PrecedentRetrievalIssue] = Field(default_factory=list, description="Issues identified")
    feedback: str = Field(default="Precedent retrieval complete.", description="Overall feedback message")
    verified_precedent_object: Optional[RoleSpecificPrecedentRetrievalObject] = Field(
        default=None,
        description="Final verified precedent retrieval object"
    )


# Export schemas
__all__ = [
    "MatchedStatuteItem",
    "PropositionItem",
    "CaseRetrievalProfile",
    "PrecedentRoleRef",
    "PrecedentRoleEvaluation",
    "PrecedentCaseDetail",
    "CompactPrecedentSummary",
    "RoleSpecificRelevanceEvaluation",
    "RoleSpecificPrecedentItem",
    "RoleSpecificPrecedentRetrievalObject",
    "PrecedentRetrievalIssue",
    "PrecedentRetrievalResult",
]
