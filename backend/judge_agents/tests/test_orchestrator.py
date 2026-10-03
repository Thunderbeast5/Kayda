"""
Phase 4 tests — AI Courtroom Orchestrator
Tests the full hearing graph without any LLM calls.
All LLM-dependent nodes are patched with deterministic stubs.

Run: python -m pytest tests/test_orchestrator.py -v
"""
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from judge_agents.orchestrator import (
    build_hearing_graph,
    run_hearing,
    hearing_start_node,
    defence_turn_node,
    prosecution_turn_node,
    io_turn_node,
    question_routing_node,
    dynamic_retrieval_node,
    legal_verification_node,
    route_after_score,
)
from judge_agents.courtroom_memory import get_memory, clear_memory, CourtRoomStateMemory
from judge_agents.judge_agent import _get_judge


# ── Shared fixtures ───────────────────────────────────────────────────────────

def _make_state(case_id: str = "ORCH_TEST_001") -> dict:
    return {
        "session_id": case_id,
        "structured_case_context": {
            "session_id": case_id,
            "who": {"complainant": "Ramesh", "accused": ["Suresh"], "victims": ["Ramesh"]},
            "incident": {"summary": "Assault with iron rod", "date": "01/08/2026",
                         "time": "21:00", "place": "Pune, Maharashtra"},
            "sections": ["BNS 117"],
        },
        "evidence_context": {
            "weapon": "Iron rod",
            "injuries": "Fracture",
            "evidence_strength": "Medium",
            "contradictions": [],
            "missing_evidence": [],
        },
        "legal_context_package": {
            "recommended_sections": [
                {"section": "BNS 117", "title": "Grievous hurt", "confidence": 0.91},
            ],
            "supporting_articles": ["Article 21"],
            "pipeline_confidence": 0.88,
        },
        "precedent_context": {
            "similar_cases": [
                {"case_name": "Gurbaksh Singh Sibbia v. State of Punjab",
                 "citation": "1980 AIR 1632"},
            ]
        },
        "bail_assessment_report": {
            "gravity_of_offence": "Medium", "flight_risk": "Low",
            "custodial_need": "No", "witness_tampering_risk": "Low",
            "antecedents": "None",
            "mitigating_factors": ["No prior record"], "aggravating_factors": ["Weapon used"],
        },
        "defence_arguments": (
            "1. No prior criminal record.\n"
            "2. Permanent resident — no flight risk.\n"
            "3. No custodial interrogation required.\n"
            "4. BNS 117 intent not established.\n"
            "5. Article 21 protects liberty."
        ),
        "prosecution_arguments": (
            "1. Iron rod — dangerous weapon.\n"
            "2. Grievous hurt proved by medical evidence.\n"
            "3. Custodial remand needed for weapon seizure.\n"
            "4. Witness tampering risk."
        ),
        "investigation_report": (
            "FIR registered 01/08/2026. Accused not arrested. "
            "Iron rod not seized. Medical report filed."
        ),
        "defence_final_submission": "We request bail be granted with conditions.",
        "prosecution_final_submission": "State opposes bail.",
        "courtroom_state_memory": [],
        "judge_evaluation": {},
        "judge_questions": [],
        "judge_new_issues": [],
        "judge_debate_round": 0,
        "judge_findings": {},
    }


# ── Stub for LLM scoring output ───────────────────────────────────────────────

_STUB_SCORING_OUTPUT = """
DEFENCE SCORES:
Legal Validity: 7
Evidence Linkage: 6
Logic Coherence: 8

PROSECUTION SCORES:
Legal Validity: 8
Evidence Linkage: 7
Logic Coherence: 7

SUFFICIENCY: YES

QUESTIONS (only if SUFFICIENCY is NO — list up to 3, one per line):

NEW LEGAL ISSUES DETECTED (list any sections/acts raised in arguments but NOT in APPLICABLE LAW above, one per line, or write NONE):
NONE
"""

def _make_findings_stub(case_id: str = "E2E_HEARING_001") -> str:
    return json.dumps({
        "case_id": case_id,
        "hearing_date": "07/08/2026",
        "judge_name": "AI Judge",
        "applicant": "Suresh",
        "respondent": "State of Maharashtra",
        "sections_applied": ["BNS 117"],
        "constitutional_articles_applied": ["Article 21"],
        "precedents_applied": [
            {"case_name": "Gurbaksh Singh Sibbia v. State of Punjab",
             "citation": "1980 AIR 1632", "principle_applied": "Bail with conditions"}
        ],
        "evidence_evaluation": {
            "strength": "Medium", "key_evidence": ["Medical report"],
            "contradictions_noted": [], "missing_evidence": [],
        },
        "bail_factor_analysis": {
            "gravity_of_offence": "Medium", "flight_risk": "Low",
            "custodial_need": "No", "witness_tampering_risk": "Low",
            "antecedents": "None", "mitigating_factors": ["No prior record"],
            "aggravating_factors": ["Weapon used"],
        },
        "argument_evaluation": {
            "defence_score":     {"legal_validity": 7, "evidence_linkage": 6, "logic_coherence": 8, "total": 21},
            "prosecution_score": {"legal_validity": 8, "evidence_linkage": 7, "logic_coherence": 7, "total": 22},
        },
        "judicial_analysis": "Having heard both parties, this Court finds that bail may be granted with conditions.",
        "preliminary_finding": "Bail Likely Granted",
        "confidence": 72,
        "conditions_if_granted": ["Surrender passport", "Report weekly"],
        "questions_asked": [],
        "dynamic_retrieval_triggered": False,
        "new_issues_identified": [],
    })

_STUB_FINDINGS_OUTPUT = _make_findings_stub("ORCH_TEST_001")


def _stub_llm_response(content: str):
    mock = MagicMock()
    mock.content = content
    return mock


# ── Individual node tests ─────────────────────────────────────────────────────

class TestOrchestratorNodes:

    def setup_method(self):
        """Clear memory and judge state before each test."""
        clear_memory("ORCH_TEST_001")
        judge = _get_judge()
        judge._contexts.pop("ORCH_TEST_001", None)
        judge._live_legal_pkg.pop("ORCH_TEST_001", None)
        judge._live_prec_ctx.pop("ORCH_TEST_001", None)

    def test_hearing_start_node_initialises_memory(self):
        state = _make_state()
        result = hearing_start_node(state)
        memory = get_memory("ORCH_TEST_001")
        assert memory.turn_count() >= 1  # System turn written
        assert isinstance(result.get("courtroom_state_memory"), list)

    def test_defence_turn_passes_through_state(self):
        state = _make_state()
        hearing_start_node(state)
        result = defence_turn_node(state)
        # Phase 4: pass-through — state unchanged
        assert result["defence_arguments"] == state["defence_arguments"]

    def test_prosecution_turn_passes_through_state(self):
        state = _make_state()
        hearing_start_node(state)
        result = prosecution_turn_node(state)
        assert result["prosecution_arguments"] == state["prosecution_arguments"]

    def test_io_turn_passes_through_state(self):
        state = _make_state()
        hearing_start_node(state)
        result = io_turn_node(state)
        assert result["investigation_report"] == state["investigation_report"]

    def test_dynamic_retrieval_node_clears_issues(self):
        state = _make_state()
        state["judge_new_issues"] = ["NDPS 37", "Article 22"]
        hearing_start_node(state)
        result = dynamic_retrieval_node(state)
        assert result["judge_new_issues"] == []

    def test_legal_verification_passes_valid_findings(self):
        state = _make_state()
        state["judge_findings"] = json.loads(_STUB_FINDINGS_OUTPUT)
        hearing_start_node(state)
        result = legal_verification_node(state)
        assert result["verification_status"] == "PASSED"
        assert result["verification_issues"] == []

    def test_legal_verification_catches_empty_analysis(self):
        state = _make_state()
        bad_findings = json.loads(_STUB_FINDINGS_OUTPUT)
        bad_findings["judicial_analysis"] = ""
        state["judge_findings"] = bad_findings
        hearing_start_node(state)
        result = legal_verification_node(state)
        assert result["verification_status"] == "ISSUES_FOUND"
        assert any("judicial_analysis" in i for i in result["verification_issues"])

    def test_legal_verification_catches_invalid_finding(self):
        state = _make_state()
        bad_findings = json.loads(_STUB_FINDINGS_OUTPUT)
        bad_findings["preliminary_finding"] = "Unknown Value"
        state["judge_findings"] = bad_findings
        hearing_start_node(state)
        result = legal_verification_node(state)
        assert result["verification_status"] == "ISSUES_FOUND"

    def test_question_routing_node_answers_questions(self):
        state = _make_state()
        state["judge_questions"] = [
            {"target": "IO Agent", "issue": "seizure", "question": "Is weapon seized?",
             "answer": None, "round": 1},
        ]
        hearing_start_node(state)
        result = question_routing_node(state)
        answered = result["judge_questions"]
        assert len(answered) == 1
        assert answered[0]["answer"] is not None


class TestRouteAfterScore:

    def test_routes_to_questions_when_questions_present(self):
        state = {
            "judge_questions": [{"target": "IO", "question": "Q?", "answer": None}],
            "judge_new_issues": [],
            "judge_debate_round": 1,
        }
        assert route_after_score(state) == "needs_questions"

    def test_routes_to_retrieval_when_issues_present(self):
        state = {
            "judge_questions": [],
            "judge_new_issues": ["NDPS 37"],
            "judge_debate_round": 1,
        }
        assert route_after_score(state) == "needs_retrieval"

    def test_routes_to_verdict_when_clean(self):
        state = {
            "judge_questions": [],
            "judge_new_issues": [],
            "judge_debate_round": 1,
        }
        assert route_after_score(state) == "verdict"

    def test_routes_to_verdict_when_max_rounds_exceeded(self):
        state = {
            "judge_questions": [{"q": "still pending"}],
            "judge_new_issues": ["NDPS 37"],
            "judge_debate_round": 3,  # > MAX_DEBATE_ROUNDS
        }
        assert route_after_score(state) == "verdict"


# ── Full graph end-to-end test (LLM patched) ─────────────────────────────────

class TestFullHearingGraph:

    def setup_method(self):
        clear_memory("E2E_HEARING_001")
        judge = _get_judge()
        judge._contexts.pop("E2E_HEARING_001", None)
        judge._live_legal_pkg.pop("E2E_HEARING_001", None)
        judge._live_prec_ctx.pop("E2E_HEARING_001", None)

    def test_full_hearing_completes_without_llm(self):
        state = _make_state("E2E_HEARING_001")
        with patch(
            "judge_agents.judge_agent.BailJudgeAgent._call_llm",
            side_effect=[_STUB_SCORING_OUTPUT, _make_findings_stub("E2E_HEARING_001")],
        ):
            result = run_hearing(state)
        assert result.get("judge_findings")
        assert result["judge_findings"].get("preliminary_finding") in {
            "Bail Likely Granted", "Bail Likely Rejected", "Inconclusive"
        }
        assert result.get("verification_status") == "PASSED"
        assert len(result.get("courtroom_state_memory", [])) > 0

    def test_full_hearing_memory_has_all_speakers(self):
        state = _make_state("E2E_HEARING_001")
        with patch(
            "judge_agents.judge_agent.BailJudgeAgent._call_llm",
            side_effect=[_STUB_SCORING_OUTPUT, _make_findings_stub("E2E_HEARING_001")],
        ):
            result = run_hearing(state)
        speakers = {t["speaker"] for t in result["courtroom_state_memory"]}
        assert "Defence"     in speakers
        assert "Prosecution" in speakers
        assert "IO Agent"    in speakers

    def test_full_hearing_findings_sections_not_hallucinated(self):
        state = _make_state("E2E_HEARING_001")
        with patch(
            "judge_agents.judge_agent.BailJudgeAgent._call_llm",
            side_effect=[_STUB_SCORING_OUTPUT, _make_findings_stub("E2E_HEARING_001")],
        ):
            result = run_hearing(state)
        findings = result["judge_findings"]
        allowed  = {"BNS 117", "BNS_117", "ARTICLE_21", "Article 21"}
        for sec in findings.get("sections_applied", []):
            assert sec in allowed, f"Hallucinated section: {sec}"

    def test_full_hearing_state_memory_serialised(self):
        """courtroom_state_memory in final state must be a list of dicts."""
        state = _make_state("E2E_HEARING_001")

        with patch(
            "judge_agents.judge_agent.BailJudgeAgent._call_llm",
            side_effect=[_STUB_SCORING_OUTPUT, _make_findings_stub("E2E_HEARING_001")],
        ):
            result = run_hearing(state)

        mem = result.get("courtroom_state_memory", [])
        assert isinstance(mem, list)
        for turn in mem:
            assert isinstance(turn, dict)
            assert "speaker" in turn
            assert "content" in turn

    def test_full_hearing_with_question_loop(self):
        """
        Hearing where scoring returns SUFFICIENCY:NO → questions → re-score → verdict.
        LLM returns insufficient first, then sufficient on second call.
        """
        case_id = "E2E_QUESTION_LOOP"
        clear_memory(case_id)
        judge = _get_judge()
        judge._contexts.pop(case_id, None)
        judge._live_legal_pkg.pop(case_id, None)
        judge._live_prec_ctx.pop(case_id, None)

        scoring_with_question = """
DEFENCE SCORES:
Legal Validity: 5
Evidence Linkage: 4
Logic Coherence: 5

PROSECUTION SCORES:
Legal Validity: 4
Evidence Linkage: 3
Logic Coherence: 4

SUFFICIENCY: NO

QUESTIONS (only if SUFFICIENCY is NO — list up to 3, one per line):
TARGET: IO Agent | ISSUE: weapon seizure | QUESTION: Has the iron rod been seized?

NEW LEGAL ISSUES DETECTED:
NONE
"""
        scoring_sufficient = _STUB_SCORING_OUTPUT  # returns YES on second call

        state = _make_state(case_id)

        with patch(
            "judge_agents.judge_agent.BailJudgeAgent._call_llm",
            side_effect=[
                scoring_with_question,               # first score → questions
                scoring_sufficient,                  # re-score after answers → sufficient
                _make_findings_stub(case_id),        # findings
            ],
        ):
            result = run_hearing(state)

        assert result.get("judge_findings"), "Findings must be present after question loop"
        assert result.get("verification_status") == "PASSED"
        # Memory must have a question turn
        memory = get_memory(case_id)
        q_turns = [t for t in memory.get_history() if t.turn_type == "question"]
        assert len(q_turns) >= 1

    def test_verification_catches_none_confidence(self):
        """legal_verification_node must handle None confidence without crashing."""
        state = _make_state("ORCH_TEST_001")
        bad_findings = json.loads(_STUB_FINDINGS_OUTPUT)
        bad_findings["confidence"] = None
        state["judge_findings"] = bad_findings
        hearing_start_node(state)
        result = legal_verification_node(state)
        # Should not raise — should flag as issue
        assert result["verification_status"] == "ISSUES_FOUND"
