"""
Stage 4 Pydantic Schemas: Statutory Ingredient Evaluation & Prima Facie Assessment (Schema v4.0)
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from .common import ManualReviewMixin, _sanitize_manual_review


class IngredientEvaluationItem(BaseModel):
    ingredient: str = Field(description="Essential statutory legal ingredient or clause name")
    matched_fact: Optional[str] = Field(default=None, description="Matched factual proposition or null if missing")
    status: str = Field(description="Evaluation status: 'Satisfied', 'Partially Satisfied', 'Missing', 'Contradicted', or 'Unknown'")
    reason: str = Field(description="Explicit reasoning grounded in facts")
    confidence: float = Field(default=0.90, description="Confidence score (0.0 to 1.0)")


class StatutoryIngredientItem(BaseModel):
    ingredient: str = Field(description="Essential statutory legal ingredient or statutory clause")
    logical_operator: str = Field(
        default="MANDATORY",
        description="Logical operator: 'MANDATORY' (or 'AND') for mandatory elements, 'OR' for disjunctive statutory branches"
    )
    condition_group: Optional[str] = Field(
        default="default",
        description="Grouping identifier for disjunctive OR conditions (e.g. 'Cruelty_Disjunctive_Branches')"
    )
    status: str = Field(description="Status of ingredient: 'Satisfied', 'Not Satisfied', or 'Insufficient Evidence'")
    reason: str = Field(description="Reasoning grounded strictly in available case facts")


class VerifiedOffenceItemStage4(BaseModel):
    section_number: str = Field(description="Section number string e.g. '498A', '85', 'Section 4'")
    statute: str = Field(default="IPC", description="Statute name e.g. 'IPC', 'BNS', 'Dowry Prohibition Act'")
    title: str = Field(description="Canonical statutory title")
    irac_reasoning: Optional[Dict[str, Any]] = Field(
        default=None,
        description="IRAC structured reasoning: issue, rule, application (prosecution_version, defence_version, net_evaluation), conclusion"
    )
    ingredient_evaluation: List[IngredientEvaluationItem] = Field(
        default_factory=list,
        description="Detailed ingredient evaluation trace"
    )
    overall_prima_facie_strength: str = Field(
        default="Strong",
        description="Prima facie attraction strength: 'Strong', 'Moderate', 'Weak', or 'Not Attracted'"
    )
    missing_mandatory_facts: List[str] = Field(
        default_factory=list,
        description="Missing mandatory statutory facts"
    )
    missing_supporting_facts: List[str] = Field(
        default_factory=list,
        description="Missing supporting evidentiary facts e.g. Independent witness, Electronic communications"
    )
    investigation_requirements: List[str] = Field(
        default_factory=list,
        description="Evidence and steps required to complete investigation"
    )
    legal_reasoning: str = Field(default="", description="Concise statutory legal reasoning trace")
    overall_status: str = Field(
        default="Prima Facie Attracted",
        description="Overall status: 'Prima Facie Attracted', 'Partially Attracted', or 'Not Attracted'"
    )
    confidence: Optional[float] = Field(
        default=None,
        description="Explicit numerical confidence score (0.0 to 1.0) if provided"
    )
    classification: str = Field(
        default="PRIMARY",
        description="Candidate tier preserved from Stage 2/3: 'PRIMARY', 'SECONDARY' or 'CONDITIONAL'"
    )

    @property
    def section_title(self) -> str:
        return self.title

    @property
    def overall_confidence(self) -> float:
        if self.confidence is not None:
            return self.confidence
        mapping = {"Strong": 0.95, "Moderate": 0.80, "Weak": 0.60, "Not Attracted": 0.20}
        return mapping.get(self.overall_prima_facie_strength, 0.85)

    @property
    def ingredients(self) -> List[StatutoryIngredientItem]:
        items = []
        for e in self.ingredient_evaluation:
            items.append(
                StatutoryIngredientItem(
                    ingredient=e.ingredient,
                    logical_operator="MANDATORY",
                    status="Satisfied" if e.status in ("Satisfied", "Partially Satisfied") else "Not Satisfied",
                    reason=e.reason,
                )
            )
        return items


class VerifiedSectionItem(BaseModel):
    section_number: str = Field(description="Section number (e.g. '498A', '506', '85')")
    section_title: str = Field(description="Section title (e.g. 'Cruelty by Husband or Relatives')")
    punishment_text: Optional[str] = Field(
        default=None,
        description="Extracted punishment text (e.g. 'Imprisonment up to 3 years and fine')"
    )
    max_imprisonment_years: Optional[float] = Field(
        default=None,
        description="Maximum term of imprisonment in years (e.g. 3.0, 7.0, 10.0)"
    )
    arnesh_kumar_threshold_exceeded: bool = Field(
        default=False,
        description="True if max imprisonment > 7 years (Arnesh Kumar threshold exceeded), False if <= 7 years"
    )
    ingredients: List[StatutoryIngredientItem] = Field(
        default_factory=list,
        description="List of essential statutory ingredients evaluated against case facts"
    )
    disjunctive_clause_applied: Optional[str] = Field(
        default=None,
        description="Applied disjunctive clause for OR statutes (e.g. 'Satisfied via Clause (a) Willful Conduct / Grave Injury')"
    )
    overall_confidence: float = Field(default=0.90, description="Overall applicability confidence score (0.0 to 1.0)")

    def is_statutorily_satisfied(self) -> bool:
        if not self.ingredients:
            return False

        mandatory_items = [ing for ing in self.ingredients if ing.logical_operator in ("MANDATORY", "AND")]
        or_groups: Dict[str, List[StatutoryIngredientItem]] = {}
        for ing in self.ingredients:
            if ing.logical_operator == "OR":
                group_key = ing.condition_group or "default_or_group"
                if group_key not in or_groups:
                    or_groups[group_key] = []
                or_groups[group_key].append(ing)

        all_mandatory_ok = all(ing.status == "Satisfied" for ing in mandatory_items)
        if not all_mandatory_ok:
            return False

        for group_key, items in or_groups.items():
            if not any(ing.status == "Satisfied" for ing in items):
                return False

        return True


class StatutoryVerificationObject(ManualReviewMixin):
    schema_version: str = Field(default="4.0", description="Schema version of StatutoryVerificationObject contract")
    verified_offences: List[VerifiedOffenceItemStage4] = Field(
        default_factory=list,
        description="List of verified offences with ingredient evaluation and prima facie strength"
    )
    conditional_offences: List[VerifiedOffenceItemStage4] = Field(
        default_factory=list,
        description="CONDITIONAL sections (statutory gap or unproven predicate); not treated as established offences"
    )
    verified_sections: List[VerifiedSectionItem] = Field(
        default_factory=list,
        description="List of verified statutory sections (maintained for backward compatibility)"
    )
    legal_regime: Optional[str] = Field(
        default="IPC + CrPC",
        description="Legal regime passed through unchanged from Stage 3 ('IPC + CrPC')"
    )

    verification_status: str = Field(
        default="VERIFIED",
        description="Verification status: PENDING, VERIFIED, or RETRY"
    )
    pipeline_transition: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Stage-to-stage transition audit: lists sections received from Stage 3, confirmed, dropped (with reasons), and passing to Stage 5."
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.verified_sections and self.verified_offences:
            for vo in self.verified_offences:
                self.verified_sections.append(
                    VerifiedSectionItem(
                        section_number=vo.section_number,
                        section_title=vo.title,
                        punishment_text="Imprisonment as prescribed by law.",
                        max_imprisonment_years=3.0,
                        arnesh_kumar_threshold_exceeded=False,
                        ingredients=vo.ingredients,
                        overall_confidence=vo.overall_confidence,
                    )
                )

    def to_downstream_json(self) -> str:
        return self.model_dump_json(indent=2)


class StatutoryVerificationIssue(BaseModel):
    target: str = Field(description="Target section number or ingredient with error")
    issue: str = Field(description="Detailed description of statutory verification audit issue")
    feedback: str = Field(description="Actionable instructions for statutory verification agent correction")


class StatutoryVerificationResult(BaseModel):
    status: str = Field(description="Status: 'VERIFIED' or 'RETRY'")
    issues: List[StatutoryVerificationIssue] = Field(default_factory=list, description="List of audit issues identified")
    feedback: str = Field(default="Statutory verification audit complete.", description="Overall summary feedback")
    verified_statutory_object: Optional[StatutoryVerificationObject] = Field(default=None, description="Verified StatutoryVerificationObject")
