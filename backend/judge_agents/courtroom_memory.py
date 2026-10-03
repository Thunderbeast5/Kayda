"""
CourtRoomStateMemory — Phase 2
===============================
Shared memory store for all courtroom agents during a hearing.

Every agent reads from and writes to this store.
The Judge Agent uses it to track the full conversation history,
questions asked, answers received, evidence discussed, and
retrieved laws/precedents across all debate rounds.

Design
------
- In-process dict-based store (no external dependency required).
- Keyed by case_id so multiple hearings can run in the same process.
- All writes are append-only (no history is ever deleted mid-hearing).
- Serialisable to JSON for persistence / LangGraph state passing.

Agents that read/write
----------------------
  Defence Agent        — writes arguments, reads judge questions
  Prosecutor Agent     — writes arguments, reads judge questions
  IO Agent             — writes investigation report, reads judge questions
  Judge Agent          — writes questions, reads all arguments + answers
  Orchestrator         — reads full memory to decide turn order
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Turn model ─────────────────────────────────────────────────────────────────

class HearingTurn(BaseModel):
    """
    A single turn in the courtroom hearing.

    speaker    : "Judge" | "Defence" | "Prosecution" | "IO Agent" | "System"
    turn_type  : "argument" | "question" | "answer" | "submission" | "finding"
    content    : the actual text spoken / submitted
    round      : debate round number (starts at 1)
    timestamp  : UTC ISO string
    metadata   : optional extra fields (section cited, evidence referenced, etc.)
    """
    speaker:    str
    turn_type:  str
    content:    str
    round:      int = 1
    timestamp:  str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata:   dict[str, Any] = Field(default_factory=dict)


# ── Memory store ───────────────────────────────────────────────────────────────

class CourtRoomStateMemory:
    """
    Central shared memory for one anticipatory bail hearing.

    Usage
    -----
    memory = CourtRoomStateMemory(case_id="FIR_2026_001")

    # Agents write their turns
    memory.add_turn("Defence", "argument", "1. No prior criminal record...")
    memory.add_turn("Judge",   "question", "Is custodial interrogation needed?",
                    metadata={"target": "IO Agent"})

    # Agents read what they need
    history = memory.get_history()
    questions = memory.get_unanswered_questions()

    # Judge reads everything
    summary = memory.to_summary_string()
    """

    def __init__(self, case_id: str):
        self.case_id:   str = case_id
        self._turns:    list[HearingTurn] = []

        # Quick-access indexes
        self._questions:    list[HearingTurn] = []   # all Judge questions
        self._answers:      list[HearingTurn] = []   # all answers to Judge questions
        self._laws_cited:   list[str] = []            # sections referenced during hearing
        self._precedents_cited: list[str] = []        # cases cited during hearing
        self._evidence_discussed: list[str] = []      # evidence items raised

    # ── Write ──────────────────────────────────────────────────────────────────

    def add_turn(
        self,
        speaker: str,
        turn_type: str,
        content: str,
        round: int = 1,
        metadata: Optional[dict] = None,
    ) -> HearingTurn:
        """
        Append a new turn to the hearing history.

        Parameters
        ----------
        speaker   : "Judge" | "Defence" | "Prosecution" | "IO Agent" | "System"
        turn_type : "argument" | "question" | "answer" | "submission" | "finding"
        content   : the text content
        round     : debate round number
        metadata  : optional extra data

        Returns
        -------
        The created HearingTurn object.
        """
        turn = HearingTurn(
            speaker=speaker,
            turn_type=turn_type,
            content=content,
            round=round,
            metadata=metadata or {},
        )
        self._turns.append(turn)

        # Maintain quick-access indexes
        if turn_type == "question":
            self._questions.append(turn)
        elif turn_type == "answer":
            self._answers.append(turn)

        # Extract mentioned sections (BNS/IPC/BNSS/BSA patterns)
        import re
        for match in re.finditer(
            r'\b(BNS|IPC|BNSS|BSA|POCSO|IT Act|NDPS)\s+\d+[A-Za-z]?\b',
            content, re.IGNORECASE
        ):
            sec = match.group(0).strip()
            if sec not in self._laws_cited:
                self._laws_cited.append(sec)

        return turn

    def record_question(
        self,
        question_text: str,
        target: str,
        issue: str,
        round: int = 1,
    ) -> HearingTurn:
        """Convenience method — record a Judge question with routing metadata."""
        return self.add_turn(
            speaker="Judge",
            turn_type="question",
            content=question_text,
            round=round,
            metadata={"target": target, "issue": issue, "answered": False},
        )

    def record_answer(
        self,
        answer_text: str,
        respondent: str,
        question_index: int,
        round: int = 1,
    ) -> HearingTurn:
        """
        Record an answer to a specific question.
        Also marks the corresponding question turn as answered.
        """
        turn = self.add_turn(
            speaker=respondent,
            turn_type="answer",
            content=answer_text,
            round=round,
            metadata={"answers_question_index": question_index},
        )
        # Mark the question as answered
        if 0 <= question_index < len(self._questions):
            self._questions[question_index].metadata["answered"] = True
        return turn

    def record_evidence(self, evidence_item: str) -> None:
        """Mark a piece of evidence as having been discussed in the hearing."""
        if evidence_item not in self._evidence_discussed:
            self._evidence_discussed.append(evidence_item)

    def record_precedent(self, case_name: str) -> None:
        """Mark a precedent as having been cited."""
        if case_name not in self._precedents_cited:
            self._precedents_cited.append(case_name)

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_history(self, speaker: Optional[str] = None) -> list[HearingTurn]:
        """Return all turns, optionally filtered by speaker."""
        if speaker:
            return [t for t in self._turns if t.speaker.lower() == speaker.lower()]
        return list(self._turns)

    def get_unanswered_questions(self) -> list[HearingTurn]:
        """Return all Judge questions that have not yet been answered."""
        return [q for q in self._questions if not q.metadata.get("answered", False)]

    def get_answered_questions(self) -> list[tuple[HearingTurn, Optional[HearingTurn]]]:
        """
        Return list of (question_turn, answer_turn) pairs.
        answer_turn is None if no answer received yet.
        """
        result = []
        for i, q in enumerate(self._questions):
            answer = next(
                (a for a in self._answers
                 if a.metadata.get("answers_question_index") == i),
                None,
            )
            result.append((q, answer))
        return result

    def get_latest_round_turns(self, round: int) -> list[HearingTurn]:
        """Return all turns from a specific debate round."""
        return [t for t in self._turns if t.round == round]

    def get_laws_cited(self) -> list[str]:
        return list(self._laws_cited)

    def get_precedents_cited(self) -> list[str]:
        return list(self._precedents_cited)

    def get_evidence_discussed(self) -> list[str]:
        return list(self._evidence_discussed)

    def turn_count(self) -> int:
        return len(self._turns)

    def question_count(self) -> int:
        return len(self._questions)

    # ── Summary for LLM prompt injection ──────────────────────────────────────

    def to_summary_string(self, max_turns: int = 20) -> str:
        """
        Compact text representation of the most recent turns.
        Used to inject hearing history into the Judge's LLM prompts.
        """
        recent = self._turns[-max_turns:] if len(self._turns) > max_turns else self._turns
        if not recent:
            return "No previous turns recorded."

        lines = []
        for t in recent:
            prefix = f"[Round {t.round}] {t.speaker.upper()} ({t.turn_type})"
            lines.append(f"{prefix}:\n{t.content}")

        summary = "\n\n".join(lines)

        if self._laws_cited:
            summary += f"\n\nLaws cited so far: {', '.join(self._laws_cited)}"
        if self._precedents_cited:
            summary += f"\nPrecedents cited: {', '.join(self._precedents_cited)}"

        return summary

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Full serialisation — used for LangGraph state and persistence."""
        return {
            "case_id": self.case_id,
            "turns": [t.model_dump() for t in self._turns],
            "laws_cited": self._laws_cited,
            "precedents_cited": self._precedents_cited,
            "evidence_discussed": self._evidence_discussed,
            "question_count": self.question_count(),
            "turn_count": self.turn_count(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CourtRoomStateMemory":
        """Reconstruct from a serialised dict (e.g. from LangGraph state)."""
        memory = cls(case_id=data.get("case_id", "unknown"))
        for t_data in data.get("turns", []):
            turn = HearingTurn(**t_data)
            memory._turns.append(turn)
            if turn.turn_type == "question":
                memory._questions.append(turn)
            elif turn.turn_type == "answer":
                memory._answers.append(turn)
        memory._laws_cited       = data.get("laws_cited", [])
        memory._precedents_cited = data.get("precedents_cited", [])
        memory._evidence_discussed = data.get("evidence_discussed", [])
        return memory

    def to_list(self) -> list[dict]:
        """Compact list format for injecting into LangGraph state key."""
        return [t.model_dump() for t in self._turns]


# ── Global registry ────────────────────────────────────────────────────────────
# Allows multiple hearings to share one memory store registry per process.

_registry: dict[str, CourtRoomStateMemory] = {}


def get_memory(case_id: str) -> CourtRoomStateMemory:
    """Get or create a CourtRoomStateMemory for the given case_id."""
    if case_id not in _registry:
        _registry[case_id] = CourtRoomStateMemory(case_id=case_id)
    return _registry[case_id]


def clear_memory(case_id: str) -> None:
    """Clear memory for a case (end of hearing cleanup)."""
    _registry.pop(case_id, None)
