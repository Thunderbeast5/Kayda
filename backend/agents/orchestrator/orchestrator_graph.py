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
      ├─ "needs_accused" → accused → judge_score   (loop, max configurable rounds)
      └─ "verdict"       → judge_verdict
  → END
"""

import sys
import json
import contextvars
from pathlib import Path
from typing import Callable, Optional

# Ensure paths for backend, agents, and prosecutor are accessible
_backend_dir = Path(__file__).resolve().parent.parent.parent
_mootcourt_root = _backend_dir.parent
_prosecutor_dir = _backend_dir / "prosecutor"
_agents_dir = _backend_dir / "agents"

for _p in [str(_prosecutor_dir), str(_backend_dir), str(_agents_dir), str(_mootcourt_root)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from langgraph.graph import StateGraph, START, END

from config.state import AgentState
from backend.agents.evidence.evidence_analyzer import analyze_evidence, build_session_id, extract_facts
from backend.agents.lexigraph.lexigraph import lexigraph_node
from backend.agents.defense.defense import DefenseAgent
from backend.agents.judge.judge import judge_score_node, judge_verdict_node, should_ask_accused
from backend.agents.accused.accused import accused_node
from prosecutor_agent import ProsecutorAgent
from lexigraph_agent import LexiGraphAgent

# Context variable for live stage progress reporting (used by async job store & API)
current_stage_callback = contextvars.ContextVar("current_stage_callback", default=None)


def notify_stage(stage_name: str, message: str = "") -> None:
    """Notify the active callback of a stage transition."""
    cb = current_stage_callback.get()
    if cb:
        try:
            cb(stage_name, message)
        except Exception:
            pass


# ── Singleton agents ──────────────────────────────────────────────────────────
_defense_agent = DefenseAgent()
_prosecutor_agent = None


def get_prosecutor_agent() -> ProsecutorAgent:
    global _prosecutor_agent
    if _prosecutor_agent is None:
        lexi_agent = LexiGraphAgent()
        _prosecutor_agent = ProsecutorAgent(lexigraph_agent=lexi_agent)
    return _prosecutor_agent


# ── Node functions ────────────────────────────────────────────────────────────

def evidence_analyzer_node(state: AgentState) -> dict:
    print("\n" + "=" * 65)
    print("[Orchestrator] ▶ Stage 1/5: EVIDENCE ANALYZER")
    print("=" * 65)
    notify_stage("evidence_analyzer", "Extracting structured facts from case evidence...")

    user_query = state["user_query"]
    query_path = Path(user_query) if len(user_query) < 512 else None
    if query_path and query_path.exists() and query_path.is_file():
        facts = analyze_evidence(state["session_id"], user_query)
        print("[Orchestrator] evidence_analyzer: extracted facts from file.")
    else:
        facts = extract_facts(user_query)
        print("[Orchestrator] evidence_analyzer: extracted facts from raw text.")

    return {"structured_facts": facts}


def orchestrator_lexigraph_node(state: AgentState) -> dict:
    print("\n" + "=" * 65)
    print("[Orchestrator] ▶ Stage 2/5: LEXIGRAPH LEGAL RETRIEVAL")
    print("=" * 65)
    notify_stage("lexigraph", "Retrieving applicable statutes and precedents from Neo4j & Pinecone...")

    updated_state = lexigraph_node(state)
    relevant_laws = updated_state.get("relevant_laws") or []
    lexigraph_result = updated_state.get("lexigraph_result") or {}
    print(f"[Orchestrator] LexiGraph retrieved {len(relevant_laws)} verified statutory provisions.")

    return {
        "relevant_laws": relevant_laws,
        "lexigraph_result": lexigraph_result,
    }


def prosecutor_node(state: AgentState) -> dict:
    print("\n" + "-" * 50)
    print("[Orchestrator] ▶ Stage 3/5: ADVOCACY (Prosecution Branch)")
    print("-" * 50)
    notify_stage("prosecution_defense", "Prosecution formulating legal charges and arguments...")

    facts = state.get("structured_facts") or {}
    if isinstance(facts, dict) and facts:
        case_facts = json.dumps(facts, indent=2)
    elif isinstance(facts, str) and facts.strip():
        case_facts = facts
    else:
        case_facts = state.get("user_query", "")

    prosecutor = get_prosecutor_agent()
    turn_result = prosecutor.generate_turn(case_facts=case_facts, phase="opening")

    sections = []
    if turn_result.theory_of_case:
        sections.append(f"THEORY OF THE CASE:\n{turn_result.theory_of_case}")
    if turn_result.statutory_basis:
        sections.append(f"STATUTORY BASIS:\n{turn_result.statutory_basis}")
    if turn_result.precedent_support:
        sections.append(f"PRECEDENT SUPPORT:\n{turn_result.precedent_support}")
    if turn_result.legal_principles:
        sections.append(f"LEGAL PRINCIPLES:\n{turn_result.legal_principles}")
    if turn_result.application_to_facts:
        sections.append(f"APPLICATION TO FACTS:\n{turn_result.application_to_facts}")
    if turn_result.spoken_argument:
        sections.append(f"COURTROOM SUBMISSION:\n{turn_result.spoken_argument}")

    prosecution_args = "\n\n".join(sections) if sections else (turn_result.spoken_argument or "")
    print("[Orchestrator] prosecutor: argument generation complete.")
    return {"prosecution_args": prosecution_args}


def defense_node(state: AgentState) -> dict:
    print("\n" + "-" * 50)
    print("[Orchestrator] ▶ Stage 3/5: ADVOCACY (Defense Branch)")
    print("-" * 50)
    notify_stage("prosecution_defense", "Defense developing theory and identifying evidentiary weaknesses...")

    args = _defense_agent.generate(
        structured_facts      = state.get("structured_facts", {}),
        lexigraph_result      = state.get("lexigraph_result", {}),
        prosecution_arguments = state.get("prosecution_args", ""),
    )
    print("[Orchestrator] defense: argument generation complete.")
    return {"defense_args": args}


def orchestrator_judge_score_node(state: AgentState) -> dict:
    print("\n" + "=" * 65)
    print("[Orchestrator] ▶ Stage 4/5: JUDICIAL EVALUATION & SCORING")
    print("=" * 65)
    notify_stage("judge_scoring", "Evaluating legal validity, evidence linkage, and logical coherence...")

    return judge_score_node(state)


def orchestrator_accused_node(state: AgentState) -> dict:
    round_num = state.get("debate_round", 0) + 1
    print("\n" + "=" * 65)
    print(f"[Orchestrator] ▶ Stage 4b: ACCUSED CLARIFICATION (Round {round_num})")
    print("=" * 65)
    notify_stage("accused_testimony", f"Court questioning Accused for clarification (Round {round_num})...")

    updated_state = accused_node(state)
    return {
        "accused_history": updated_state.get("accused_history", []),
        "debate_round": updated_state.get("debate_round", round_num),
        "judge_question": "",
    }


def orchestrator_judge_verdict_node(state: AgentState) -> dict:
    print("\n" + "=" * 65)
    print("[Orchestrator] ▶ Stage 5/5: FINAL JUDICIAL VERDICT")
    print("=" * 65)
    notify_stage("judge_verdict", "Deliberating and delivering final judgment and legal reasoning...")

    return judge_verdict_node(state)


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph():
    """Compile and return the LangGraph StateGraph state machine."""
    graph = StateGraph(AgentState)

    # ── nodes ──────────────────────────────────────────────────────────────
    graph.add_node("evidence_analyzer", evidence_analyzer_node)
    graph.add_node("lexigraph",         orchestrator_lexigraph_node)
    graph.add_node("prosecutor",        prosecutor_node)
    graph.add_node("defense",           defense_node)
    graph.add_node("judge_score",       orchestrator_judge_score_node)
    graph.add_node("accused",           orchestrator_accused_node)
    graph.add_node("judge_verdict",     orchestrator_judge_verdict_node)

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


# ── Reusable Orchestrator runner ──────────────────────────────────────────────

def run_orchestrator(
    query: str,
    session_id: Optional[str] = None,
    on_stage: Optional[Callable[[str, str], None]] = None,
) -> dict:
    """
    Central production entry point to run the full MootCourt LangGraph
    orchestration pipeline.
    """
    clean_query = (query or "").strip()
    if not clean_query:
        raise ValueError("Case query cannot be empty.")

    if not session_id:
        session_id = build_session_id(clean_query)

    initial_state: AgentState = {
        "session_id":       session_id,
        "user_query":       clean_query,
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

    graph = build_graph()

    token = current_stage_callback.set(on_stage)
    try:
        print("\n" + "█" * 70)
        print(f"[Orchestrator] STARTING MOOT COURT ORCHESTRATION — Session: {session_id[:32]}...")
        print("█" * 70)
        result = graph.invoke(initial_state)
        print("\n" + "█" * 70)
        print("[Orchestrator] ORCHESTRATION PIPELINE COMPLETE")
        print("█" * 70 + "\n")
        return result
    finally:
        current_stage_callback.reset(token)


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_query = "The accused stabbed the victim with a knife near the railway station. Two witnesses saw the incident."
    res = run_orchestrator(test_query)
    verdict = res.get("judge_verdict", {})
    print(f"Decision: {verdict.get('decision')}")
    print(f"Laws: {verdict.get('laws_applied')}")

