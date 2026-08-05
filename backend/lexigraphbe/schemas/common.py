"""
Common models, helper functions, and shared verification types for LexiGraph Schemas.
"""

import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


def _sanitize_manual_review(v: Any) -> List[str]:
    """Helper function to sanitize manual_review fields into clean list of strings."""
    if not v:
        return []
    if not isinstance(v, list):
        if isinstance(v, (str, dict)):
            v = [v]
        else:
            return []
    sanitized = []
    for item in v:
        if isinstance(item, str):
            sanitized.append(item)
        elif isinstance(item, dict):
            sec = item.get("section_number") or item.get("section") or item.get("target") or item.get("concept") or ""
            reason = item.get("reason") or item.get("issue") or item.get("details") or item.get("note") or ""
            if sec and reason:
                sanitized.append(f"{sec}: {reason}")
            elif sec:
                sanitized.append(str(sec))
            elif reason:
                sanitized.append(str(reason))
            else:
                sanitized.append(json.dumps(item, ensure_ascii=False))
        else:
            sanitized.append(str(item))
    return sanitized


class ManualReviewMixin(BaseModel):
    manual_review: List[str] = Field(
        default_factory=list,
        description="Flagged statutory inconsistencies, low confidence items, or unknown regime warnings"
    )

    @field_validator("manual_review", mode="before")
    @classmethod
    def validate_manual_review(cls, v: Any) -> List[str]:
        return _sanitize_manual_review(v)


# Explicit Mandatory Fields required for Stage 1 downstream legal agents
STAGE1_MANDATORY_FIELDS = [
    "accused_identity",
    "offence_narrative",
    "requested_relief",
    "procedural_stage",
    "legal_regime",
]

# Universal Baseline Procedural Documents checklist
UNIVERSAL_PROCEDURAL_DOCUMENTS = [
    "FIR / Complaint Copy",
    "Bail Application Copy",
]


class VerificationIssue(BaseModel):
    field: str = Field(description="Target field with issue")
    issue: str = Field(description="Description of the issue or discrepancy")
    feedback: str = Field(description="Actionable feedback for intake agent correction")


class VerificationResult(BaseModel):
    status: str = Field(description="Verification status: 'VERIFIED' or 'NEEDS_CORRECTION'")
    contract_status: str = Field(default="UNCHECKED", description="Stage 1 Hard Contract status: 'CONTRACT_PASSED', 'CONTRACT_WARNING', 'CONTRACT_BLOCKED'")
    issues: List[VerificationIssue] = Field(default_factory=list, description="List of identified issues if status is NEEDS_CORRECTION")
    feedback: Optional[str] = Field(default=None, description="Overall verification feedback summary")
    verified_case_profile: Optional[Any] = Field(default=None, description="The verified CaseProfile if status is VERIFIED")

    def export_case_context_object(self) -> Any:
        import datetime
        from .stage0 import CaseContextObject, CaseProfile
        profile = self.verified_case_profile or CaseProfile()
        status, violations = profile.validate_stage1_contract()
        accused_names = profile.get_accused_list()

        return CaseContextObject(
            schema_version="1.0",
            case_profile=profile,
            contract_status=status,
            contract_violations=violations,
            verification_status=self.status,
            active_parties=accused_names,
            system_metadata={
                "intake_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "overall_confidence": profile.overall_confidence,
                "low_confidence_count": len(profile.low_confidence_fields),
                "flag_for_confirmation": profile.flag_for_confirmation,
            }
        )
