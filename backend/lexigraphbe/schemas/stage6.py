"""
Stage 6 Pydantic Schemas: Judicial Precedent Retrieval Engine -> PrecedentRetrievalObject
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from .common import ManualReviewMixin, _sanitize_manual_review


class PrecedentItem(BaseModel):
    case_name: str = Field(description="Name of precedent case (e.g. 'Arnesh Kumar v. State of Bihar')")
    court: str = Field(description="Court issuing judgment (e.g. 'Supreme Court' or 'High Court of Delhi')")
    citation: str = Field(description="Official legal citation (e.g. '(2014) 8 SCC 273')")
    facts: str = Field(description="Factual summary of precedent case")
    verified_offences: List[str] = Field(default_factory=list, description="Offences cited or evaluated in precedent (e.g. ['498A IPC', '506 IPC'])")
    bail_outcome: str = Field(description="Bail outcome granted in precedent (e.g. 'Anticipatory Bail Principles Applied', 'Conditional Bail Modified')")
    ratio_decidendi: str = Field(description="Binding ratio decidendi / legal principle established by court")
    similarity_score: float = Field(description="Relevance similarity score (0.0 to 1.0) compared to current case")


class PrecedentRetrievalObject(ManualReviewMixin):
    schema_version: str = Field(default="1.0", description="Schema version of PrecedentRetrievalObject contract")
    precedents: List[PrecedentItem] = Field(default_factory=list, description="List of retrieved judicial precedents ranked by similarity score descending")
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
