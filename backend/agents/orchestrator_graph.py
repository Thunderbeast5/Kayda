"""
MootCourt Orchestrator — LangGraph state machine

Node pipeline
-------------
START
  → evidence_analyzer      (OCR + LLM fact extraction)
  → lexigraph              (Neo4j + Pinecone law retrieval)
  → prosecutor             (prosecution arguments)        ─┐
  → defense                (defense arguments)            ─┤ parallel
  → judge_score            (score both, may raise question)
      ├─ "needs_accused" → accused → judge_score   (loop, max 2 rounds)
      └─ "verdict"       → judge_verdict
  → END
"""

from langgraph.graph import StateGraph, START, END

from state            import AgentState
from evidence_analyzer import analyze_evidence, build_session_id
from lexigraph        import lexigraph_node
from defense          import DefenseAgent
from judge            import judge_score_node, judge_verdict_node, should_ask_accused
from accused          import accused_node

# ── Singleton agents ──────────────────────────────────────────────────────────
_defense_agent = DefenseAgent()


# ── Node functions ────────────────────────────────────────────────────────────

def evidence_analyzer_node(state: AgentState) -> AgentState:
    facts = analyze_evidence(state["session_id"], state["user_query"])
    state["structured_facts"] = facts
    print("[Orchestrator] evidence_analyzer: done.")
    return state


def prosecutor_node(state: AgentState) -> dict:
    # TODO Sprint 5: replace stub with real prosecutor.py
    # For now returns a placeholder so the rest of the graph can run.
    print("[Orchestrator] prosecutor: stub — replace with prosecutor.py")
    return {"prosecution_args": "Prosecution stub: accused committed the offence per IPC 379."}


def defense_node(state: AgentState) -> dict:
    args = _defense_agent.generate(
        structured_facts     = state["structured_facts"],
        lexigraph_result     = state["lexigraph_result"],
        prosecution_arguments = state["prosecution_args"],
    )
    print("[Orchestrator] defense: done.")
    return {"defense_args": args}


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(AgentState)

    # ── nodes ──────────────────────────────────────────────────────────────
    graph.add_node("evidence_analyzer", evidence_analyzer_node)
    graph.add_node("lexigraph",         lexigraph_node)
    graph.add_node("prosecutor",        prosecutor_node)
    graph.add_node("defense",           defense_node)
    graph.add_node("judge_score",       judge_score_node)
    graph.add_node("accused",           accused_node)
    graph.add_node("judge_verdict",     judge_verdict_node)

    # ── static edges ───────────────────────────────────────────────────────
    graph.add_edge(START,               "evidence_analyzer")
    graph.add_edge("evidence_analyzer", "lexigraph")
    graph.add_edge("lexigraph",         "prosecutor")
    graph.add_edge("lexigraph",         "defense")
    graph.add_edge("prosecutor",        "judge_score")
    graph.add_edge("defense",           "judge_score")
    graph.add_edge("accused",           "judge_score")    # loops back after testimony
    graph.add_edge("judge_verdict",     END)

    # ── conditional edge: judge_score → accused  OR  judge_verdict ─────────
    graph.add_conditional_edges(
        "judge_score",
        should_ask_accused,          # returns "needs_accused" or "verdict"
        {
            "needs_accused": "accused",
            "verdict":       "judge_verdict",
        },
    )

    return graph.compile()


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = build_graph()

    file_path  = "../test_fir.pdf"
    session_id = build_session_id(file_path)
    print(f"Session: {session_id}\n")

    initial_state: AgentState = {
        "session_id":       session_id,
        "user_query":       file_path,
        "structured_facts": {},
        "relevant_laws":    [],
        "lexigraph_result": {},
        "prosecution_args": "",
        "defense_args":     "",
        "judge_scores":     {},
        "judge_question":   "",
        "accused_history":  [],
        "debate_round":     0,
        "judge_verdict":    {},
    }

    result = app.invoke(initial_state)

    print("\n" + "=" * 70)
    print("FINAL STATE")
    print("=" * 70)
    verdict = result.get("judge_verdict", {})
    print(f"Decision:   {verdict.get('decision', 'N/A')}")
    print(f"Confidence: {verdict.get('confidence', 'N/A')}%")
    print(f"Laws:       {verdict.get('laws_applied', [])}")
    print(f"\nExplanation:\n{verdict.get('explanation', '')}")
