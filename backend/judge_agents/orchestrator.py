"""
AI Courtroom Orchestrator — Phase 4
=====================================
Central controller of the anticipatory bail hearing.

Responsibilities
----------------
- Assigns speaking turns (Defence → Prosecution → IO → Judge)
- Manages the LangGraph state machine connecting all courtroom agents
- Routes state after each Judge scoring pass:
    "needs_questions"  → question-answering sub-graph
    "needs_retrieval"  → Dynamic Retrieval Trigger
    "verdict"          → final findings pass
- Triggers DynamicRetrievalTrigger when Judge detects new issues
- Passes JudicialFindings to Legal Verification Agent stub
- Serialises full CourtRoomStateMemory into LangGraph state

Architecture (JUDGE_AGENT.md §4):
    evidence_analyzer → lexigraph → bail_assessment
            ↓
    orchestrator_start
            ↓
    defence_turn  →  prosecution_turn  →  io_turn
            ↓
    judge_score_node
      ├─ needs_questions → question_routing_node → judge_score_node
      ├─ needs_retrieval → dynamic_retrieval_node → judge_score_node
      └─ verdict → judge_verdict_node
            ↓
    legal_verification_node
            ↓
    END

Design
------
- Each courtroom agent is a stub in Phase 4 (replaced by real agents in Phase 5+)
- Debate engine enforces MAX_DEBATE_ROUNDS
- Full CourtRoomStateMemory maintained across all nodes
- LangGraph state is the single source of truth between nodes
"""

from __future__ import annotations

import json
from typing import Optional

from langgraph.graph import StateGraph, START, END

from .judge_agent import (
    BailJudgeAgent,
    BailHearingState,
    bail_judge_score_node,
    bail_judge_verdict_node,
    should_proceed_to_verdict,
    _deserialise_questions,
    _get_judge,
)
from .courtroom_memory import get_memory, clear_memory
from .dynamic_retrieval import DynamicRetrievalTrigger
from .services.issue_detector import IssueDetector

MAX_DEBATE_ROUNDS = 2


# ── Courtroom agent stubs ──────────────────────────────────────────────────────
# These are replaced by real Defence/Prosecution/IO agents in later phases.
# Each stub reads from state and writes its output back to state.

def defence_turn_node(state: dict) -> dict:
    """
    Defence Agent turn.
    Phase 4: pass-through — arguments already in state from upstream.
    Memory writes happen inside bail_judge_score_node to avoid duplicates.
    Real Defence Agent (Phase 5) generates LLM arguments here.
    """
    round_n = state.get("judge_debate_round", 1)
    print(f"[Orchestrator] Defence turn (round {round_n}) — arguments ready in state.")
    return state


def prosecution_turn_node(state: dict) -> dict:
    """
    Prosecution Agent turn.
    Phase 4: pass-through.
    Real Prosecution Agent (Phase 5) generates LLM arguments here.
    """
    round_n = state.get("judge_debate_round", 1)
    print(f"[Orchestrator] Prosecution turn (round {round_n}) — arguments ready in state.")
    return state


def io_turn_node(state: dict) -> dict:
    """
    Investigating Officer Agent turn.
    Phase 4: pass-through.
    Real IO Agent (Phase 5) generates LLM investigation report here.
    """
    round_n = state.get("judge_debate_round", 1)
    print(f"[Orchestrator] IO Agent turn (round {round_n}) — report ready in state.")
    return state


def question_routing_node(state: dict) -> dict:
    """
    Routes Judge questions to the correct courtroom agent and
    collects answers into state.

    In Phase 4: answers are simulated (empty string if no real agent).
    Real agents answer in Phase 5.
    """
    case_id   = state.get("session_id", "unknown")
    memory    = get_memory(case_id)
    raw_qs    = state.get("judge_questions", [])
    round_n   = state.get("judge_debate_round", 1)

    answered_qs = []
    for i, q in enumerate(raw_qs):
        target   = q.get("target", "IO Agent")
        question = q.get("question", "")
        # Phase 4 stub — real agents answer in Phase 5
        answer   = q.get("answer") or f"(Answer from {target} — pending Phase 5 agent)"
        memory.record_answer(answer, target, i, round_n)
        answered_qs.append({**q, "answer": answer})
        print(f"[Orchestrator] Question answered by {target}: '{question[:60]}...'")

    # Update state with answered questions
    state = {**state, "judge_questions": answered_qs}

    # Transition: AWAITING_ANSWERS → EVALUATING_ARGUMENTS (handled inside ingest_answers)
    judge = _get_judge()
    if case_id in judge._contexts:
        answers = [
            {
                "question_index": i,
                "respondent":     q.get("target", "IO Agent"),
                "answer":         q.get("answer", ""),
                "round":          round_n,
            }
            for i, q in enumerate(answered_qs)
        ]
        judge.ingest_answers(case_id, answers)

    memory_list = memory.to_list()
    return {**state, "courtroom_state_memory": memory_list}


def dynamic_retrieval_node(state: dict) -> dict:
    """
    Dynamic Retrieval node — fires when Judge detects new legal issues.

    Phase 4: no-op retrieval (callback=None).
    Phase 5+: wire in real LexiGraph + Precedent callbacks.
    """
    case_id     = state.get("session_id", "unknown")
    memory      = get_memory(case_id)
    new_issues  = state.get("judge_new_issues", [])
    round_n     = state.get("judge_debate_round", 1)

    print(f"[Orchestrator] Dynamic retrieval triggered for {len(new_issues)} issue(s).")

    # In Phase 4: log to memory and pass through unchanged (no real LexiGraph call)
    memory.add_turn(
        "System", "finding",
        f"[Orchestrator] Dynamic retrieval requested for: {new_issues}. "
        f"Returning unchanged context (Phase 4 no-op).",
        round=round_n,
    )

    # Clear new_issues so we don't loop indefinitely
    return {
        **state,
        "judge_new_issues": [],
        "courtroom_state_memory": memory.to_list(),
    }


def legal_verification_node(state: dict) -> dict:
    """
    Legal Verification Agent — Phase 4 stub.

    Checks performed:
    - judicial_analysis is non-empty string
    - preliminary_finding is one of the three valid values
    - confidence is an integer in range 0-100
    - sections_applied is a list
    """
    case_id  = state.get("session_id", "unknown")
    findings = state.get("judge_findings") or {}
    memory   = get_memory(case_id)

    issues: list[str] = []

    if not str(findings.get("judicial_analysis") or "").strip():
        issues.append("judicial_analysis is empty")

    valid_findings = {"Bail Likely Granted", "Bail Likely Rejected", "Inconclusive"}
    if findings.get("preliminary_finding") not in valid_findings:
        issues.append(f"Invalid preliminary_finding: {findings.get('preliminary_finding')}")

    try:
        raw_conf = findings.get("confidence")
        if raw_conf is None:
            raise ValueError("confidence is None")
        conf = int(raw_conf)
        if not (0 <= conf <= 100):
            issues.append(f"Confidence out of range: {conf}")
    except (TypeError, ValueError) as e:
        issues.append(f"Confidence is not a valid number: {findings.get('confidence')} ({e})")

    if not isinstance(findings.get("sections_applied"), list):
        issues.append("sections_applied is not a list")

    verification_status = "PASSED" if not issues else "ISSUES_FOUND"

    memory.add_turn(
        "System", "finding",
        f"[LegalVerification] Status: {verification_status}. "
        f"Issues: {issues if issues else 'None'}.",
        round=state.get("judge_debate_round", 1),
    )

    print(f"[LegalVerification] {verification_status} — Issues: {issues or 'None'}")

    return {
        **state,
        "verification_status": verification_status,
        "verification_issues": issues,
        "courtroom_state_memory": memory.to_list(),
    }


def hearing_start_node(state: dict) -> dict:
    """
    Orchestrator start — initialises the hearing for the case_id.
    Must be the first node in the graph.
    """
    case_id = state.get("session_id", "unknown")
    judge   = _get_judge()

    if case_id not in judge._contexts:
        judge.start_hearing(case_id)
        print(f"[Orchestrator] Hearing started: {case_id}")
    else:
        print(f"[Orchestrator] Hearing already running: {case_id}")

    memory = get_memory(case_id)
    return {**state, "courtroom_state_memory": memory.to_list()}


# ── Routing function ───────────────────────────────────────────────────────────

def route_after_score(state: dict) -> str:
    """
    Conditional edge after judge_score_node.
    Returns one of: "needs_questions" | "needs_retrieval" | "verdict"
    """
    return should_proceed_to_verdict(state)


# ── Graph builder ──────────────────────────────────────────────────────────────

def build_hearing_graph():
    """
    Build and compile the full anticipatory bail hearing LangGraph.

    Node flow:
      START
        → hearing_start
        → defence_turn
        → prosecution_turn
        → io_turn
        → judge_score          ← can loop back via questions or retrieval
            ├─ needs_questions → question_routing → judge_score
            ├─ needs_retrieval → dynamic_retrieval → judge_score
            └─ verdict         → judge_verdict
                                    → legal_verification
                                        → END

    Returns compiled LangGraph application.
    """
    graph = StateGraph(dict)

    # ── Nodes ──────────────────────────────────────────────────────────────
    graph.add_node("hearing_start",       hearing_start_node)
    graph.add_node("defence_turn",        defence_turn_node)
    graph.add_node("prosecution_turn",    prosecution_turn_node)
    graph.add_node("io_turn",             io_turn_node)
    graph.add_node("judge_score",         bail_judge_score_node)
    graph.add_node("question_routing",    question_routing_node)
    graph.add_node("dynamic_retrieval",   dynamic_retrieval_node)
    graph.add_node("judge_verdict",       bail_judge_verdict_node)
    graph.add_node("legal_verification",  legal_verification_node)

    # ── Static edges ───────────────────────────────────────────────────────
    graph.add_edge(START,             "hearing_start")
    graph.add_edge("hearing_start",   "defence_turn")
    graph.add_edge("defence_turn",    "prosecution_turn")
    graph.add_edge("prosecution_turn","io_turn")
    graph.add_edge("io_turn",         "judge_score")

    # After question routing, go back to judge_score for re-evaluation
    graph.add_edge("question_routing",  "judge_score")
    # After dynamic retrieval, go back to judge_score with updated context
    graph.add_edge("dynamic_retrieval", "judge_score")

    # After verdict, verify
    graph.add_edge("judge_verdict",     "legal_verification")
    graph.add_edge("legal_verification", END)

    # ── Conditional edges ──────────────────────────────────────────────────
    graph.add_conditional_edges(
        "judge_score",
        route_after_score,
        {
            "needs_questions": "question_routing",
            "needs_retrieval": "dynamic_retrieval",
            "verdict":         "judge_verdict",
        },
    )

    return graph.compile()


# ── Convenience runner ─────────────────────────────────────────────────────────

def run_hearing(initial_state: dict) -> dict:
    """
    Run a complete anticipatory bail hearing from initial state.

    Parameters
    ----------
    initial_state : dict matching BailHearingState keys.
                    Must include at minimum:
                    - session_id
                    - structured_case_context
                    - evidence_context
                    - legal_context_package
                    - precedent_context
                    - bail_assessment_report
                    - defence_arguments
                    - prosecution_arguments
                    - investigation_report

    Returns
    -------
    Final state dict with judge_findings, verification_status,
    courtroom_state_memory populated.
    """
    app = build_hearing_graph()
    final_state = app.invoke(initial_state)

    case_id  = initial_state.get("session_id", "unknown")
    findings = final_state.get("judge_findings") or {}

    print("\n" + "=" * 60)
    print("HEARING COMPLETE")
    print("=" * 60)
    print(f"  Case ID          : {case_id}")
    print(f"  Finding          : {findings.get('preliminary_finding', 'N/A')}")
    print(f"  Confidence       : {findings.get('confidence', 'N/A')}%")
    print(f"  Verification     : {final_state.get('verification_status', 'N/A')}")
    print(f"  Memory turns     : {len(final_state.get('courtroom_state_memory', []))}")
    print("=" * 60)

    return final_state
