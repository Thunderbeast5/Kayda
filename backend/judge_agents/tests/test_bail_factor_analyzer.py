"""
Unit tests for BailFactorAnalyzer.
Run: python -m pytest backend/judge_agents/tests/test_bail_factor_analyzer.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from judge_agents.services.bail_factor_analyzer import BailFactorAnalyzer

_analyzer = BailFactorAnalyzer()


class TestBailFactorAnalyzer:

    def test_full_report_parsed(self):
        report = {
            "gravity_of_offence":     "High",
            "flight_risk":            "Low",
            "custodial_need":         "Yes",
            "witness_tampering_risk": "Medium",
            "antecedents":            "One prior conviction",
            "mitigating_factors":     ["Family ties", "Employed"],
            "aggravating_factors":    ["Use of weapon"],
        }
        result = _analyzer.analyze(report)
        assert result.gravity_of_offence == "High"
        assert result.flight_risk == "Low"
        assert result.custodial_need == "Yes"
        assert result.witness_tampering_risk == "Medium"
        assert result.antecedents == "One prior conviction"
        assert "Family ties" in result.mitigating_factors
        assert "Use of weapon" in result.aggravating_factors

    def test_empty_report_returns_safe_defaults(self):
        result = _analyzer.analyze({})
        assert result.gravity_of_offence == "High"
        assert result.flight_risk == "Medium"
        assert result.custodial_need == "No"
        assert result.antecedents == "None"
        assert result.mitigating_factors == []
        assert result.aggravating_factors == []

    def test_none_report_returns_safe_defaults(self):
        result = _analyzer.analyze(None)
        assert result.gravity_of_offence == "High"
        assert result.custodial_need == "No"

    def test_normalises_case_insensitive_levels(self):
        report = {"gravity_of_offence": "high", "flight_risk": "LOW"}
        result = _analyzer.analyze(report)
        assert result.gravity_of_offence == "High"
        assert result.flight_risk == "Low"

    def test_normalises_moderate_to_medium(self):
        report = {"gravity_of_offence": "Moderate"}
        result = _analyzer.analyze(report)
        assert result.gravity_of_offence == "Medium"

    def test_comma_separated_factors_parsed(self):
        report = {
            "mitigating_factors": "No prior record, Employed, Family ties",
            "aggravating_factors": "Use of weapon, Threatening witness",
        }
        result = _analyzer.analyze(report)
        assert len(result.mitigating_factors) == 3
        assert len(result.aggravating_factors) == 2

    def test_custodial_need_yes_variants(self):
        for val in ("Yes", "yes", "true", "TRUE", "required", "needed"):
            result = _analyzer.analyze({"custodial_need": val})
            assert result.custodial_need == "Yes", f"Failed for: {val}"

    def test_custodial_need_no_variants(self):
        for val in ("No", "no", "false", "FALSE", "not required"):
            result = _analyzer.analyze({"custodial_need": val})
            assert result.custodial_need == "No", f"Failed for: {val}"
