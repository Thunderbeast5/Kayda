"""
Shared Pydantic schemas for the Virtual Moot Court system.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────
# Case Extraction Schemas
# ─────────────────────────────────────────────────────────────

class CitedFact(BaseModel):
    fact_label: str
    inferred_meaning: str
    verbatim_quote: str
    char_start: Optional[int] = None
    char_end: Optional[int] = None


class ProsecutionSubQuery(BaseModel):
    id: str
    query: str
    legal_concept: str
    bail_relevance: str
    supporting_facts: List[CitedFact]
    priority: int = Field(ge=1)


class ProsecutorOutput(BaseModel):
    """
    Result of the prosecutor's case understanding pass.
    Built AFTER lexigraphbe has already retrieved sections —
    so this analysis is informed by the actual verified law.
    NOT used to drive lexigraphbe.
    """
    schema_version: str = "1.0"
    case_summary: str
    victim: List[str] = Field(default_factory=list)
    accused: List[str] = Field(default_factory=list)
    relationship: str = ""
    legal_concepts: List[str] = Field(default_factory=list)
    sub_queries: List[ProsecutionSubQuery] = Field(default_factory=list)
    bail_rejection_summary: str = ""
    hallucination_flags: List[str] = Field(default_factory=list)
    verification_status: str = "PENDING"


# ─────────────────────────────────────────────────────────────
# Section Usage Plan
# Prosecutor decides, per section, when and why to deploy it.
# ─────────────────────────────────────────────────────────────

class SectionUsage(BaseModel):
    """
    For one retrieved section, the prosecutor decides:
      - which pillar it supports
      - when to use it (opening / rebuttal / only-if-defense-raises)
      - what specific fact from the case it anchors to
      - the argument it enables
    """
    section_number: str
    statute: str
    title: str
    pillar: str                   # P1:Gravity | P2:PrimaFacie | P3:CustodialInterrogation | P4:FlightRisk
    deploy_when: str              # "opening" | "rebuttal" | "conditional"
    anchored_fact: str            # the specific case fact this section applies to
    argument_enabled: str         # one sentence: what prosecution argument this unlocks
    prima_facie_strength: str     # from lexigraphbe: Strong | Moderate | Weak
    overall_status: str           # from lexigraphbe: Prima Facie Attracted | Partially Attracted | Not Attracted


class SectionUsagePlan(BaseModel):
    """
    The prosecutor's complete deployment plan for all retrieved sections.
    Stored in session. Drives which sections appear in which argument.
    """
    sections: List[SectionUsage] = Field(default_factory=list)

    def for_opening(self) -> List[SectionUsage]:
        return [s for s in self.sections if s.deploy_when == "opening"]

    def for_rebuttal(self) -> List[SectionUsage]:
        return [s for s in self.sections if s.deploy_when in ("opening", "rebuttal")]

    def conditional(self) -> List[SectionUsage]:
        return [s for s in self.sections if s.deploy_when == "conditional"]


# ─────────────────────────────────────────────────────────────
# Session State
# ─────────────────────────────────────────────────────────────

class TurnRecord(BaseModel):
    turn_number: int
    speaker: str                          # "prosecutor" | "defense"
    full_argument: str
    summary_bullets: List[str]            # 3-5 bullets — what LLM sees in future turns
    concepts_used: List[str]
    positions_asserted: List[str]
    pillars_covered: List[str] = Field(default_factory=list)
    sections_cited: List[str] = Field(default_factory=list)   # section numbers cited this turn


class RetrievedSection(BaseModel):
    """One IPC/BNS section from lexigraphbe. Stored once, never re-queried."""
    section_number: str
    statute: str
    title: str
    classification: str
    overall_status: str
    overall_prima_facie_strength: str
    punishment_text: str
    ingredient_evaluation: List[Dict[str, Any]] = Field(default_factory=list)
    legal_reasoning: str
    missing_supporting_facts: List[str] = Field(default_factory=list)
    investigation_requirements: List[str] = Field(default_factory=list)
    retrieved_at_turn: int = 0            # 0 = initial retrieval; >0 = mid-session


class SessionState(BaseModel):
    """
    Full moot court session state. Written after every turn.
    Maps cleanly to a DB document when frontend is connected.
    """
    session_id: str
    case_id: str
    case_text: str
    student_role: str

    prosecutor_output: Optional[ProsecutorOutput] = None
    section_usage_plan: Optional[SectionUsagePlan] = None

    # Sections keyed by section_number — never re-queried once stored
    retrieved_sections: Dict[str, RetrievedSection] = Field(default_factory=dict)

    # Repetition prevention
    argued_concepts: List[str] = Field(default_factory=list)
    prosecutor_positions: List[str] = Field(default_factory=list)
    defense_positions: List[str] = Field(default_factory=list)
    pillars_argued: List[str] = Field(default_factory=list)
    sections_cited_so_far: List[str] = Field(default_factory=list)

    turns: List[TurnRecord] = Field(default_factory=list)
    current_turn: int = 0
    status: str = "active"


# ─────────────────────────────────────────────────────────────
# Orchestrator Schemas
# ─────────────────────────────────────────────────────────────

class OrchestratorInput(BaseModel):
    """
    Simple: just the case text.
    Orchestrator runs lexigraphbe untouched and returns sections.
    """
    case_text: str


class VerifiedSection(BaseModel):
    section_number: str
    statute: str
    title: str
    classification: str
    overall_status: str
    overall_prima_facie_strength: str
    punishment_text: str
    ingredient_evaluation: List[Dict[str, Any]] = Field(default_factory=list)
    legal_reasoning: str
    missing_supporting_facts: List[str] = Field(default_factory=list)
    investigation_requirements: List[str] = Field(default_factory=list)


class OrchestratorResult(BaseModel):
    schema_version: str = "1.0"
    stage0_case_context: Dict[str, Any] = Field(default_factory=dict)
    stage1_legal_query: Dict[str, Any] = Field(default_factory=dict)
    stage2_subquery_mapping: Dict[str, Any] = Field(default_factory=dict)
    stage3_chapter_identification: Dict[str, Any] = Field(default_factory=dict)
    stage4_statutory_verification: Dict[str, Any] = Field(default_factory=dict)
    stage5_bail_reasoning: Dict[str, Any] = Field(default_factory=dict)
    stage6_precedent_retrieval: Dict[str, Any] = Field(default_factory=dict)
    verified_sections: List[VerifiedSection] = Field(default_factory=list)
    bail_recommendation: str = ""
    manual_review_flags: List[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# Argument Generation
# ─────────────────────────────────────────────────────────────

class ArgumentDecision(BaseModel):
    """
    Structured decision the LLM produces before writing any argument.
    Enforces non-repetition and controls orchestrator calls.
    """
    needs_new_sections: bool
    unaddressed_fact: str             # the specific fact for which no section exists yet
                                      # (only populated when needs_new_sections=True)
    new_concepts: List[str]
    pillars_to_address: List[str]
    countering: List[str]
    new_ground: List[str]
    sections_to_cite: List[str]       # section numbers the prosecutor will cite this turn
    argument: str
    summary_bullets: List[str]
    positions_asserted: List[str]