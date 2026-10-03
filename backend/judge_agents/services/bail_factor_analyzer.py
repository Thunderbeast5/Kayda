"""
BailFactorAnalyzer service.

Extracts and normalises the nine bail factors from the
bail_assessment_report dict produced by the Bail Assessment Agent.

This service is deterministic — it does not call the LLM.
The LLM applies these factors when forming findings (FindingsBuilder).
"""

from typing import Literal
from ..models.judicial_findings import BailFactorAnalysis


_LEVEL_MAP = {
    # Normalise common LLM variations to High / Medium / Low
    "high":    "High",
    "medium":  "Medium",
    "moderate": "Medium",
    "low":     "Low",
    "nil":     "Low",
    "none":    "Low",
    "yes":     "High",
    "no":      "Low",
}


def _normalise_level(raw: str | None, default: str = "Medium") -> str:
    if not raw:
        return default
    return _LEVEL_MAP.get(str(raw).strip().lower(), default)


def _normalise_yes_no(raw: str | None, default: str = "No") -> Literal["Yes", "No"]:
    if not raw:
        return default  # type: ignore[return-value]
    val = str(raw).strip().lower()
    if val in ("yes", "true", "1", "required", "needed", "high"):
        return "Yes"
    return "No"


def _extract_list(value) -> list[str]:
    """Accept a list or a comma-separated string."""
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str) and value.strip():
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


class BailFactorAnalyzer:
    """
    Reads a raw bail_assessment_report dict and returns a
    normalised BailFactorAnalysis Pydantic model.

    The report dict is expected to follow this loose schema
    (produced by the Bail Assessment Agent — Phase 2 build):
    {
        "gravity_of_offence":      "High" | "Medium" | "Low",
        "flight_risk":             "High" | "Medium" | "Low",
        "custodial_need":          "Yes" | "No",
        "witness_tampering_risk":  "High" | "Medium" | "Low",
        "antecedents":             "None" | "description",
        "recovery_pending":        "Yes" | "No",
        "cooperation":             "Good" | "Poor" | "N/A",
        "mitigating_factors":      ["factor", ...],
        "aggravating_factors":     ["factor", ...],
    }

    Missing keys fall back to safe defaults.
    """

    def analyze(self, bail_assessment_report: dict) -> BailFactorAnalysis:
        r = bail_assessment_report or {}

        gravity         = _normalise_level(r.get("gravity_of_offence"), "High")
        flight_risk     = _normalise_level(r.get("flight_risk"), "Medium")
        custodial_need  = _normalise_yes_no(r.get("custodial_need"), "No")
        tampering_risk  = _normalise_level(r.get("witness_tampering_risk"), "Medium")
        antecedents     = str(r.get("antecedents") or "None").strip() or "None"
        mitigating      = _extract_list(r.get("mitigating_factors"))
        aggravating     = _extract_list(r.get("aggravating_factors"))

        return BailFactorAnalysis(
            gravity_of_offence=gravity,         # type: ignore[arg-type]
            flight_risk=flight_risk,             # type: ignore[arg-type]
            custodial_need=custodial_need,
            witness_tampering_risk=tampering_risk, # type: ignore[arg-type]
            antecedents=antecedents,
            mitigating_factors=mitigating,
            aggravating_factors=aggravating,
        )
