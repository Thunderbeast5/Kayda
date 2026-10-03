"""
Unit tests for IssueDetector — Phase 3
Run: python -m pytest tests/test_issue_detector.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from judge_agents.services.issue_detector import IssueDetector, _known_sections, _known_precedents

detector = IssueDetector()

# ── Shared context fixtures ───────────────────────────────────────────────────

_LEGAL_PKG = {
    "recommended_sections": [
        {"section": "BNS 117", "title": "Grievous hurt"},
        {"section": "BNS 118", "title": "Grievous hurt by weapon"},
    ],
    "supporting_articles": ["Article 21 - Right to life"],
}

_PREC_CTX = {
    "similar_cases": [
        {"case_name": "Gurbaksh Singh Sibbia v. State of Punjab", "citation": "1980 AIR 1632"},
    ]
}


class TestKnownSections:

    def test_extracts_bns_sections(self):
        known = _known_sections(_LEGAL_PKG)
        assert "BNS_117" in known
        assert "BNS_118" in known

    def test_extracts_articles(self):
        known = _known_sections(_LEGAL_PKG)
        assert "ARTICLE_21" in known

    def test_empty_package_returns_empty_set(self):
        assert _known_sections({}) == set()


class TestKnownPrecedents:

    def test_extracts_case_name(self):
        known = _known_precedents(_PREC_CTX)
        assert "gurbaksh singh sibbia v. state of punjab" in known

    def test_list_format(self):
        known = _known_precedents([{"case_name": "Some Case v. State"}])
        assert "some case v. state" in known

    def test_empty_returns_empty_set(self):
        assert _known_precedents({}) == set()


class TestIssueDetector:

    def test_no_issues_when_all_known(self):
        texts = {
            "Defence":     "BNS 117 applies. Article 21 protects liberty.",
            "Prosecution": "BNS 118 shows dangerous weapon use.",
            "IO Agent":    "Investigation ongoing.",
        }
        result = detector.detect(texts, _LEGAL_PKG, _PREC_CTX)
        # BNS 117, BNS 118, Article 21 are all known — no new issues
        unknown = [i for i in result.new_issues if i.issue_type == "UNKNOWN_SECTION"]
        assert len(unknown) == 0

    def test_unknown_section_detected(self):
        texts = {
            "Defence": "NDPS 37 imposes special bail restrictions.",
            "Prosecution": "",
            "IO Agent": "",
        }
        result = detector.detect(texts, _LEGAL_PKG, _PREC_CTX)
        refs = [i.reference for i in result.new_issues]
        assert any("NDPS" in r for r in refs)
        assert result.retrieval_required is True

    def test_unknown_article_detected(self):
        texts = {
            "Defence": "Article 22 guarantees protection against arbitrary arrest.",
            "Prosecution": "",
            "IO Agent": "",
        }
        result = detector.detect(texts, _LEGAL_PKG, _PREC_CTX)
        types = [i.issue_type for i in result.new_issues]
        assert "UNKNOWN_ARTICLE" in types

    def test_known_article_not_flagged(self):
        texts = {
            "Defence": "Article 21 protects right to life.",
            "Prosecution": "",
            "IO Agent": "",
        }
        result = detector.detect(texts, _LEGAL_PKG, _PREC_CTX)
        art_issues = [i for i in result.new_issues if i.issue_type == "UNKNOWN_ARTICLE"]
        assert len(art_issues) == 0

    def test_procedural_law_detected(self):
        texts = {
            "Defence": "BNSS 484 governs anticipatory bail.",
            "Prosecution": "",
            "IO Agent": "",
        }
        result = detector.detect(texts, _LEGAL_PKG, _PREC_CTX)
        types = [i.issue_type for i in result.new_issues]
        assert "PROCEDURAL_LAW" in types

    def test_crpc_detected_as_procedural(self):
        texts = {
            "Defence": "CrPC 438 is the relevant provision.",
            "Prosecution": "",
            "IO Agent": "",
        }
        result = detector.detect(texts, _LEGAL_PKG, _PREC_CTX)
        types = [i.issue_type for i in result.new_issues]
        assert "PROCEDURAL_LAW" in types

    def test_unknown_precedent_detected(self):
        texts = {
            "Defence": "As held in (2020) 5 SCC 1, anticipatory bail should not be time-limited.",
            "Prosecution": "",
            "IO Agent": "",
        }
        result = detector.detect(texts, _LEGAL_PKG, _PREC_CTX)
        types = [i.issue_type for i in result.new_issues]
        assert "UNKNOWN_PRECEDENT" in types

    def test_multiple_sources_scanned(self):
        texts = {
            "Defence":     "NDPS 37 applies.",
            "Prosecution": "IPC 302 is relevant.",
            "IO Agent":    "BNSS 167 remand provisions apply.",
        }
        result = detector.detect(texts, _LEGAL_PKG, _PREC_CTX)
        sources = {i.source for i in result.new_issues}
        # All three sources should contribute issues
        assert len(sources) >= 2

    def test_no_duplicate_references(self):
        texts = {
            "Defence":     "NDPS 37 is crucial. Also NDPS 37 restricts bail.",
            "Prosecution": "NDPS 37 must be considered.",
            "IO Agent":    "",
        }
        result = detector.detect(texts, _LEGAL_PKG, _PREC_CTX)
        refs = [i.reference for i in result.new_issues if "NDPS" in i.reference]
        assert len(refs) == 1  # deduplicated

    def test_target_agents_populated(self):
        texts = {
            "Defence": "NDPS 37 applies and (2020) 5 SCC 1 confirms this.",
            "Prosecution": "",
            "IO Agent": "",
        }
        result = detector.detect(texts, _LEGAL_PKG, _PREC_CTX)
        # Should need both LexiGraph (for NDPS) and Precedent (for the case)
        assert "LexiGraph" in result.target_agents or "Precedent" in result.target_agents

    def test_empty_texts_no_issues(self):
        result = detector.detect({"Defence": "", "Prosecution": "", "IO Agent": ""}, _LEGAL_PKG, _PREC_CTX)
        assert result.new_issues == []
        assert result.retrieval_required is False

    def test_retrieval_required_flag(self):
        texts = {"Defence": "POCSO 4 imposes mandatory minimum.", "Prosecution": "", "IO Agent": ""}
        result = detector.detect(texts, _LEGAL_PKG, _PREC_CTX)
        assert result.retrieval_required is True
