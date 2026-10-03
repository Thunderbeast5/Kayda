"""
Evidence Analyzer - Pydantic Schemas
======================================
All data models for the Case Preparation pipeline.

Key separation:
  CaseBrief    - safe to show students (NO court outcome, NO ratio decidendi)
  HiddenGround - judge/evaluator only (actual decision, reasoning)
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


# ====================================================================
# Sub-models
# ====================================================================

class VehicleItem(BaseModel):
    type: Optional[str] = None
    registration_no: Optional[str] = None
    make_model: Optional[str] = None
    engine_chassis_no: Optional[str] = None
    estimated_value: Optional[str] = None


class TimelineEvent(BaseModel):
    event_id: str = ""
    date: Optional[str] = None           # DD/MM/YYYY
    time: Optional[str] = None           # HH:MM (24h)
    event_type: str = "other"
    description: Optional[str] = None
    actors: List[str] = Field(default_factory=list)
    witnesses: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    amount: Optional[str] = None


class ProceduralStep(BaseModel):
    date: Optional[str] = None
    event: str = ""


# ====================================================================
# Stage 1 - raw extracted facts
# ====================================================================

class FIRFacts(BaseModel):
    """Extracted from FIR / Police Complaint. ALL fields are PUBLIC."""
    document_type: str = "fir"
    fir_number: Optional[str] = None
    police_station: Optional[str] = None
    district: Optional[str] = None
    date_filed: Optional[str] = None
    investigating_officer: Optional[str] = None
    complainant: Optional[str] = None
    accused: List[str] = Field(default_factory=list)
    victims: List[str] = Field(default_factory=list)
    incident_summary: Optional[str] = None
    incident_date: Optional[str] = None
    incident_time: Optional[str] = None
    incident_place: Optional[str] = None
    modus_operandi: Optional[str] = None
    cash_stolen: Optional[str] = None
    gold_stolen: Optional[str] = None
    vehicles_involved: List[VehicleItem] = Field(default_factory=list)
    other_property_stolen: List[str] = Field(default_factory=list)
    total_estimated_loss: Optional[str] = None
    sections_charged: List[str] = Field(default_factory=list)
    evidence_summary: List[str] = Field(default_factory=list)
    witness_names: List[str] = Field(default_factory=list)
    investigation_status: Optional[str] = None


class BailOrderFacts(BaseModel):
    """
    Extracted from Anticipatory Bail Application or Court Bail Order.
    Contains BOTH public facts and hidden court outcome.
    Split downstream into CaseBrief + HiddenGround.
    """
    document_type: str = "bail_order"
    case_number: Optional[str] = None
    court: Optional[str] = None
    judge: Optional[str] = None
    date_of_order: Optional[str] = None
    bail_type: str = "anticipatory"
    applicant: Optional[str] = None
    respondent: Optional[str] = None
    complainant: Optional[str] = None
    victims: List[str] = Field(default_factory=list)
    co_accused: List[str] = Field(default_factory=list)
    applicant_counsel: Optional[str] = None
    state_counsel: Optional[str] = None
    investigating_officer: Optional[str] = None
    fir_number: Optional[str] = None
    police_station: Optional[str] = None
    district: Optional[str] = None
    incident_summary: Optional[str] = None
    incident_date: Optional[str] = None
    incident_time: Optional[str] = None
    incident_place: Optional[str] = None
    offence_nature: Optional[str] = None
    sections_charged: List[str] = Field(default_factory=list)
    property_stolen: List[str] = Field(default_factory=list)
    total_loss: Optional[str] = None
    chargesheet_filed: Optional[bool] = None
    applicant_described_as_absconding: Optional[bool] = None
    custodial_interrogation_sought: Optional[bool] = None
    identification_parade_required: Optional[bool] = None
    defense_submissions: List[str] = Field(default_factory=list)
    prosecution_submissions: List[str] = Field(default_factory=list)
    procedural_history: List[ProceduralStep] = Field(default_factory=list)
    evidence_items: List[str] = Field(default_factory=list)
    # HIDDEN fields - court outcome only goes into HiddenGround
    actual_bail_outcome: Optional[str] = None
    court_reasoning: Optional[str] = None
    bail_conditions_imposed: List[str] = Field(default_factory=list)
    bail_amount: Optional[str] = None
    ratio_decidendi: Optional[str] = None
    judicial_observations: List[str] = Field(default_factory=list)
    key_legal_findings: List[str] = Field(default_factory=list)


# ====================================================================
# Stage 2 - PUBLIC vs HIDDEN split
# ====================================================================

class CaseBrief(BaseModel):
    """
    Student-facing. NEVER contains bail outcome, ratio decidendi,
    court findings, or final orders.
    Safe for Prosecution + Defense agents.
    """
    document_type: str
    bail_type: str = "anticipatory"
    case_number: Optional[str] = None
    court: Optional[str] = None
    fir_number: Optional[str] = None
    police_station: Optional[str] = None
    district: Optional[str] = None
    applicant: Optional[str] = None
    respondent: Optional[str] = None
    complainant: Optional[str] = None
    victims: List[str] = Field(default_factory=list)
    co_accused: List[str] = Field(default_factory=list)
    incident_summary: str = ""
    offence_nature: Optional[str] = None
    incident_date: Optional[str] = None
    incident_time: Optional[str] = None
    incident_place: Optional[str] = None
    sections_charged: List[str] = Field(default_factory=list)
    evidence_items: List[str] = Field(default_factory=list)
    investigation_facts: List[str] = Field(default_factory=list)
    chargesheet_filed: Optional[bool] = None
    custodial_interrogation_sought: Optional[bool] = None
    identification_parade_required: Optional[bool] = None
    prosecution_submissions: List[str] = Field(default_factory=list)
    defense_submissions: List[str] = Field(default_factory=list)
    procedural_history: List[ProceduralStep] = Field(default_factory=list)
    property_stolen: List[str] = Field(default_factory=list)
    total_loss: Optional[str] = None
    raw_case_narrative: str = ""


class HiddenGround(BaseModel):
    """
    Judge/evaluator only.
    Contains the real outcome and court reasoning.
    NEVER sent to student-facing agents.
    """
    actual_bail_outcome: Optional[str] = None
    bail_conditions_imposed: List[str] = Field(default_factory=list)
    bail_amount: Optional[str] = None
    ratio_decidendi: Optional[str] = None
    court_reasoning: Optional[str] = None
    key_legal_findings: List[str] = Field(default_factory=list)
    judicial_observations: List[str] = Field(default_factory=list)
    expected_outcome_justification: str = ""


class CasePrepResult(BaseModel):
    """
    Final output of CasePrepAgent.prepare().
    Orchestrator routes:
      case_brief    -> Prosecution + Defense agents
      hidden_ground -> Judge agent only
      timeline      -> all agents
    """
    session_id: str = ""
    document_type: str = "bail_order"
    case_brief: CaseBrief
    hidden_ground: HiddenGround
    timeline: List[TimelineEvent] = Field(default_factory=list)
    raw_text: str = ""
    extraction_warnings: List[str] = Field(default_factory=list)
