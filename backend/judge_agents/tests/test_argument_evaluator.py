"""
Unit tests for ArgumentEvaluator.
Run: python -m pytest backend/judge_agents/tests/test_argument_evaluator.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from judge_agents.services.argument_evaluator import ArgumentEvaluator

_evaluator = ArgumentEvaluator()


def _make_scoring_output(
    def_lv=7, def_el=6, def_lc=8,
    pro_lv=8, pro_el=7, pro_lc=7,
    sufficient="YES",
    questions="",
    new_issues="NONE",
):
    return f"""
DEFENCE SCORES:
Legal Validity: {def_lv}
Evidence Linkage: {def_el}
Logic Coherence: {def_lc}

PROSECUTION SCORES:
Legal Validity: {pro_lv}
Evidence Linkage: {pro_el}
Logic Coherence: {pro_lc}

SUFFICIENCY: {sufficient}

QUESTIONS (only if SUFFICIENCY is NO — list up to 3, one per line):
{questions}

NEW LEGAL ISSUES DETECTED (list any sections/acts raised in arguments but NOT in APPLICABLE LAW above, one per line, or write NONE):
{new_issues}
"""


class TestArgumentEvaluator:

    def test_scores_parsed_correctly(self):
        output = _make_scoring_output(def_lv=7, def_el=6, def_lc=8, pro_lv=8, pro_el=7, pro_lc=7)
        evaluation, _, _, _ = _evaluator.parse(output)
        assert evaluation.defence_score.legal_validity == 7
        assert evaluation.defence_score.evidence_linkage == 6
        assert evaluation.defence_score.logic_coherence == 8
        assert evaluation.defence_score.total == 21
        assert evaluation.prosecution_score.legal_validity == 8
        assert evaluation.prosecution_score.total == 22

    def test_sufficient_yes_returns_no_questions(self):
        output = _make_scoring_output(sufficient="YES")
        _, is_sufficient, raw_questions, _ = _evaluator.parse(output)
        assert is_sufficient is True
        assert raw_questions == []

    def test_sufficient_no_returns_questions(self):
        q_block = (
            "TARGET: IO Agent | ISSUE: Weapon recovery | "
            "QUESTION: Is custodial interrogation required to recover the weapon?"
        )
        output = _make_scoring_output(sufficient="NO", questions=q_block)
        _, is_sufficient, raw_questions, _ = _evaluator.parse(output)
        assert is_sufficient is False
        assert len(raw_questions) == 1
        assert raw_questions[0]["target"] == "IO Agent"
        assert "weapon" in raw_questions[0]["question"].lower()

    def test_new_issues_none_returns_empty(self):
        output = _make_scoring_output(new_issues="NONE")
        _, _, _, new_issues = _evaluator.parse(output)
        assert new_issues == []

    def test_new_issues_parsed(self):
        output = _make_scoring_output(new_issues="NDPS Section 37\nBNS 115")
        _, _, _, new_issues = _evaluator.parse(output)
        assert len(new_issues) == 2
        assert "NDPS Section 37" in new_issues

    def test_scores_clamped_to_0_10(self):
        output = _make_scoring_output(def_lv=15, pro_lv=-3)
        evaluation, _, _, _ = _evaluator.parse(output)
        assert evaluation.defence_score.legal_validity == 10
        assert evaluation.prosecution_score.legal_validity == 0

    def test_fallback_on_missing_scores(self):
        # No scores, no SUFFICIENCY line → numeric fallback (0 < 15) → insufficient
        output = "NEW LEGAL ISSUES DETECTED:\nNONE"
        evaluation, is_sufficient, _, _ = _evaluator.parse(output)
        assert evaluation.defence_score.total == 0
        assert evaluation.prosecution_score.total == 0
        assert is_sufficient is False

    def test_explicit_sufficiency_yes_overrides_threshold(self):
        # SUFFICIENCY: YES even with zero scores → sufficient (LLM override)
        output = "SUFFICIENCY: YES\nNEW LEGAL ISSUES DETECTED:\nNONE"
        evaluation, is_sufficient, _, _ = _evaluator.parse(output)
        assert is_sufficient is True

    def test_multiple_questions_parsed(self):
        q_block = (
            "TARGET: Defence | ISSUE: Mens rea | QUESTION: Did accused intend to cause grievous hurt?\n"
            "TARGET: IO Agent | ISSUE: Recovery | QUESTION: Is weapon recovery pending?\n"
        )
        output = _make_scoring_output(sufficient="NO", questions=q_block)
        _, _, raw_questions, _ = _evaluator.parse(output)
        assert len(raw_questions) == 2
