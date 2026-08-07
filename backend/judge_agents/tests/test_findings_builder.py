"""
Unit tests for FindingsBuilder.
Run: python -m pytest backend/judge_agents/tests/test_findings_builder.py -v
"""

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from judge_agents.services.findings_builder import FindingsBuilder

_builder = FindingsBuilder()

_LEGAL_PKG = {
    "recommended_sections": [
        {"section": "BNS 117", "title": "Grievous hurt", "confidence": 0.91},
        {"section": "BNS 118", "title": "Dangerous weapon", "confidence": 0.85},
    ],
    "supporting_articles": ["Article 21"],
}

_PRECEDENT_CTX = {
    "similar_cases": [
        {
            "case_name": "Gurbaksh Singh Sibbia v. State of Punjab",
            "citation": "1980 AIR 1632",
        }
    ]
}

_VALID_JSON = {
    "case_id": "TEST_001",
    "hearing_date": "07/08/2026",
    "judge_name": "AI Judge",
    "applicant": "Suresh Kumar",
    "respondent": "State of Maharashtra",
    "sections_applied": ["BNS 117", "BNS 118"],
    "constitutional_articles_applied": ["Article 21"],
    "precedents_applied": [
        {
            "case_name": "Gurbaksh Singh Sibbia v. State of Punjab",
            "citation": "1980 AIR 1632",
            "principle_applied": "Bail may be granted with conditions",
        }
    ],
    "evidence_evaluation": {
        "strength": "Medium",
        "key_evidence": ["Medical report"],
        "contradictions_noted": [],
        "missing_evidence": ["CCTV footage"],
    },
    "bail_factor_analysis": {
        "gravity_of_offence": "Medium",
        "flight_risk": "Low",
        "custodial_need": "No",
        "witness_tampering_risk": "Low",
        "antecedents": "None",
        "mitigating_factors": ["No prior record"],
        "aggravating_factors": ["Use of weapon"],
    },
    "argument_evaluation": {
        "defence_score": {"legal_validity": 7, "evidence_linkage": 6, "logic_coherence": 8, "total": 21},
        "prosecution_score": {"legal_validity": 8, "evidence_linkage": 7, "logic_coherence": 7, "total": 22},
    },
    "judicial_analysis": "Having heard the parties, this Court finds...",
    "preliminary_finding": "Bail Likely Granted",
    "confidence": 72,
    "conditions_if_granted": ["Surrender passport", "Report weekly"],
    "questions_asked": [],
    "dynamic_retrieval_triggered": False,
    "new_issues_identified": [],
}


class TestFindingsBuilder:

    def _build(self, data=None, state_history=None):
        raw = json.dumps(data or _VALID_JSON)
        return _builder.build(
            llm_output=raw,
            legal_context_package=_LEGAL_PKG,
            precedent_context=_PRECEDENT_CTX,
            state_history=state_history or [],
        )

    def test_valid_json_parses_correctly(self):
        findings = self._build()
        assert findings.case_id == "TEST_001"
        assert findings.applicant == "Suresh Kumar"
        assert findings.preliminary_finding == "Bail Likely Granted"
        assert findings.confidence == 72

    def test_sections_applied_in_findings(self):
        findings = self._build()
        assert "BNS 117" in findings.sections_applied
        assert "BNS 118" in findings.sections_applied

    def test_hallucination_guard_removes_unknown_section(self):
        data = {**_VALID_JSON, "sections_applied": ["BNS 117", "BNS 999"]}
        findings = self._build(data)
        assert "BNS 117" in findings.sections_applied
        assert "BNS 999" not in findings.sections_applied

    def test_hallucination_guard_removes_unknown_precedent(self):
        data = {
            **_VALID_JSON,
            "precedents_applied": [
                {
                    "case_name": "Fake v. Fake",
                    "citation": "2099 AIR 0",
                    "principle_applied": "Hallucinated principle",
                }
            ],
        }
        findings = self._build(data)
        assert len(findings.precedents_applied) == 0

    def test_known_precedent_passes_guard(self):
        findings = self._build()
        assert len(findings.precedents_applied) == 1
        assert "Sibbia" in findings.precedents_applied[0].case_name

    def test_confidence_clamped(self):
        data = {**_VALID_JSON, "confidence": 150}
        findings = self._build(data)
        assert findings.confidence == 100

        data2 = {**_VALID_JSON, "confidence": -10}
        findings2 = self._build(data2)
        assert findings2.confidence == 0

    def test_evidence_strength_normalised(self):
        findings = self._build()
        assert findings.evidence_evaluation.strength in ("High", "Medium", "Low")

    def test_preliminary_finding_normalised(self):
        data = {**_VALID_JSON, "preliminary_finding": "likely rejected"}
        findings = self._build(data)
        assert findings.preliminary_finding == "Bail Likely Rejected"

    def test_state_history_stored(self):
        history = ["IDLE → RECEIVING_INPUTS", "RECEIVING_INPUTS → COMPREHENDING_CASE"]
        findings = self._build(state_history=history)
        assert findings.state_history == history

    def test_malformed_json_returns_safe_fallback(self):
        findings = _builder.build(
            llm_output="This is not JSON at all.",
            legal_context_package=_LEGAL_PKG,
            precedent_context=_PRECEDENT_CTX,
            state_history=[],
        )
        # Should not raise — falls back to defaults
        assert findings.preliminary_finding == "Inconclusive"
        assert findings.confidence == 50
