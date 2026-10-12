"""
BNSS Section Retrieval and Verification Pydantic Schemas.

BNSSRetrievalObject — procedural criminal law sections from the Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)
identified and verified as relevant to the current case facts (bail, arrest, custody, remand, investigation).

Key design notes:
  - BNSS sections have NO criminal ingredients (they are procedural rules, not offences).
  - LLM evaluates procedural relevance (anticipatory bail, arrest safeguards, notice of appearance,
    custody/remand necessity, default bail, bail conditions).
  - BNSSVerifierAgent audits and accepts/rejects candidate sections based on case facts.
  - Sourced directly from bnss_bail_core.json (primary) and bnss.json (fallback).
  - Each BNSS section carries its CrPC equivalent mapped via Neo4j REPLACES edge.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BNSSSectionItem(BaseModel):
    """A single BNSS section evaluated for procedural relevance to the case."""

    section_number: str = Field(
        description="BNSS section number string, e.g. '35', '187', '479', '480', '482'"
    )
    heading: str = Field(
        default="", description="BNSS section heading / title"
    )
    chapter_number: str = Field(
        default="", description="BNSS chapter number (Roman numeral, e.g. 'XXXV')"
    )
    chapter_title: str = Field(
        default="", description="BNSS chapter title"
    )
    relevance_category: str = Field(
        default="BAIL",
        description=(
            "Procedural category: "
            "'ANTICIPATORY_BAIL', 'ARREST_PROCEDURE', 'NOTICE_OF_APPEARANCE', "
            "'CUSTODY_REMAND', 'REGULAR_BAIL', 'DEFAULT_BAIL', 'BAIL_CONDITIONS', "
            "'INVESTIGATION', 'GENERAL_PROCEDURE'"
        ),
    )
    relevance_reason: str = Field(
        default="",
        description="Explanation of how this section applies to the live procedural controversy in the case",
    )
    replaces_CrPC: Optional[str] = Field(
        default=None,
        description=(
            "Equivalent Code of Criminal Procedure (CrPC) section(s) that this BNSS section replaces, "
            "e.g. '438', '41, 41A', '167'. None if no CrPC equivalent mapped."
        ),
    )
    statutory_text: str = Field(
        default="",
        description="Statutory text of the BNSS section (truncated for prompt context)",
    )
    verification_status: str = Field(
        default="VERIFIED",
        description="Verification verdict: 'VERIFIED' or 'REJECTED'",
    )
    verification_reason: str = Field(
        default="",
        description="Audit verdict reason explaining why the section was accepted or rejected",
    )
    confidence_score: float = Field(
        default=1.0,
        description="Confidence score in the range [0.0, 1.0]",
    )


class BNSSVerificationIssue(BaseModel):
    """An issue identified during BNSS procedural verification."""

    section_number: str = Field(description="Target BNSS section number")
    issue: str = Field(description="Description of procedural mismatch")
    verdict: str = Field(description="'ACCEPT' or 'REJECT'")
    reason: str = Field(description="Detailed factual or statutory justification")


class BNSSRetrievalObject(BaseModel):
    """
    Output of the BNSS Retrieval & Verification Pipeline (Stage 3c).

    Contains all verified BNSS procedural sections alongside their CrPC equivalents,
    explicitly rejected candidate sections with reasons, and the BNSS → CrPC mapping.
    """

    schema_version: str = Field(default="3c.0")
    relevant_sections: List[BNSSSectionItem] = Field(
        default_factory=list,
        description="BNSS sections verified and accepted as relevant to the live procedural issues",
    )
    rejected_sections: List[BNSSSectionItem] = Field(
        default_factory=list,
        description="Candidate BNSS sections evaluated and rejected as inapplicable, tangential, or noisy",
    )
    bnss_to_crpc_map: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "BNSS → CrPC section equivalents, sourced from Neo4j REPLACES edges. "
            "key = BNSS section, value = CrPC section."
        ),
    )
    retrieval_notes: List[str] = Field(
        default_factory=list,
        description="Audit notes / warnings from the BNSS retrieval and verification process",
    )
    legal_regime: Optional[str] = Field(
        default=None,
        description="Legal regime passed through from Stage 1 ('IPC + CrPC' or 'BNS + BNSS')",
    )

    def to_downstream_json(self) -> str:
        return self.model_dump_json(indent=2)
