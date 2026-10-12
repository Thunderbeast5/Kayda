"""
Stage 5 Pydantic Schemas: Anticipatory Bail Reasoning Engine -> BailReasoningObject
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from .common import ManualReviewMixin, _sanitize_manual_review


class BailFactorEvaluationItem(BaseModel):
    value: str = Field(description="Evaluated factor value e.g. 'High', 'Medium', 'Low', 'Required', 'Not Required', 'Strong', 'Weak', 'None', 'Cooperative'")
    reason: Optional[str] = Field(default=None, description="Factual justification grounded strictly in available case facts")


class BailEvaluationMap(BaseModel):
    gravity_of_offence: BailFactorEvaluationItem = Field(description="Gravity of accusation evaluation")
    prima_facie_case: BailFactorEvaluationItem = Field(description="Prima facie case evaluation based on Stage 4 verified statutory ingredients")
    custodial_interrogation: BailFactorEvaluationItem = Field(description="Custodial interrogation requirement assessment")
    witness_tampering: BailFactorEvaluationItem = Field(description="Witness tampering / intimidation risk assessment")
    evidence_tampering: BailFactorEvaluationItem = Field(description="Evidence tampering risk assessment")
    flight_risk: BailFactorEvaluationItem = Field(description="Flight risk assessment")
    criminal_antecedents: BailFactorEvaluationItem = Field(description="Criminal antecedents assessment")
    cooperation: BailFactorEvaluationItem = Field(description="Cooperation with investigation assessment")


class OverallBailRecommendation(BaseModel):
    decision: str = Field(description="Bail decision: 'Recommend Grant Anticipatory Bail', 'Recommend Reject Anticipatory Bail', or 'Recommend Conditional Anticipatory Bail'")
    confidence: float = Field(description="Overall decision confidence score (0.0 to 1.0)")
    summary_reasoning: Optional[str] = Field(default=None, description="Judicial reasoning summary supporting the bail decision")


class SideArgumentPackage(BaseModel):
    target_side: str = Field(description="Role side: 'PROSECUTION' or 'DEFENSE'")
    primary_objective: str = Field(description="Objective: 'REJECT_BAIL' for Prosecution, 'GRANT_BAIL' for Defense")
    key_factors_highlighted: List[str] = Field(default_factory=list, description="Key statutory bail factors emphasized")
    argument_points: List[str] = Field(default_factory=list, description="Structured legal argument points grounded in facts and law")
    suggested_conditions_or_objections: List[str] = Field(default_factory=list, description="Prosecution objections or Defense proposed bail conditions")


class BailReasoningObject(ManualReviewMixin):
    schema_version: str = Field(default="5.0", description="Schema version of BailReasoningObject contract")
    target_side: str = Field(default="BOTH", description="Target role side: 'PROSECUTION', 'DEFENSE', or 'BOTH'")
    bail_provision_applied: str = Field(default="Section 438 CrPC", description="Statutory bail provision applied ('Section 438 CrPC')")
    legal_regime: Optional[str] = Field(default="IPC + CrPC", description="Legal regime passed through unchanged ('IPC + CrPC')")
    bail_evaluation: BailEvaluationMap = Field(description="Structured evaluation of 8 judicially developed anticipatory bail factors")
    prosecution_arguments: Optional[SideArgumentPackage] = Field(default=None, description="Prosecution argument package advocating bail DENIAL")
    defense_arguments: Optional[SideArgumentPackage] = Field(default=None, description="Defense argument package advocating bail GRANT")
    overall_recommendation: OverallBailRecommendation = Field(description="Overall judicial anticipatory bail recommendation")
    verification_status: str = Field(default="PENDING", description="Verification status: PENDING, VERIFIED, or RETRY")

    def to_downstream_json(self) -> str:
        return self.model_dump_json(indent=2)


class BailVerificationIssue(BaseModel):
    target: str = Field(description="Target bail factor or recommendation item with audit error")
    issue: str = Field(description="Detailed description of bail reasoning audit issue")
    feedback: str = Field(description="Actionable instructions for bail reasoning agent correction")


class BailVerificationResult(BaseModel):
    status: str = Field(description="Status: 'VERIFIED' or 'RETRY'")
    issues: List[BailVerificationIssue] = Field(default_factory=list, description="List of audit issues identified")
    feedback: str = Field(default="Bail reasoning verification audit complete.", description="Overall summary feedback")
    verified_bail_object: Optional[BailReasoningObject] = Field(default=None, description="Verified BailReasoningObject")
