"""
Stage 3 Pydantic Schemas: Statutory Verification & Normalization -> ChapterIdentificationObject (Schema v3.0)
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from .common import ManualReviewMixin, _sanitize_manual_review


class ChapterCandidateItem(BaseModel):
    concept: str = Field(description="Legal concept from Stage 1 (e.g. 'Dowry Demand')")
    chapter_number: str = Field(description="Chapter number (e.g. 'XXA', 'XXII')")
    chapter_name: str = Field(description="Chapter name (e.g. 'Of Cruelty by Husband or Relatives')")
    confidence: float = Field(description="Confidence score for chapter relevance (0.0 to 1.0)")


class SectionCandidateItem(BaseModel):
    concept: str = Field(description="Matching legal concept from Stage 1")
    section_number: str = Field(description="Section number (e.g. '498A', '506')")
    section_title: str = Field(description="Section title (e.g. 'Cruelty by Husband or Relatives')")
    confidence: float = Field(description="Confidence score for section candidate (0.0 to 1.0)")


class PunishmentSpec(BaseModel):
    minimum: Optional[str] = Field(default=None, description="Minimum imprisonment term or null")
    maximum: Optional[str] = Field(default=None, description="Maximum imprisonment term")
    fine: bool = Field(default=True, description="Whether fine is applicable")


class VerifiedOffenceItem(BaseModel):
    section_number: str = Field(description="Normalized section number string e.g. '498A', 'Section 4'")
    statute: str = Field(default="IPC", description="Primary statute e.g. 'IPC', 'Dowry Prohibition Act'")
    ipc_equivalent: Optional[str] = Field(default=None, description="IPC equivalent section number e.g. '498A'")
    bns_equivalent: Optional[str] = Field(default=None, description="Deprecated / always null in IPC-only pipeline")
    title: str = Field(description="Canonical statutory section title")
    chapter_number: str = Field(default="XXA", description="Statutory chapter number")
    chapter_title: str = Field(default="Of Cruelty by Husband or Relatives of Husband", description="Statutory chapter name")
    punishment: PunishmentSpec = Field(default_factory=PunishmentSpec, description="Verified punishment specifications")
    classification: str = Field(default="PRIMARY", description="Candidate tier preserved from Stage 2: 'PRIMARY', 'SECONDARY', or 'CONDITIONAL'")
    cognizable: bool = Field(default=True, description="Whether offence is cognizable")
    bailable: bool = Field(default=False, description="Whether offence is bailable")
    verification_status: str = Field(default="VERIFIED", description="Verification status e.g. 'VERIFIED' or 'FLAGGED'")
    verification_notes: List[str] = Field(default_factory=list, description="Verification notes / audit logs")


class ChapterIdentificationObject(ManualReviewMixin):
    schema_version: str = Field(default="3.0", description="Schema version of ChapterIdentificationObject contract")
    verified_offences: List[VerifiedOffenceItem] = Field(
        default_factory=list,
        description="List of verified and normalized statutory offences"
    )
    chapter_candidates: List[ChapterCandidateItem] = Field(
        default_factory=list,
        description="List of shortlisted candidate chapters (maintained for backward compatibility)"
    )
    section_candidates: List[SectionCandidateItem] = Field(
        default_factory=list,
        description="List of shortlisted candidate section titles (maintained for backward compatibility)"
    )
    legal_regime: Optional[str] = Field(
        default="IPC + CrPC",
        description="Legal regime passed through from Stage 1 ('IPC + CrPC')"
    )

    verification_status: str = Field(
        default="VERIFIED",
        description="Verification status: PENDING, VERIFIED, or RETRY"
    )
    pipeline_transition: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Stage-to-stage transition audit: lists sections received from Stage 2, accepted, rejected (with reasons), and passing to Stage 4."
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.section_candidates and self.verified_offences:
            for vo in self.verified_offences:
                if vo.verification_status == "NOT_TRIGGERED":
                    conf = 0.0
                elif vo.classification == "PRIMARY":
                    conf = 0.95
                else:
                    conf = 0.80

                self.section_candidates.append(
                    SectionCandidateItem(
                        concept=vo.title,
                        section_number=vo.section_number,
                        section_title=vo.title,
                        confidence=conf,
                    )
                )
        if not self.chapter_candidates and self.verified_offences:
            seen_chaps = set()
            for vo in self.verified_offences:
                if vo.chapter_number not in seen_chaps:
                    seen_chaps.add(vo.chapter_number)
                    self.chapter_candidates.append(
                        ChapterCandidateItem(
                            concept=vo.title,
                            chapter_number=vo.chapter_number,
                            chapter_name=vo.chapter_title,
                            confidence=0.95,
                        )
                    )

    def to_downstream_json(self) -> str:
        return self.model_dump_json(indent=2)


class ChapterVerificationIssue(BaseModel):
    target: str = Field(description="Target chapter or section candidate ID/name")
    issue: str = Field(description="Detailed explanation of verification issue found")
    feedback: str = Field(description="Actionable feedback for correction")


class ChapterVerificationResult(BaseModel):
    status: str = Field(description="Status: 'VERIFIED' or 'RETRY'")
    issues: List[ChapterVerificationIssue] = Field(default_factory=list, description="List of issues identified")
    feedback: str = Field(default="Verification complete.", description="Overall summary feedback")
    verified_chapter_object: Optional[ChapterIdentificationObject] = Field(default=None, description="Verified ChapterIdentificationObject")
