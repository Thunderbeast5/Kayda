"""
Judge Agents — Virtual Moot Court: Anticipatory Bail
Phase 1: Core Judge Agent (scoring + findings)
Phase 2: QuestionGenerator + CourtRoomStateMemory + Answer Ingestion
Phase 3: IssueDetector + DynamicRetrievalTrigger + Hearing Resume
Phase 4: AI Courtroom Orchestrator + Full Hearing Graph
"""

from .judge_agent import (
    BailJudgeAgent,
    bail_judge_score_node,
    bail_judge_verdict_node,
    should_proceed_to_verdict,
)
from .courtroom_memory import CourtRoomStateMemory, get_memory, clear_memory
from .dynamic_retrieval import DynamicRetrievalTrigger, RetrievalResult
from .orchestrator import build_hearing_graph, run_hearing

__all__ = [
    "BailJudgeAgent",
    "bail_judge_score_node",
    "bail_judge_verdict_node",
    "should_proceed_to_verdict",
    "CourtRoomStateMemory",
    "get_memory",
    "clear_memory",
    "DynamicRetrievalTrigger",
    "RetrievalResult",
    "build_hearing_graph",
    "run_hearing",
]
