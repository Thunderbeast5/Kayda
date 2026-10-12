"""
tests/test_verdict_voting.py
============================
Integration tests for the voting judge engine.

These tests:
  1. Load fixtures from tests/fixtures/bail_cases.yaml
  2. Run voting.decide() directly (bypassing the full orchestrator)
  3. Assert the expected outcome matches

If a fixture regresses:
  - Check holding retrieval recall for that case
  - Improve holdings data or fact extraction
  - NEVER add if-statements to judge/voting.py to fix it

Run:
  cd backend
  pytest tests/test_verdict_voting.py -v
"""

import pytest
import yaml
from pathlib import Path

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "bail_cases.yaml"


def load_fixtures():
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def pytest_generate_tests(metafunc):
    if "case_fixture" in metafunc.fixturenames:
        cases = load_fixtures()
        metafunc.parametrize(
            "case_fixture",
            cases,
            ids=[c["case"] for c in cases],
        )


# --------------------------------------------------------------------------- #
# Unit tests for validate() and aggregate() -- no LLM calls                   #
# --------------------------------------------------------------------------- #

class TestValidate:
    def test_valid_vote_passes(self):
        from agents.judge.voting import Factor, JudgeVote, validate
        vote = JudgeVote(
            outcome="DENIED",
            factors=[Factor(finding="absconding", fact_ids=["fact_1"], holding_ids=["srikant_para23"])],
            open_questions=[],
            laws_applied=["CrPC 438"],
        )
        assert validate(vote, {"fact_1", "fact_2"}, {"srikant_para23"})

    def test_invented_fact_fails(self):
        from agents.judge.voting import Factor, JudgeVote, validate
        vote = JudgeVote(
            outcome="DENIED",
            factors=[Factor(finding="absconding", fact_ids=["fact_99"], holding_ids=[])],
            open_questions=[],
            laws_applied=[],
        )
        assert not validate(vote, {"fact_1"}, set())

    def test_invented_holding_fails(self):
        from agents.judge.voting import Factor, JudgeVote, validate
        vote = JudgeVote(
            outcome="DENIED",
            factors=[Factor(finding="absconding", fact_ids=["fact_1"], holding_ids=["ghost_holding"])],
            open_questions=[],
            laws_applied=[],
        )
        assert not validate(vote, {"fact_1"}, {"srikant_para23"})

    def test_no_opinion_without_questions_fails(self):
        from agents.judge.voting import Factor, JudgeVote, validate
        vote = JudgeVote(
            outcome="NO_OPINION",
            factors=[Factor(finding="unclear", fact_ids=["fact_1"], holding_ids=[])],
            open_questions=[],
        )
        assert not validate(vote, {"fact_1"}, set())

    def test_no_opinion_with_questions_passes(self):
        from agents.judge.voting import Factor, JudgeVote, validate
        vote = JudgeVote(
            outcome="NO_OPINION",
            factors=[Factor(finding="unclear", fact_ids=["fact_1"], holding_ids=[])],
            open_questions=["Is there an unexecuted warrant?"],
        )
        assert validate(vote, {"fact_1"}, set())

    def test_verdict_without_facts_fails(self):
        from agents.judge.voting import Factor, JudgeVote, validate
        vote = JudgeVote(
            outcome="GRANTED",
            factors=[Factor(finding="cooperated", fact_ids=[], holding_ids=[])],
            open_questions=[],
        )
        assert not validate(vote, {"fact_1"}, set())


class TestAggregate:
    def _vote(self, outcome):
        from agents.judge.voting import Factor, JudgeVote
        return JudgeVote(
            outcome=outcome,
            factors=[Factor(finding="x", fact_ids=["fact_1"], holding_ids=[])],
            open_questions=["q"] if outcome == "NO_OPINION" else [],
            raw_explanation="test",
        )

    def test_majority_denied(self):
        from agents.judge.voting import aggregate
        votes = [self._vote("DENIED")] * 4 + [self._vote("GRANTED")]
        result = aggregate(votes)
        assert result.outcome == "DENIED"
        assert result.confidence == "high"
        assert result.agreement_rate == pytest.approx(0.8)

    def test_split_gives_no_opinion(self):
        from agents.judge.voting import aggregate
        votes = [self._vote("DENIED")] * 2 + [self._vote("GRANTED")] * 2 + [self._vote("NO_OPINION")]
        result = aggregate(votes)
        assert result.outcome == "NO_OPINION"
        assert result.confidence == "low"

    def test_empty_votes_gives_no_opinion(self):
        from agents.judge.voting import aggregate
        result = aggregate([])
        assert result.outcome == "NO_OPINION"
        assert result.agreement_rate == 0.0

    def test_medium_confidence_threshold(self):
        from agents.judge.voting import aggregate
        votes = [self._vote("GRANTED")] * 3 + [self._vote("DENIED")] * 2
        result = aggregate(votes)
        assert result.outcome == "GRANTED"
        assert result.confidence == "medium"  # 60%, not >= 80%


# --------------------------------------------------------------------------- #
# Integration test: run decide() against fixtures (requires OPENAI_API_KEY)   #
# --------------------------------------------------------------------------- #

@pytest.mark.integration
class TestVerdictFixtures:
    """
    Marked 'integration' -- skipped in CI unless explicitly enabled.
    Run with:  pytest tests/test_verdict_voting.py -m integration -v
    """

    def test_fixture_outcome(self, case_fixture):
        import os
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        from agents.judge.voting import decide
        from agents.config.llm_config import get_llm

        llm = get_llm()

        # Convert YAML dicts to the shape decide() expects
        facts = case_fixture.get("facts", [])
        holdings = case_fixture.get("holdings", [])
        expected = case_fixture["expect"].upper()

        result = decide(
            facts=facts,
            holdings=holdings,
            prosecution_args=case_fixture.get("prosecution_args", ""),
            defense_args=case_fixture.get("defense_args", ""),
            accused_history=[],
            llm=llm,
            n=3,   # Use 3 votes in tests to save cost
        )

        assert result.outcome == expected, (
            f"Case '{case_fixture['case']}': expected {expected}, "
            f"got {result.outcome} (tally={result.vote_tally}, "
            f"agreement={result.agreement_rate:.0%})\n"
            f"why: {result.why}"
        )
