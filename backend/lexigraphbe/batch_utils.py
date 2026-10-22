"""
Batching Utilities and Contracts for LexiGraph Backend.
Collapses multiplicative O(N x M) loops into single-call batched LLM requests
for Stage 2 (Chapter/Section Mapping) and Stage 5 (Ingredient Verification).
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from .schemas import SubQueryItem


# ==============================================================================
# STAGE 2 BATCH MAPPING SCHEMAS (Single-Call Sub-Query -> Chapter/Section Mapping)
# ==============================================================================

class SectionMappingCandidate(BaseModel):
    section_number: str = Field(description="Section number string e.g. '498A', '85', 'Section 4'")
    section_title: str = Field(description="Section title or offence description")
    statute: str = Field(default="IPC", description="Statute name e.g. 'IPC', 'BNS', 'Dowry Prohibition Act'")
    candidate_type: str = Field(default="PRIMARY", description="Candidate tier: 'PRIMARY', 'SECONDARY', or 'CONDITIONAL'")
    score: float = Field(default=0.90, description="Confidence score (0.0 to 1.0)")
    score_breakdown: Dict[str, float] = Field(
        default_factory=dict,
        description="Detailed score components: ingredient_match (0.40), classifier_score (0.25), keyword_match (0.20), semantic_similarity (0.15)"
    )
    ingredients_matched: List[str] = Field(default_factory=list, description="Matched statutory ingredients")
    missing_facts: List[str] = Field(
        default_factory=list,
        description="Unproven or missing factual elements required for full statutory satisfaction (used by downstream Prosecutor/Defense/Judge agents)"
    )
    relevance_reasoning: str = Field(default="", description="Explicit reasoning breakdown")
    retrieval_sources: List[str] = Field(
        default_factory=list,
        description="How the candidate was found: 'bm25', 'family_screening:<TIER>', 'graph_link:<section>', 'fact_safety_net'",
    )


class NotTriggeredSectionItem(BaseModel):
    section_number: str = Field(description="Screened section number e.g. '304B', '307'")
    section_title: str = Field(description="Screened section title e.g. 'Dowry Death'")
    statute: str = Field(default="IPC", description="Statute name e.g. 'IPC', 'BNS'")
    not_triggered_reason: str = Field(description="Explicit reason section was not triggered during screening e.g. 'No death alleged in case facts'")
    missing_mandatory_ingredients: List[str] = Field(default_factory=list, description="Mandatory statutory ingredients absent from case facts")

    @property
    def rejection_reason(self) -> str:
        """Backward-compatibility accessor for rejection_reason."""
        return self.not_triggered_reason


# Alias for backward compatibility
RejectedSectionItem = NotTriggeredSectionItem


class SubQueryChapterMapping(BaseModel):
    sub_query_id: str = Field(description="Sub-query identifier (e.g. SQ1, SQ2)")
    sub_query_text: str = Field(description="Sub-query text")
    target_parties: List[str] = Field(default_factory=list, description="Target accused parties for this sub-query")
    facts_extracted: List[str] = Field(default_factory=list, description="Extracted factual elements grounded in text")
    ingredients_matched: List[str] = Field(default_factory=list, description="Matched statutory legal ingredients")
    candidate_chapters: List[str] = Field(default_factory=list, description="List of matched chapter names/numbers")
    primary_candidate_sections: List[SectionMappingCandidate] = Field(default_factory=list, description="Primary high-confidence candidate offences (direct legal nexus)")
    secondary_candidate_sections: List[SectionMappingCandidate] = Field(default_factory=list, description="Secondary/associated candidate offences (ancillary legal nexus)")
    conditional_candidate_sections: List[SectionMappingCandidate] = Field(default_factory=list, description="Conditional candidate offences where applicability depends on unresolved definitional prerequisites")
    not_triggered_sections: List[NotTriggeredSectionItem] = Field(default_factory=list, description="Explicitly screened out sections with non-trigger reasons")
    candidate_sections: List[str] = Field(default_factory=list, description="List of matched section numbers or titles")
    relevance_reasoning: str = Field(default="", description="Brief explanation of legal relevance")

    @property
    def rejected_sections(self) -> List[NotTriggeredSectionItem]:
        """Backward-compatibility accessor for rejected_sections."""
        return self.not_triggered_sections

    def model_post_init(self, __context: Any) -> None:
        """Populates candidate_sections list from primary + secondary + conditional candidates if empty for backwards compatibility."""
        if not self.candidate_sections:
            combined = []
            for c in self.primary_candidate_sections:
                if c.section_number not in combined:
                    combined.append(c.section_number)
            for c in self.secondary_candidate_sections:
                if c.section_number not in combined:
                    combined.append(c.section_number)
            for c in self.conditional_candidate_sections:
                if c.section_number not in combined:
                    combined.append(c.section_number)
            self.candidate_sections = combined


class Stage2BatchedMappingResponse(BaseModel):
    schema_version: str = Field(default="1.0", description="Schema version of Stage 2 mapping response")
    mappings: List[SubQueryChapterMapping] = Field(
        default_factory=list,
        description="Batched mapping list connecting each sub-query to candidate chapters/sections in ONE call"
    )


# ==============================================================================
# STAGE 5 BATCH INGREDIENT VERIFICATION SCHEMAS (Single-Call Shortlist Verification)
# ==============================================================================

class SectionIngredientEvaluation(BaseModel):
    section_identifier: str = Field(description="Section identifier (e.g. IPC 498A, BNS 85)")
    section_title: str = Field(description="Title of section")
    ingredients_present: List[str] = Field(default_factory=list, description="List of statutory ingredients satisfied by case facts")
    ingredients_missing: List[str] = Field(default_factory=list, description="List of statutory ingredients missing from case facts")
    target_parties: List[str] = Field(default_factory=list, description="Target accused parties this section applies to")
    applicability_score: float = Field(description="Applicability score (0.0 to 1.0) based on fact-ingredient alignment")
    bail_relevance_summary: str = Field(description="Summary of relevance for anticipatory bail arguments")


class Stage5BatchedIngredientResponse(BaseModel):
    schema_version: str = Field(default="1.0", description="Schema version of Stage 5 ingredient response")
    evaluations: List[SectionIngredientEvaluation] = Field(
        default_factory=list,
        description="Batched evaluation list assessing all shortlisted sections in ONE call"
    )
