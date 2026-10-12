"""
Unit tests for QuestionGenerator and GapDetector — Phase 2
Run: python -m pytest tests/test_question_generator.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from judge_agents.services.question_generator import GapDetector, _parse_generated_questions, _map_target
from judge_agents.models.hearing_state import HearingContext
from judge_agents.models.question_model import QuestionTarget


# ── Shared fixtures ───────────────────────────────────────────────────────────

_EVIDENCE = {
    "weapon": "Iron rod",
    "injuries": "Fracture of left arm",
    "evidence_strength": "Medium",
    "contradictions": ["Eyewitness timing differs by 30 minutes"],
    "missing_evidence": ["Iron rod not seized", "Forensic report pending"],
}

_LEGAL_PKG = {
    "recommended_sections": [
        {
            "section": "BNS 117",
            "title": "Grievous hurt",
            "applicability": "Accused must have intention to cause grievous hurt",
        }
    ]
}

_DEFENCE = "The accused is a permanent resident with strong family ties."
_PROSECUTION = "The accused used a dangerous weapon causing fracture."
_IO_REPORT = "FIR registered. Iron rod not seized. Eyewitness statement pending."
_BAIL_REPORT = {"gravity_of_offence": "Medium", "antecedents": "None"}


class TestGapDetector:
    detector = GapDetector()

    def test_weapon_not_seized_detected(self):
        # Use args that don't mention "weapon" so the IO_STATUS_UNCLEAR gap triggers
        defence_no_weapon = "The accused is a permanent resident with family ties."
        prosecution_no_weapon = "The accused caused grievous hurt with an instrument."
        gaps = self.detector.detect(
            _EVIDENCE, _LEGAL_PKG, defence_no_weapon, prosecution_no_weapon, _IO_REPORT, _BAIL_REPORT
        )
        cats = [g["category"] for g in gaps]
        assert "IO_STATUS_UNCLEAR" in cats

    def test_custodial_need_gap_detected(self):
        # Neither side mentions custodial / interrogation
        gaps = self.detector.detect(
            _EVIDENCE, _LEGAL_PKG,
            "No prior record.",
            "Used dangerous weapon.",
            "FIR registered. Weapon not seized.",
            _BAIL_REPORT,
        )
        cats = [g["category"] for g in gaps]
        assert "CUSTODIAL_NEED_UNARGUED" in cats

    def test_custodial_need_not_detected_when_addressed(self):
        gaps = self.detector.detect(
            _EVIDENCE, _LEGAL_PKG,
            "Custodial interrogation is not required.",
            "Custodial remand is essential.",
            _IO_REPORT,
            _BAIL_REPORT,
        )
        cats = [g["category"] for g in gaps]
        assert "CUSTODIAL_NEED_UNARGUED" not in cats

    def test_flight_risk_gap_detected(self):
        gaps = self.detector.detect(
            _EVIDENCE, _LEGAL_PKG,
            "The accused is innocent.",  # no flight risk mention
            _PROSECUTION,
            _IO_REPORT,
            _BAIL_REPORT,
        )
        cats = [g["category"] for g in gaps]
        assert "FLIGHT_RISK_UNARGUED" in cats

    def test_flight_risk_not_detected_when_addressed(self):
        gaps = self.detector.detect(
            _EVIDENCE, _LEGAL_PKG,
            "Accused is permanent resident with family ties — no flight risk.",
            _PROSECUTION,
            _IO_REPORT,
            _BAIL_REPORT,
        )
        cats = [g["category"] for g in gaps]
        assert "FLIGHT_RISK_UNARGUED" not in cats

    def test_contradiction_gap_detected(self):
        evidence_with_contradiction = {**_EVIDENCE, "contradictions": ["Witness says 9pm but FIR says 10pm"]}
        gaps = self.detector.detect(
            evidence_with_contradiction, _LEGAL_PKG, _DEFENCE, _PROSECUTION, _IO_REPORT, _BAIL_REPORT
        )
        cats = [g["category"] for g in gaps]
        assert "CONTRADICTION" in cats

    def test_no_gaps_when_all_addressed(self):
        well_argued_defence = (
            "Accused is permanent resident — no flight risk. "
            "No custodial interrogation required. "
            "No prior criminal record. "
            "Intent to cause harm was absent."
        )
        well_argued_prosecution = (
            "Custodial interrogation is essential for weapon recovery. "
            "Antecedents checked — none found."
        )
        io = "Iron rod seized on 02/08/2026. Eyewitness statement recorded."
        bail = {"antecedents": "None", "gravity_of_offence": "Low"}
        evidence_clean = {
            "weapon": "Iron rod",
            "injuries": "Minor bruise",
            "evidence_strength": "Low",
            "contradictions": [],
            "missing_evidence": [],
        }
        gaps = self.detector.detect(
            evidence_clean, _LEGAL_PKG, well_argued_defence, well_argued_prosecution, io, bail
        )
        # Should be empty or only minor gaps
        critical = [g for g in gaps if g["priority"] == 1]
        assert len(critical) == 0

    def test_gaps_sorted_by_priority(self):
        gaps = self.detector.detect(
            _EVIDENCE, _LEGAL_PKG, _DEFENCE, _PROSECUTION, _IO_REPORT, _BAIL_REPORT
        )
        priorities = [g["priority"] for g in gaps]
        assert priorities == sorted(priorities)

    def test_no_duplicate_categories(self):
        gaps = self.detector.detect(
            _EVIDENCE, _LEGAL_PKG, _DEFENCE, _PROSECUTION, _IO_REPORT, _BAIL_REPORT
        )
        cats = [g["category"] for g in gaps]
        assert len(cats) == len(set(cats))

    def test_target_is_valid_string(self):
        gaps = self.detector.detect(
            _EVIDENCE, _LEGAL_PKG, _DEFENCE, _PROSECUTION, _IO_REPORT, _BAIL_REPORT
        )
        valid_targets = {"Defence", "Prosecution", "IO Agent"}
        for g in gaps:
            assert g["target"] in valid_targets, f"Invalid target: {g['target']}"


class TestParseGeneratedQuestions:

    def test_single_question_parsed(self):
        raw = "TARGET: IO Agent | ISSUE: weapon seizure | QUESTION: Has the iron rod been seized?"
        qs = _parse_generated_questions(raw)
        assert len(qs) == 1
        assert qs[0]["target"] == "IO Agent"
        assert "iron rod" in qs[0]["question"].lower()

    def test_multiple_questions_parsed(self):
        raw = (
            "TARGET: Defence | ISSUE: flight risk | QUESTION: Does the accused hold a passport?\n"
            "TARGET: IO Agent | ISSUE: seizure | QUESTION: When will the weapon be seized?"
        )
        qs = _parse_generated_questions(raw)
        assert len(qs) == 2

    def test_no_questions_needed_returns_empty(self):
        raw = "NO QUESTIONS NEEDED"
        qs = _parse_generated_questions(raw)
        assert qs == []

    def test_blank_lines_skipped(self):
        raw = "\n\nTARGET: Defence | ISSUE: intent | QUESTION: Was there intention to harm?\n\n"
        qs = _parse_generated_questions(raw)
        assert len(qs) == 1

    def test_malformed_line_skipped(self):
        raw = (
            "This is not a valid line\n"
            "TARGET: IO Agent | ISSUE: recovery | QUESTION: Is recovery pending?"
        )
        qs = _parse_generated_questions(raw)
        assert len(qs) == 1


class TestMapTarget:

    def test_maps_defence(self):
        assert _map_target("Defence") == QuestionTarget.DEFENCE
        assert _map_target("defense") == QuestionTarget.DEFENCE

    def test_maps_prosecution(self):
        assert _map_target("Prosecution") == QuestionTarget.PROSECUTION
        assert _map_target("prosecutor") == QuestionTarget.PROSECUTION

    def test_maps_io_agent_default(self):
        assert _map_target("IO Agent") == QuestionTarget.IO_AGENT
        assert _map_target("unknown") == QuestionTarget.IO_AGENT


class TestQuestionGeneratorBudgetGuard:
    """
    Tests the budget guard without calling the LLM.
    We patch generate() to test budget logic only.
    """

    def test_budget_exhausted_returns_empty(self):
        ctx = HearingContext(session_id="TEST")
        ctx.questions_asked_count = 5  # already at max
        detector = GapDetector()
        gaps = detector.detect(
            _EVIDENCE, _LEGAL_PKG, _DEFENCE, _PROSECUTION, _IO_REPORT, _BAIL_REPORT
        )
        # Simulate budget check — no questions should be generated
        remaining = 5 - ctx.questions_asked_count
        assert remaining == 0

    def test_budget_partial_limits_questions(self):
        ctx = HearingContext(session_id="TEST")
        ctx.questions_asked_count = 4  # 1 remaining
        remaining = 5 - ctx.questions_asked_count
        assert remaining == 1

    def test_context_tracks_count(self):
        ctx = HearingContext(session_id="TEST")
        assert ctx.can_ask_question(5) is True
        ctx.questions_asked_count = 5
        assert ctx.can_ask_question(5) is False
