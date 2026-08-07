"""
Unit tests for CourtRoomStateMemory — Phase 2
Run: python -m pytest tests/test_courtroom_memory.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from judge_agents.courtroom_memory import CourtRoomStateMemory, get_memory, clear_memory


class TestCourtRoomStateMemory:

    def _new(self, case_id="TEST_001"):
        return CourtRoomStateMemory(case_id=case_id)

    def test_add_turn_increases_count(self):
        m = self._new()
        m.add_turn("Defence", "argument", "No prior record.", round=1)
        assert m.turn_count() == 1

    def test_question_index_tracked(self):
        m = self._new()
        m.record_question("Is weapon seized?", "IO Agent", "weapon seizure", round=1)
        assert m.question_count() == 1
        assert len(m.get_unanswered_questions()) == 1

    def test_answer_marks_question_answered(self):
        m = self._new()
        m.record_question("Is weapon seized?", "IO Agent", "weapon seizure", round=1)
        m.record_answer("Weapon not yet seized.", "IO Agent", question_index=0, round=1)
        assert len(m.get_unanswered_questions()) == 0

    def test_multiple_questions_partial_answers(self):
        m = self._new()
        m.record_question("Q1?", "Defence", "gap1", round=1)
        m.record_question("Q2?", "IO Agent", "gap2", round=1)
        m.record_answer("A1.", "Defence", 0, round=1)
        unanswered = m.get_unanswered_questions()
        assert len(unanswered) == 1
        assert unanswered[0].content == "Q2?"

    def test_get_answered_questions_pairs(self):
        m = self._new()
        m.record_question("Q1?", "Defence", "gap1", round=1)
        m.record_answer("A1.", "Defence", 0, round=1)
        pairs = m.get_answered_questions()
        assert len(pairs) == 1
        q, a = pairs[0]
        assert q.content == "Q1?"
        assert a.content == "A1."

    def test_law_extraction_from_content(self):
        m = self._new()
        m.add_turn("Defence", "argument", "BNS 117 and BNS 118 apply here.", round=1)
        laws = m.get_laws_cited()
        assert "BNS 117" in laws
        assert "BNS 118" in laws

    def test_no_duplicate_laws(self):
        m = self._new()
        m.add_turn("Defence",     "argument", "BNS 117 applies.", round=1)
        m.add_turn("Prosecution", "argument", "BNS 117 is violated.", round=1)
        assert m.get_laws_cited().count("BNS 117") == 1

    def test_record_precedent(self):
        m = self._new()
        m.record_precedent("Gurbaksh Singh Sibbia v. State of Punjab")
        assert "Gurbaksh Singh Sibbia v. State of Punjab" in m.get_precedents_cited()

    def test_no_duplicate_precedents(self):
        m = self._new()
        m.record_precedent("Case A")
        m.record_precedent("Case A")
        assert m.get_precedents_cited().count("Case A") == 1

    def test_to_summary_string_not_empty(self):
        m = self._new()
        m.add_turn("Defence", "argument", "Bail should be granted.", round=1)
        summary = m.to_summary_string()
        assert "Bail should be granted" in summary
        assert "DEFENCE" in summary.upper()

    def test_to_summary_string_empty(self):
        m = self._new()
        s = m.to_summary_string()
        assert s == "No previous turns recorded."

    def test_serialise_roundtrip(self):
        m = self._new("CASE_X")
        m.add_turn("Defence", "argument", "No prior record.", round=1)
        m.record_question("Weapon seized?", "IO Agent", "seizure", round=1)
        m.record_answer("Not yet seized.", "IO Agent", 0, round=1)
        data = m.to_dict()
        m2 = CourtRoomStateMemory.from_dict(data)
        assert m2.case_id == "CASE_X"
        assert m2.turn_count() == m.turn_count()
        assert m2.question_count() == m.question_count()

    def test_to_list_format(self):
        m = self._new()
        m.add_turn("Judge", "question", "Is custody needed?", round=1)
        lst = m.to_list()
        assert isinstance(lst, list)
        assert lst[0]["speaker"] == "Judge"

    def test_get_latest_round_turns(self):
        m = self._new()
        m.add_turn("Defence",     "argument", "Round 1 arg", round=1)
        m.add_turn("Prosecution", "argument", "Round 2 arg", round=2)
        r1 = m.get_latest_round_turns(1)
        r2 = m.get_latest_round_turns(2)
        assert len(r1) == 1
        assert len(r2) == 1
        assert r1[0].content == "Round 1 arg"

    def test_global_registry_get_memory(self):
        clear_memory("REG_TEST")
        m1 = get_memory("REG_TEST")
        m2 = get_memory("REG_TEST")
        assert m1 is m2  # same instance

    def test_global_registry_clear(self):
        get_memory("CLEAR_TEST")
        clear_memory("CLEAR_TEST")
        m_new = get_memory("CLEAR_TEST")
        assert m_new.turn_count() == 0
