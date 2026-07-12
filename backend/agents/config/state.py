from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph


class AgentState(TypedDict):
    session_id: str
    user_query: str
    structured_facts: dict
    relevant_laws: List[dict]       # top-ranked IPC sections from LexiGraph
    lexigraph_result: dict          # full LexiGraph output (counts, keywords, etc.)
    prosecution_args: str
    defense_args: str
    # ── Judge / Accused loop ──────────────────────────────────────────
    judge_scores: dict              # {prosecution: {legal:n, evidence:n, logic:n}, defense: {...}}
    judge_question: str             # question Judge sends to Accused when evidence insufficient
    accused_history: List[str]      # all Accused testimonies this session (also Redis-persisted)
    debate_round: int               # how many Judge→Accused rounds have run (max 2)
    judge_verdict: dict             # final {decision, laws_applied, confidence, explanation}
