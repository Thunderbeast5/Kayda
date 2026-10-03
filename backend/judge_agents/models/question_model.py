"""
JudgeQuestion model.

Represents a single clarification question raised by the Judge
during a hearing, along with the answer received.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class QuestionTarget(str, Enum):
    """Who the Judge is directing the question to."""
    DEFENCE     = "Defence"
    PROSECUTION = "Prosecution"
    IO_AGENT    = "IO Agent"


class JudgeQuestion(BaseModel):
    """
    A single targeted clarification question from the Judge.

    Fields
    ------
    target      : who is being asked
    issue       : the specific legal or factual gap identified
    question    : the precise one-sentence question
    answer      : filled in after the target agent responds (None until then)
    round       : which debate round this question was raised in
    """
    target:   QuestionTarget
    issue:    str = Field(..., description="Specific legal or factual gap")
    question: str = Field(..., description="Precise one-sentence question")
    answer:   Optional[str] = None
    round:    int = 1

    def is_answered(self) -> bool:
        return self.answer is not None and self.answer.strip() != ""

    def to_dict(self) -> dict:
        return {
            "target":   self.target.value,
            "issue":    self.issue,
            "question": self.question,
            "answer":   self.answer or "",
        }
