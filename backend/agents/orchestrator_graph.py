from langgraph.graph import StateGraph, START, END
from state import AgentState
from evidence_analyzer import analyze_evidence, build_session_id
from lexigraph import lexigraph_node


# ── Agent nodes ───────────────────────────────────────────────────────────────

def evidence_analyzer(state: AgentState) -> AgentState:
    # NOTE: user_query must be a file path (PDF/image) for this to work.
    facts = analyze_evidence(state["session_id"], state["user_query"])
    state["structured_facts"] = facts
    print("evidence_analyzer: Done.")
    return state


def prosecutor(state: AgentState) -> dict:
    print("prosecutor: Done.")
    return {"prosecution_args": "prosecutor done"}


def defense(state: AgentState) -> dict:
    print("defense: Done.")
    return {"defense_args": "defense done"}


def judge(state: AgentState) -> dict:
    print("judge: Done.")
    return {"judge_verdict": {"verdict": "guilty"}}


# ── Graph definition ──────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("evidence_analyzer", evidence_analyzer)
    graph.add_node("lexigraph",         lexigraph_node)     # Sprint 4
    graph.add_node("prosecutor",        prosecutor)
    graph.add_node("defense",           defense)
    graph.add_node("judge",             judge)

    graph.add_edge(START,              "evidence_analyzer")
    graph.add_edge("evidence_analyzer", "lexigraph")        # facts → law retrieval
    graph.add_edge("lexigraph",         "prosecutor")        # laws available to both
    graph.add_edge("lexigraph",         "defense")
    graph.add_edge("prosecutor",        "judge")
    graph.add_edge("defense",           "judge")
    graph.add_edge("judge",             END)

    return graph.compile()


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = build_graph()

    file_path  = "../test_fir.pdf"
    session_id = build_session_id(file_path)
    print(f"Creating new session: {session_id}")

    dummy_state: AgentState = {
        "session_id":       session_id,
        "user_query":       file_path,
        "structured_facts": {},
        "relevant_laws":    [],
        "lexigraph_result": {},
        "prosecution_args": "",
        "defense_args":     "",
        "judge_verdict":    {},
        "accused_history":  [],
    }

    result = app.invoke(dummy_state)
    print("\nFinal state:")
    print(result)
