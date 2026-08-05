"""
Bail Condition Closed-Set Validator.

Maintains the canonical list of legally permissible anticipatory bail condition categories
derived from Section 438(2) CrPC (IPC regime) and Section 482(2) BNSS (BNS regime),
and judicial precedents including Gurbaksh Singh Sibbia, Sushila Aggarwal, and Satender Kumar Antil.

Validates every generated bail condition against the closed set.
Rejects or flags conditions outside the authorized statutory categories.
"""

from __future__ import annotations
import re
from typing import List, Optional, Tuple


# ==============================================================================
# CANONICAL CLOSED SET: Permissible Anticipatory Bail Condition Categories
# Section 438(2) CrPC / Section 482(2) BNSS + established judicial practice
# ==============================================================================

PERMISSIBLE_BAIL_CONDITION_CATEGORIES = {
    "appearance": {
        "label": "Appearance / Availability for Interrogation",
        "description": "Accused shall make himself available for interrogation by the investigating officer as and when required.",
        "trigger_keywords": [
            "appear", "make himself available", "report", "present himself", "interrogation",
            "whenever required", "io", "investigating officer", "attendance"
        ],
        "statutory_basis": "S.438(2)(i) CrPC / S.482(2)(i) BNSS",
    },
    "passport": {
        "label": "Surrender Passport / Travel Restriction",
        "description": "Accused shall not leave India without prior permission of the court. Passport to be surrendered if directed.",
        "trigger_keywords": [
            "passport", "leave india", "travel", "travel abroad", "leave country",
            "surrender passport", "prior permission to travel", "not leave", "not depart"
        ],
        "statutory_basis": "S.438(2)(iv) CrPC / S.482(2)(iv) BNSS",
    },
    "no_tampering": {
        "label": "Non-Tampering with Evidence / Witnesses",
        "description": "Accused shall not directly or indirectly tamper with witnesses, complainant, or evidence.",
        "trigger_keywords": [
            "tamper", "influence witness", "threaten witness", "approach complainant",
            "interfere", "induce", "not tamper", "not threaten", "non-interference",
            "no contact with complainant", "not approach victim"
        ],
        "statutory_basis": "S.438(2)(ii) CrPC / S.482(2)(ii) BNSS",
    },
    "address_notification": {
        "label": "Address / Location Notification",
        "description": "Accused shall not change residential address without intimating the investigating officer.",
        "trigger_keywords": [
            "address", "residence", "change address", "change of residence", "intimate",
            "notify", "location", "domicile", "residential"
        ],
        "statutory_basis": "S.438(2) CrPC / S.482(2) BNSS — General Condition",
    },
    "surety": {
        "label": "Furnishing Surety / Personal Bond",
        "description": "Accused shall furnish surety bond or personal bond for the specified amount.",
        "trigger_keywords": [
            "surety", "bond", "personal bond", "bail bond", "furnish", "security",
            "sureties", "recognizance"
        ],
        "statutory_basis": "S.438(1) CrPC / S.482(1) BNSS",
    },
    "cooperation": {
        "label": "Cooperate with Investigation",
        "description": "Accused shall fully cooperate with the investigating officer and not obstruct the investigation.",
        "trigger_keywords": [
            "cooperate", "cooperation", "not obstruct", "assist", "investigation",
            "not hamper", "aid", "not interfere with investigation"
        ],
        "statutory_basis": "S.438(2)(i) CrPC / S.482(2)(i) BNSS",
    },
    "no_crime": {
        "label": "Not Commit Similar Offence",
        "description": "Accused shall not commit an offence similar to the offence in respect of which the anticipatory bail is sought.",
        "trigger_keywords": [
            "not commit", "similar offence", "not repeat", "similar crime", "not commit any offence",
            "reoffend", "recidivism"
        ],
        "statutory_basis": "S.438(2)(iii) CrPC / S.482(2)(iii) BNSS",
    },
    "general_court_supervision": {
        "label": "Court-Directed Supervision / Reporting",
        "description": "Accused shall appear before the jurisdictional magistrate / sessions court as directed.",
        "trigger_keywords": [
            "appear before court", "appear before magistrate", "report to court",
            "court supervision", "appear before sessions court", "appear before judge"
        ],
        "statutory_basis": "S.438(2) CrPC / S.482(2) BNSS — General Condition",
    },
}

# Conditions that are NOT permissible under anticipatory bail law
IMPERMISSIBLE_CONDITION_PATTERNS = [
    (r"\bdeposit\b.*\brupees\b", "Monetary deposit conditions are impermissible as bail courts cannot act as recovery agents (Dilip Singh v. State of M.P., LAWS(SC)-2021-1-41)."),
    (r"\bpay\b.*\bcompensation\b", "Compensation payment conditions are impermissible — anticipatory bail is not a civil remedy forum."),
    (r"\bsettle\b.*\bdispute\b", "Conditions requiring civil settlement of disputes are impermissible under S.438 CrPC / S.482 BNSS."),
    (r"\bdeposit\b.*\blakhs\b", "Monetary deposit conditions are impermissible as bail courts cannot act as recovery agents."),
    (r"\bdeposit\b.*\bcash\b", "Cash deposit conditions are impermissible under anticipatory bail law."),
    (r"\brepay\b", "Repayment conditions convert bail proceedings into recovery proceedings — impermissible."),
    (r"\bimmovable property\b.*\bsurrender\b", "Surrender of immovable property as a bail condition is not authorized under S.438(2) CrPC / S.482(2) BNSS."),
]


class BailConditionValidationResult:
    """Result of validating a single generated bail condition string."""

    def __init__(
        self,
        condition_text: str,
        is_permissible: bool,
        matched_category: Optional[str],
        rejection_reason: Optional[str] = None,
    ):
        self.condition_text = condition_text
        self.is_permissible = is_permissible
        self.matched_category = matched_category
        self.rejection_reason = rejection_reason

    def __repr__(self) -> str:
        return (
            f"BailConditionValidationResult("
            f"permissible={self.is_permissible}, "
            f"category={self.matched_category!r}, "
            f"text={self.condition_text!r})"
        )


class BailConditionValidator:
    """
    Closed-set bail condition validator.

    Validates every generated bail condition string against:
    1. The canonical permissible condition categories (Section 438(2) CrPC / Section 482(2) BNSS).
    2. The impermissible condition pattern blacklist (Dilip Singh v. State of M.P. and related precedents).

    Rejects or flags conditions outside the authorized statutory categories.
    """

    def validate_single(self, condition_text: str) -> BailConditionValidationResult:
        """
        Validates a single bail condition string.

        Returns:
            BailConditionValidationResult with permissibility verdict and matched category.
        """
        cond_lower = condition_text.strip().lower()

        # Step 1: Check against impermissible blacklist patterns first
        for pattern, reason in IMPERMISSIBLE_CONDITION_PATTERNS:
            if re.search(pattern, cond_lower):
                return BailConditionValidationResult(
                    condition_text=condition_text,
                    is_permissible=False,
                    matched_category=None,
                    rejection_reason=reason,
                )

        # Step 2: Check against permissible closed-set categories
        for cat_key, cat_info in PERMISSIBLE_BAIL_CONDITION_CATEGORIES.items():
            for keyword in cat_info["trigger_keywords"]:
                if keyword in cond_lower:
                    return BailConditionValidationResult(
                        condition_text=condition_text,
                        is_permissible=True,
                        matched_category=cat_info["label"],
                        rejection_reason=None,
                    )

        # Step 3: Not matched against permissible set — flag for manual review
        return BailConditionValidationResult(
            condition_text=condition_text,
            is_permissible=False,
            matched_category=None,
            rejection_reason=(
                f"Bail condition '{condition_text}' does not map to any authorized category "
                f"under Section 438(2) CrPC / Section 482(2) BNSS. "
                f"Permissible categories are: {', '.join(c['label'] for c in PERMISSIBLE_BAIL_CONDITION_CATEGORIES.values())}."
            ),
        )

    def validate_all(
        self, conditions: List[str]
    ) -> Tuple[List[BailConditionValidationResult], List[str]]:
        """
        Validates a list of bail conditions.

        Returns:
            Tuple of:
                - List of BailConditionValidationResult for every condition.
                - List of manual_review flag strings for impermissible/unmatched conditions.
        """
        results = []
        manual_review_flags = []

        for cond in conditions:
            result = self.validate_single(cond)
            results.append(result)
            if not result.is_permissible:
                manual_review_flags.append(
                    f"IMPERMISSIBLE_BAIL_CONDITION: '{cond}' — {result.rejection_reason}"
                )

        return results, manual_review_flags
