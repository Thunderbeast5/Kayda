"""
Unit tests for DynamicRetrievalTrigger — Phase 3
Run: python -m pytest tests/test_dynamic_retrieval.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from judge_agents.dynamic_retrieval import (
    DynamicRetrievalTrigger,
    _merge_legal_packages,
    _merge_precedent_contexts,
)
from judge_agents.services.issue_detector import IssueDetector, IssueDetectionResult, NewLegalIssue
from judge_agents.courtroom_memory import CourtRoomStateMemory


# ── Fixtures ──────────────────────────────────────────────────────────────────

_LEGAL_PKG = {
    "recommended_sections": [
        {"section": "BNS 117", "title": "Grievous hurt", "confidence": 0.91},
    ],
    "supporting_articles": ["Article 21"],
}

_PREC_CTX = {
    "similar_cases": [
        {"case_name": "Gurbaksh Singh Sibbia v. State of Punjab", "citation": "1980 AIR 1632"},
    ]
}

_UPDATED_LEGAL = {
    "recommended_sections": [
        {"section": "NDPS 37", "title": "Special bail restrictions", "confidence": 0.88},
    ],
    "supporting_articles": ["Article 22"],
}

_UPDATED_PREC = {
    "similar_cases": [
        {"case_name": "Sushila Aggarwal v. State NCT Delhi", "citation": "(2020) 5 SCC 1"},
    ]
}

_DETECTION_WITH_ISSUES = IssueDetectionResult(
    new_issues=[
        NewLegalIssue(
            issue_type="UNKNOWN_SECTION",
            reference="NDPS 37",
            source="Defence",
            description="NDPS 37 not in current package",
            retrieval_needed=["LexiGraph"],
        )
    ],
    retrieval_required=True,
    target_agents=["LexiGraph"],
)

_DETECTION_NO_ISSUES = IssueDetectionResult(
    new_issues=[],
    retrieval_required=False,
    target_agents=[],
)


# ── Merge tests ───────────────────────────────────────────────────────────────

class TestMergeLegalPackages:

    def test_new_section_appended(self):
        merged = _merge_legal_packages(_LEGAL_PKG, _UPDATED_LEGAL)
        sections = [s["section"] for s in merged["recommended_sections"]]
        assert "BNS 117" in sections
        assert "NDPS 37" in sections

    def test_existing_section_not_duplicated(self):
        update_with_dupe = {
            "recommended_sections": [{"section": "BNS 117", "title": "Updated title"}],
        }
        merged = _merge_legal_packages(_LEGAL_PKG, update_with_dupe)
        bns_117 = [s for s in merged["recommended_sections"] if s["section"] == "BNS 117"]
        assert len(bns_117) == 1  # original kept, no dupe

    def test_articles_merged(self):
        merged = _merge_legal_packages(_LEGAL_PKG, _UPDATED_LEGAL)
        assert "Article 21" in merged["supporting_articles"]
        assert "Article 22" in merged["supporting_articles"]

    def test_empty_update_returns_original(self):
        merged = _merge_legal_packages(_LEGAL_PKG, {})
        assert merged["recommended_sections"] == _LEGAL_PKG["recommended_sections"]

    def test_original_not_mutated(self):
        original_copy = dict(_LEGAL_PKG)
        _merge_legal_packages(_LEGAL_PKG, _UPDATED_LEGAL)
        assert _LEGAL_PKG == original_copy


class TestMergePrecedentContexts:

    def test_new_case_appended(self):
        merged = _merge_precedent_contexts(_PREC_CTX, _UPDATED_PREC)
        names = [c["case_name"] for c in merged["similar_cases"]]
        assert "Gurbaksh Singh Sibbia v. State of Punjab" in names
        assert "Sushila Aggarwal v. State NCT Delhi" in names

    def test_no_duplicate_cases(self):
        merged = _merge_precedent_contexts(_PREC_CTX, _PREC_CTX)
        names = [c["case_name"] for c in merged["similar_cases"]]
        assert names.count("Gurbaksh Singh Sibbia v. State of Punjab") == 1

    def test_list_input_for_original(self):
        orig_list = [{"case_name": "Case A"}]
        update    = {"similar_cases": [{"case_name": "Case B"}]}
        merged = _merge_precedent_contexts(orig_list, update)
        names = [c["case_name"] for c in merged["similar_cases"]]
        assert "Case A" in names
        assert "Case B" in names


# ── DynamicRetrievalTrigger tests ─────────────────────────────────────────────

class TestDynamicRetrievalTriggerNoOp:
    """Tests with no callback (safe no-op mode)."""

    def test_no_issues_returns_not_triggered(self):
        trigger = DynamicRetrievalTrigger()
        result = trigger.trigger(_DETECTION_NO_ISSUES, _LEGAL_PKG, _PREC_CTX)
        assert result.triggered is False

    def test_no_op_returns_original_context(self):
        trigger = DynamicRetrievalTrigger()
        result = trigger.trigger(_DETECTION_WITH_ISSUES, _LEGAL_PKG, _PREC_CTX)
        assert result.triggered is True  # triggered=True because retrieval_required
        # But sections unchanged (no-op callback)
        sections = [s["section"] for s in result.updated_legal_context_package["recommended_sections"]]
        assert "BNS 117" in sections

    def test_no_op_issues_unresolved(self):
        trigger = DynamicRetrievalTrigger()
        result = trigger.trigger(_DETECTION_WITH_ISSUES, _LEGAL_PKG, _PREC_CTX)
        assert "NDPS 37" in result.issues_unresolved

    def test_retrieval_count_increments(self):
        trigger = DynamicRetrievalTrigger()
        assert trigger.retrieval_count == 0
        trigger.trigger(_DETECTION_WITH_ISSUES, _LEGAL_PKG, _PREC_CTX)
        assert trigger.retrieval_count == 1

    def test_max_retrievals_enforced(self):
        trigger = DynamicRetrievalTrigger(max_retrievals=2)
        trigger.trigger(_DETECTION_WITH_ISSUES, _LEGAL_PKG, _PREC_CTX)
        trigger.trigger(_DETECTION_WITH_ISSUES, _LEGAL_PKG, _PREC_CTX)
        assert trigger.can_trigger() is False
        result = trigger.trigger(_DETECTION_WITH_ISSUES, _LEGAL_PKG, _PREC_CTX)
        assert result.triggered is False  # blocked by max

    def test_retrieval_count_in_result(self):
        trigger = DynamicRetrievalTrigger()
        result = trigger.trigger(_DETECTION_WITH_ISSUES, _LEGAL_PKG, _PREC_CTX)
        assert result.retrieval_count == 1


class TestDynamicRetrievalTriggerWithCallback:
    """Tests with a real callback that returns updated context."""

    def _make_callback(self):
        def callback(issues, legal_pkg, prec_ctx):
            return _UPDATED_LEGAL, _UPDATED_PREC
        return callback

    def test_callback_invoked_and_merged(self):
        trigger = DynamicRetrievalTrigger(retrieval_callback=self._make_callback())
        result = trigger.trigger(_DETECTION_WITH_ISSUES, _LEGAL_PKG, _PREC_CTX)
        assert result.triggered is True
        sections = [s["section"] for s in result.updated_legal_context_package["recommended_sections"]]
        assert "BNS 117" in sections   # original preserved
        assert "NDPS 37" in sections   # new from callback

    def test_callback_resolved_issues(self):
        trigger = DynamicRetrievalTrigger(retrieval_callback=self._make_callback())
        result = trigger.trigger(_DETECTION_WITH_ISSUES, _LEGAL_PKG, _PREC_CTX)
        assert "NDPS 37" in result.issues_resolved
        assert result.issues_unresolved == []

    def test_precedents_merged_from_callback(self):
        trigger = DynamicRetrievalTrigger(retrieval_callback=self._make_callback())
        result = trigger.trigger(_DETECTION_WITH_ISSUES, _LEGAL_PKG, _PREC_CTX)
        names = [c["case_name"] for c in result.updated_precedent_context["similar_cases"]]
        assert "Gurbaksh Singh Sibbia v. State of Punjab" in names
        assert "Sushila Aggarwal v. State NCT Delhi" in names

    def test_callback_failure_returns_originals(self):
        def bad_callback(issues, legal_pkg, prec_ctx):
            raise RuntimeError("Retrieval service unavailable")
        trigger = DynamicRetrievalTrigger(retrieval_callback=bad_callback)
        result = trigger.trigger(_DETECTION_WITH_ISSUES, _LEGAL_PKG, _PREC_CTX)
        # Should not raise — returns originals
        assert result.triggered is True
        assert "NDPS 37" in result.issues_unresolved

    def test_memory_updated_on_trigger(self):
        memory = CourtRoomStateMemory(case_id="MEM_TEST")
        trigger = DynamicRetrievalTrigger(retrieval_callback=self._make_callback())
        trigger.trigger(_DETECTION_WITH_ISSUES, _LEGAL_PKG, _PREC_CTX, memory=memory)
        # Memory should have system turns for trigger + completion
        sys_turns = [t for t in memory.get_history() if t.speaker == "System"]
        assert len(sys_turns) >= 2


class TestDynamicRetrievalIntegration:
    """End-to-end: IssueDetector → DynamicRetrievalTrigger."""

    def test_detect_then_trigger_full_flow(self):
        def callback(issues, legal_pkg, prec_ctx):
            # Simulate returning the missing section
            return {
                "recommended_sections": [{"section": "NDPS 37", "title": "Bail restriction"}],
                "supporting_articles": [],
            }, {}

        detector = IssueDetector()
        trigger  = DynamicRetrievalTrigger(retrieval_callback=callback)

        texts = {"Defence": "NDPS 37 imposes special restrictions.", "Prosecution": "", "IO Agent": ""}
        detection = detector.detect(texts, _LEGAL_PKG, _PREC_CTX)

        assert detection.retrieval_required is True

        result = trigger.trigger(detection, _LEGAL_PKG, _PREC_CTX)
        assert result.triggered is True
        sections = [s["section"] for s in result.updated_legal_context_package["recommended_sections"]]
        assert "NDPS 37" in sections
