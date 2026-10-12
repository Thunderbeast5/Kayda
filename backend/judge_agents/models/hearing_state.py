"""
HearingState enum and HearingContext model.

Tracks the Judge Agent's internal state machine through an
anticipatory bail hearing.
"""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class HearingState(str, Enum):
    """
    All possible states the Judge Agent can be in during a hearing.
    Transitions are managed by BailJudgeAgent._transition().
    """
    IDLE                = "IDLE"
    RECEIVING_INPUTS    = "RECEIVING_INPUTS"
    COMPREHENDING_CASE  = "COMPREHENDING_CASE"
    HEARING_OPEN        = "HEARING_OPEN"
    EVALUATING_ARGUMENTS = "EVALUATING_ARGUMENTS"
    QUESTIONING         = "QUESTIONING"
    AWAITING_ANSWERS    = "AWAITING_ANSWERS"
    DETECTING_NEW_ISSUES = "DETECTING_NEW_ISSUES"
    AWAITING_RETRIEVAL  = "AWAITING_RETRIEVAL"
    HEARING_FINAL_SUBS  = "HEARING_FINAL_SUBS"
    FORMING_FINDINGS    = "FORMING_FINDINGS"
    FINDINGS_COMPLETE   = "FINDINGS_COMPLETE"


# Valid state transitions
_TRANSITIONS: dict[HearingState, list[HearingState]] = {
    HearingState.IDLE:                  [HearingState.RECEIVING_INPUTS],
    HearingState.RECEIVING_INPUTS:      [HearingState.COMPREHENDING_CASE],
    HearingState.COMPREHENDING_CASE:    [HearingState.HEARING_OPEN],
    HearingState.HEARING_OPEN:          [HearingState.EVALUATING_ARGUMENTS],
    HearingState.EVALUATING_ARGUMENTS:  [
        HearingState.QUESTIONING,
        HearingState.DETECTING_NEW_ISSUES,
        HearingState.HEARING_FINAL_SUBS,
    ],
    HearingState.QUESTIONING:           [HearingState.AWAITING_ANSWERS],
    HearingState.AWAITING_ANSWERS:      [
        HearingState.EVALUATING_ARGUMENTS,
        HearingState.DETECTING_NEW_ISSUES,
        HearingState.HEARING_FINAL_SUBS,
    ],
    HearingState.DETECTING_NEW_ISSUES:  [
        HearingState.AWAITING_RETRIEVAL,
        HearingState.HEARING_FINAL_SUBS,
        HearingState.EVALUATING_ARGUMENTS,
    ],
    HearingState.AWAITING_RETRIEVAL:    [HearingState.EVALUATING_ARGUMENTS],
    HearingState.HEARING_FINAL_SUBS:    [HearingState.FORMING_FINDINGS],
    HearingState.FORMING_FINDINGS:      [HearingState.FINDINGS_COMPLETE],
    HearingState.FINDINGS_COMPLETE:     [],  # terminal
}


class HearingContext(BaseModel):
    """
    Carries the Judge's current state and a log of all state transitions
    during a single hearing session.
    """
    session_id: str
    current_state: HearingState = HearingState.IDLE
    state_history: List[str] = Field(default_factory=list)
    questions_asked_count: int = 0
    dynamic_retrieval_count: int = 0
    debate_round: int = 0

    def transition(self, new_state: HearingState) -> None:
        """
        Move to a new state. Raises ValueError on illegal transition.
        """
        allowed = _TRANSITIONS.get(self.current_state, [])
        if new_state not in allowed:
            raise ValueError(
                f"Illegal state transition: {self.current_state} → {new_state}. "
                f"Allowed: {[s.value for s in allowed]}"
            )
        self.state_history.append(
            f"{self.current_state.value} → {new_state.value}"
        )
        self.current_state = new_state

    def can_ask_question(self, max_questions: int = 5) -> bool:
        return self.questions_asked_count < max_questions

    def can_trigger_retrieval(self) -> bool:
        # Prevent retrieval loops — max 2 dynamic retrievals per hearing
        return self.dynamic_retrieval_count < 2
