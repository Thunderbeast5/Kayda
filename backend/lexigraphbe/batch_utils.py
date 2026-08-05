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

class SubQueryChapterMapping(BaseModel):
    sub_query_id: str = Field(description="Sub-query identifier (e.g. SQ1, SQ2)")
    sub_query_text: str = Field(description="Sub-query text")
    target_parties: List[str] = Field(default_factory=list, description="Target accused parties for this sub-query")
    candidate_chapters: List[str] = Field(default_factory=list, description="List of matched chapter names/numbers")
    candidate_sections: List[str] = Field(default_factory=list, description="List of matched section numbers or titles")
    relevance_reasoning: str = Field(description="Brief explanation of legal relevance")


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
