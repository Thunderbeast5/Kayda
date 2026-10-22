"""
Orchestrator SimulationState
=============================
Single source of truth for the entire moot court simulation.
All agents read from and write to this state — no peer-to-peer communication.
"""

from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional, TypedDict


from pydantic import BaseModel, ConfigDict, Field


# ── Sub-types ─────────────────────────────────────────────────────────────────

class Fact(BaseModel):
    id: str                  # fact_1, fact_2...
    text: str                # "NBW issued on 03.11.2022; applicants did not appear"
    source: str = "record"   # "para 14" / "FIR" / "user input"
    type: str = "allegation" # "allegation" | "procedural_event" | "court_finding"

    model_config = ConfigDict(extra="allow")

    def __getitem__(self, item: str) -> Any:
        if item in ("text", "value"):
            return self.text
        if item == "id":
            return self.id
        if item == "source":
            return self.source
        if item == "type":
            return getattr(self, "type", "allegation")
        if item == "label":
            return getattr(self, "label", "fact")
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        try:
            return self[item]
        except (KeyError, AttributeError):
            return default


class EvidenceItem(TypedDict):
    item: str                # e.g. "fir", "medical_report", "eyewitnesses", "weapon", "cctv", "forensics", "complainant"
    status: Literal["present", "not_on_record"]
    details: Optional[str]   # e.g. "Recovered blood-stained knife", "No post-mortem report produced"


class ArgumentStructure(TypedDict, total=False):
    theory: str
    arguments: List[str]
    evidence_refs: List[str]
    sections: List[str]


class Turn(TypedDict, total=False):
    turn_no: int
    speaker: str             # "prosecutor" | "defense" | "accused" | "judge"
    round_no: int
    content: str
    citations: List[str]     # citations with Act names (e.g. ["IPC 324", "CrPC 438"])
    evidence_refs: List[str] # evidence references tracing to facts (e.g. ["fact_1", "fact_3"])
    structured_argument: Optional[ArgumentStructure]
    grounded: bool
    unverified: List[str]
    is_human: Optional[bool]
    display_name: Optional[str]


class Question(TypedDict):
    question_id: str
    asked_by: str            # always "judge"
    to: str                  # always "accused"
    question: str
    answered: bool
    answer: Optional[str]


class SideScore(TypedDict, total=False):
    legal_validity: float    # 0–10
    evidence_linkage: float  # 0–10
    logic_coherence: float   # 0–10
    total: float             # 0–30
    average: float           # 0–10


class JudgeScores(TypedDict, total=False):
    prosecution: SideScore
    defense: SideScore
    overall: float           # 0–10
    legal_validity: Optional[float]
    evidence_linkage: Optional[float]
    logic_coherence: Optional[float]


class Verdict(TypedDict):
    decision: str            # "granted" | "denied" | "no_opinion" | "interim"
    confidence: float        # 0.0–1.0
    laws_applied: List[str]
    reasoning: str



# ── Main state ────────────────────────────────────────────────────────────────

class SimulationState(TypedDict):
    # Session identity
    session_id: str
    case_id: str

    # AI vs Human mode & roles
    mode: Literal["ai_vs_human", "ai_vs_ai"]
    user_role: Optional[Literal["prosecutor", "defense"]]
    ai_role: Optional[Literal["prosecutor", "defense"]]
    human_argument: Optional[str]

    # Phase — drives routing
    phase: Literal["INIT", "EVIDENCE", "LEXIGRAPH", "COURTROOM", "VERDICT", "DONE", "FAILED"]

    # Stage outputs (populated progressively)
    case_facts: List[Fact]                # from Evidence Analyzer
    evidence_inventory: List[EvidenceItem] # inventory of present vs absent evidence items
    evidence_map: Dict[str, Any]          # evidence item -> matched statutory elements
    lexigraph_output: Dict[str, Any]      # full 7-stage lexigraphbe output
    holdings: List[Dict[str, Any]]        # retrieved judicial precedent holdings
    case_context: Dict[str, Any]          # Stage 0 CaseIntakeAgent output

    # Verification gates — courtroom cannot start until both are True
    verified: Dict[str, bool]            # {"evidence": bool, "lexigraph": bool}

    # Courtroom loop
    round_no: int
    max_rounds: int
    current_speaker: str
    transcript: List[Turn]
    pending_questions: List[Question]
    judge_scores: Dict[str, Any]
    clarification_needed: bool

    # Verdict
    verdict: Optional[Verdict]

    # Error accumulator
    errors: List[str]

    # Retry counters (internal — not sent to frontend)
    _evidence_retries: int
    _lexigraph_retries: int

