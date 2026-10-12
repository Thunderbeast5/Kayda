"""
JudicialFindings Pydantic model.

This is the primary output of the BailJudgeAgent.
It is passed to the Legal Verification Agent for correctness checks
before the Bail Order Generator produces the final order.

Schema mirrors section 8 of JUDGE_AGENT.md exactly.
"""

from typing import Optional, List, Literal
from pydantic import BaseModel, Field


# ── Sub-models ────────────────────────────────────────────────────────────────

class PrecedentApplied(BaseModel):
    case_name:        str
    citation:         str
    principle_applied: str


class EvidenceEvaluation(BaseModel):
    strength:             Literal["High", "Medium", "Low"]
    key_evidence:         List[str] = Field(default_factory=list)
    contradictions_noted: List[str] = Field(default_factory=list)
    missing_evidence:     List[str] = Field(default_factory=list)


class BailFactorAnalysis(BaseModel):
    gravity_of_offence:    Literal["High", "Medium", "Low"]
    flight_risk:           Literal["High", "Medium", "Low"]
    custodial_need:        Literal["Yes", "No"]
    witness_tampering_risk: Literal["High", "Medium", "Low"]
    antecedents:           str   # "None" or brief description
    mitigating_factors:    List[str] = Field(default_factory=list)
    aggravating_factors:   List[str] = Field(default_factory=list)


class ArgumentScore(BaseModel):
    legal_validity:   int = Field(ge=0, le=10)
    evidence_linkage: int = Field(ge=0, le=10)
    logic_coherence:  int = Field(ge=0, le=10)
    total:            int = Field(ge=0, le=30)

    @classmethod
    def from_dict(cls, d: dict) -> "ArgumentScore":
        lv = int(d.get("legal_validity", 0))
        el = int(d.get("evidence_linkage", 0))
        lc = int(d.get("logic_coherence", 0))
        return cls(
            legal_validity=lv,
            evidence_linkage=el,
            logic_coherence=lc,
            total=d.get("total", lv + el + lc),
        )


class ArgumentEvaluation(BaseModel):
    defence_score:     ArgumentScore
    prosecution_score: ArgumentScore


class QuestionRecord(BaseModel):
    target:   str
    question: str
    answer:   str = ""


# ── Main model ────────────────────────────────────────────────────────────────

class JudicialFindings(BaseModel):
    """
    Complete output of the BailJudgeAgent after a full anticipatory bail hearing.
    Passed to Legal Verification Agent unchanged.
    """
    # Identifiers
    case_id:      str
    hearing_date: str   # DD/MM/YYYY
    judge_name:   str = "AI Judge"

    # Parties
    applicant:  str
    respondent: str     # e.g. "State of Maharashtra"

    # Law applied (only sections from legal_context_package — no hallucination)
    sections_applied:              List[str] = Field(default_factory=list)
    constitutional_articles_applied: List[str] = Field(default_factory=list)
    precedents_applied:            List[PrecedentApplied] = Field(default_factory=list)

    # Evidence
    evidence_evaluation: EvidenceEvaluation

    # Bail factors
    bail_factor_analysis: BailFactorAnalysis

    # Argument scoring
    argument_evaluation: ArgumentEvaluation

    # Core judicial reasoning (multi-paragraph, formal language)
    judicial_analysis: str

    # Outcome (NOT a final order — passed to Legal Verification Agent first)
    preliminary_finding: Literal[
        "Bail Likely Granted",
        "Bail Likely Rejected",
        "Inconclusive",
    ]
    confidence: int = Field(ge=0, le=100, description="Judge's confidence % in the finding")

    # Conditions to attach if bail is granted
    conditions_if_granted: List[str] = Field(default_factory=list)

    # Hearing process metadata
    questions_asked:             List[QuestionRecord] = Field(default_factory=list)
    dynamic_retrieval_triggered: bool = False
    new_issues_identified:       List[str] = Field(default_factory=list)
    state_history:               List[str] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump()
