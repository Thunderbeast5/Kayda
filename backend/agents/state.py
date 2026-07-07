from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph


class AgentState(TypedDict):
    session_id: str
    user_query: str
    structured_facts: dict
    prosecution_args: str
    defense_args: str
    judge_verdict: dict
    accused_history: List[str]
