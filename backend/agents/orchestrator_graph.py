from langgraph.graph import StateGraph, START, END
from state import AgentState


# --- Mock nodes (real logic comes in Sprints 3-6) ---

def evidence_analyzer(state: AgentState) -> dict:
    print("evidence_analyzer: Done.")
    return {}


def prosecutor(state: AgentState) -> dict:
    print("prosecutor: Done.")
    return {"prosecution_args": "prosecutor done"}


def defense(state: AgentState) -> dict:
    print("defense: Done.")
    return {"defense_args": "defense done"}


def judge(state: AgentState) -> dict:
    print("judge: Done.")
    return {"judge_verdict": {"verdict": "guilty"}}


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("evidence_analyzer", evidence_analyzer)
    graph.add_node("prosecutor", prosecutor)
    graph.add_node("defense", defense)
    graph.add_node("judge", judge)

    graph.add_edge(START, "evidence_analyzer")
    graph.add_edge("evidence_analyzer", "prosecutor")
    graph.add_edge("evidence_analyzer", "defense")
    graph.add_edge("prosecutor", "judge")
    graph.add_edge("defense", "judge")
    graph.add_edge("judge", END)

    return graph.compile()


if __name__ == "__main__":
    app = build_graph()

    dummy_state: AgentState = {
        "session_id": "test-session-001",
        "user_query": "Theft of a bicycle in a public street",
        "structured_facts": {},
        "prosecution_args": "",
        "defense_args": "",
        "judge_verdict": {},
        "accused_history": [],
    }

    result = app.invoke(dummy_state)
    print("\nFinal state:")
    print(result)
