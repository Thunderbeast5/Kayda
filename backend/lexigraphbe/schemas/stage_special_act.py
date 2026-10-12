"""
Special Act Routing and Section Retrieval Pydantic Schemas.

Covers the 8 special acts under the act_router sub-pipeline:
1. dowry_prohibition_act.json
2. indian_institutes_of_information_technology_act.json
3. itpa.json
4. juvenile_justice_act.json
5. pocso_act.json
6. posh_act.json
7. prohibition_of_child_marriage_act.json
8. sc_st_prevention_of_atrocities_act.json

Design principles:
  - Step 1: LLM act routing decision (PROCESS, CANDIDATE, SKIP) over all 8 acts.
  - Step 2: Zero-API-call candidate prefiltering from selected special act JSON(s).
  - Step 3: Single-batch LLM reasoning and verifier auditing of candidate sections.
  - No statutory ingredients evaluation and no Neo4j mapping.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ActRoutingDecisionItem(BaseModel):
    """Decision on whether a single Special Act document applies to the case."""

    document: str = Field(
        description="Name of the Special Act JSON document, e.g. 'pocso_act.json'"
    )
    act_title: Optional[str] = Field(
        default=None, description="Human-readable title of the Special Act"
    )
    decision: str = Field(
        description="Routing decision: 'PROCESS', 'CANDIDATE', or 'SKIP'"
    )
    confidence: float = Field(
        default=1.0, description="Routing decision confidence score [0.0, 1.0]"
    )
    matched_facts: List[str] = Field(
        default_factory=list,
        description="Concrete case facts supporting the routing decision"
    )
    reason: str = Field(
        description="Grounded explanation of why the Act is selected or skipped"
    )


class SpecialActSectionItem(BaseModel):
    """A single retrieved and evaluated section from a selected Special Act."""

    act_document: str = Field(
        description="Source document name, e.g. 'pocso_act.json'"
    )
    act_title: str = Field(
        default="", description="Full title of the Special Act"
    )
    section_number: str = Field(
        description="Section number string, e.g. '3', '4', '8A'"
    )
    heading: str = Field(
        default="", description="Section title or heading"
    )
    chapter_number: Optional[str] = Field(
        default=None, description="Chapter number if present"
    )
    chapter_title: Optional[str] = Field(
        default=None, description="Chapter title if present"
    )
    statutory_text: str = Field(
        default="", description="Statutory text snippet from the Special Act JSON"
    )
    relevance_category: str = Field(
        default="SPECIAL_OFFENCE",
        description="Category: 'SPECIAL_OFFENCE', 'SPECIAL_PROCEDURE', 'PRESUMPTION_BURDEN', 'DEFINITION', 'SPECIAL_BAIL'"
    )
    relevance_reason: str = Field(
        default="", description="Factual connection explaining how this section applies"
    )
    verification_status: str = Field(
        default="VERIFIED", description="Verdict: 'VERIFIED' or 'REJECTED'"
    )
    verification_reason: str = Field(
        default="", description="Auditor's justification for acceptance or rejection"
    )
    confidence_score: float = Field(
        default=1.0, description="Confidence score [0.0, 1.0]"
    )


class SpecialActRetrievalObject(BaseModel):
    """
    Combined output of the Act Router Sub-Pipeline.
    Contains the 8-act routing decisions, the selected acts, and verified sections.
    """

    act_routing: List[ActRoutingDecisionItem] = Field(
        default_factory=list,
        description="Routing decisions for all 8 Special Act documents"
    )
    selected_acts: List[str] = Field(
        default_factory=list,
        description="Document names of Special Acts selected for processing (PROCESS or CANDIDATE)"
    )
    relevant_sections: List[SpecialActSectionItem] = Field(
        default_factory=list,
        description="Verified/accepted sections from the selected Special Acts"
    )
    rejected_sections: List[SpecialActSectionItem] = Field(
        default_factory=list,
        description="Audited & rejected candidate sections with reasons"
    )
    retrieval_notes: List[str] = Field(
        default_factory=list,
        description="Processing notes or warnings"
    )
