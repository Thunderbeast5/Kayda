"""
BSA Section Retrieval and Verification Pydantic Schemas.

BSARetrievalObject — evidence law sections from the Bharatiya Sakshya Adhiniyam, 2023
identified and verified as relevant to the current case facts.

Key design notes:
  - BSA sections have NO criminal ingredients (they are evidentiary rules, not offences).
  - LLM evaluates evidentiary relevance (proof of signatures, primary vs secondary evidence,
    electronic records, expert opinion, burden of proof).
  - BSAVerifierAgent audits and accepts/rejects candidate sections based on case facts.
  - Each BSA section carries its IEA equivalent (legacy reference) and chapter metadata.
  - Sourced directly from bsa.json with Neo4j REPLACES mapping to IEA.
  - IPC→BNS equivalent is resolved via Neo4j REPLACED_BY mapping.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BSASectionItem(BaseModel):
    """A single BSA section evaluated for relevance to the case."""

    section_number: str = Field(
        description="BSA section number string, e.g. '23', '39', '63', '72'"
    )
    heading: str = Field(
        default="", description="BSA section heading / title"
    )
    chapter_number: str = Field(
        default="", description="BSA chapter number (Roman numeral, e.g. 'V')"
    )
    chapter_title: str = Field(
        default="", description="BSA chapter title"
    )
    relevance_category: str = Field(
        default="DOCUMENTS",
        description=(
            "High-level relevance category: "
            "'HANDWRITING_SIGNATURE', 'PRIMARY_SECONDARY_EVIDENCE', "
            "'ELECTRONIC_RECORDS', 'EXPERT_OPINION', 'BURDEN_OF_PROOF', "
            "'ADMISSIONS_CONFESSIONS', 'DOCUMENTS_GENERAL', 'WITNESS'"
        ),
    )
    relevance_reason: str = Field(
        default="",
        description="Explanation of how this section applies to the live evidentiary disputes in the case",
    )
    replaces_IEA: Optional[str] = Field(
        default=None,
        description=(
            "Equivalent Indian Evidence Act (IEA) section(s) that this BSA section replaces, "
            "e.g. '65B', '45, 45A', '73'. None if no direct IEA equivalent is mapped in Neo4j."
        ),
    )
    statutory_text: str = Field(
        default="",
        description="Statutory text of the BSA section (truncated for prompt context)",
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


class BSAVerificationIssue(BaseModel):
    """An issue identified during BSA verification."""

    section_number: str = Field(description="Target BSA section number")
    issue: str = Field(description="Description of the evidentiary issue or mismatch")
    verdict: str = Field(description="'ACCEPT' or 'REJECT'")
    reason: str = Field(description="Detailed factual or statutory justification")


class BSARetrievalObject(BaseModel):
    """
    Output of the BSA Retrieval & Verification Pipeline (Stage 3b).

    Contains all verified BSA evidence-law sections alongside their IEA equivalents,
    explicitly rejected candidate sections with reasons, and the Stage 3 IPC → BNS mapping.
    """

    schema_version: str = Field(default="3b.1")
    relevant_sections: List[BSASectionItem] = Field(
        default_factory=list,
        description="BSA sections verified and accepted as relevant to the live evidentiary disputes",
    )
    rejected_sections: List[BSASectionItem] = Field(
        default_factory=list,
        description="Candidate BSA sections evaluated and rejected as inapplicable, tangential, or noisy",
    )
    ipc_to_bns_map: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "IPC → BNS section equivalents for sections identified in Stage 3, "
            "sourced from Neo4j REPLACED_BY edges. key = IPC section, value = BNS section."
        ),
    )
    retrieval_notes: List[str] = Field(
        default_factory=list,
        description="Audit notes / warnings from the BSA retrieval and verification process",
    )
    legal_regime: Optional[str] = Field(
        default=None,
        description="Legal regime passed through from Stage 1 ('IPC + CrPC' or 'BNS + BNSS')",
    )

    def to_downstream_json(self) -> str:
        return self.model_dump_json(indent=2)
