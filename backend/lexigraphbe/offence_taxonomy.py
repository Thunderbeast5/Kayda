"""
Offence taxonomy: maps ANY statute reference to broad offence categories, and derives gravity from punishment.

This replaces the keyword facets (land / deed / forgery ...), the disqualifying-facet lists (302 / 376 / 498A ...)
and the per-section gravity caps that used to live in the retriever and matcher. Nothing here is specific to one
input case: it is the structure of the IPC itself (its chapters), a table of special Acts, and the punishment
text already held in StatuteRepository.

Categories are used for two things:
  * category similarity between the input's charged offences and a precedent's charged offences
    (a murder precedent has no overlap with a cheating/forgery input, and vice-versa), and
  * default prosecution/defence argument themes for the retrieval profile.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# IPC chapter structure (sections inclusive). BNS / BNSS sections are first mapped back to IPC / CrPC through
# StatuteRepository, so one table covers both regimes.
# ---------------------------------------------------------------------------
_IPC_RANGES: List[Tuple[int, int, str]] = [
    (107, 120, "ABETMENT"),
    (120, 120, "CONSPIRACY"),            # 120A / 120B (letter suffix handled by numeric prefix)
    (121, 130, "OFFENCE_AGAINST_STATE"),
    (141, 160, "PUBLIC_ORDER"),
    (161, 171, "CORRUPTION"),
    (172, 190, "CONTEMPT_OF_AUTHORITY"),
    (191, 229, "FALSE_EVIDENCE_JUSTICE"),
    (230, 263, "COUNTERFEIT_COIN_STAMPS"),
    (268, 294, "PUBLIC_HEALTH_SAFETY_NUISANCE"),
    (295, 298, "RELIGION"),
    (299, 311, "HOMICIDE"),
    (312, 318, "MISCARRIAGE_CHILD"),
    (319, 338, "HURT"),
    (339, 358, "RESTRAINT_ASSAULT"),
    (359, 374, "KIDNAPPING_TRAFFICKING"),
    (375, 376, "SEXUAL_OFFENCE"),
    (377, 377, "SEXUAL_OFFENCE"),
    (354, 354, "SEXUAL_OFFENCE"),
    (378, 382, "THEFT"),
    (383, 389, "EXTORTION"),
    (390, 402, "ROBBERY_DACOITY"),
    (403, 409, "MISAPPROPRIATION_BREACH_OF_TRUST"),
    (410, 414, "STOLEN_PROPERTY"),
    (415, 420, "CHEATING"),
    (421, 424, "FRAUDULENT_TRANSFER"),
    (425, 440, "MISCHIEF"),
    (441, 462, "TRESPASS"),
    (463, 477, "FORGERY"),
    (478, 489, "TRADEMARK_CURRENCY"),
    (493, 498, "MARRIAGE_RELATED"),
    (499, 502, "DEFAMATION"),
    (503, 510, "INTIMIDATION_INSULT"),
]

# Individual IPC sections whose category is not obvious from their chapter (statute facts, not case facts).
_IPC_OVERRIDES: Dict[str, Set[str]] = {
    "120A": {"CONSPIRACY"}, "120B": {"CONSPIRACY"},
    "498A": {"MARRIAGE_CRUELTY"}, "304B": {"HOMICIDE", "MARRIAGE_CRUELTY"},
    "34": {"COMMON_INTENTION"}, "149": {"COMMON_INTENTION"}, "511": {"ATTEMPT"},
    "354A": {"SEXUAL_OFFENCE"}, "354B": {"SEXUAL_OFFENCE"}, "354C": {"SEXUAL_OFFENCE"}, "354D": {"SEXUAL_OFFENCE"},
    "493": {"MARRIAGE_RELATED"}, "494": {"MARRIAGE_RELATED"}, "496": {"MARRIAGE_RELATED"}, "497": {"MARRIAGE_RELATED"},
    "468": {"FORGERY", "CHEATING"},          # forgery *for the purpose of cheating*
    "471": {"FORGERY"}, "420": {"CHEATING"},
    # Rash / negligent endangerment is both an offence against the body and a public-safety offence.
    "336": {"HURT", "PUBLIC_HEALTH_SAFETY_NUISANCE"}, "337": {"HURT", "PUBLIC_HEALTH_SAFETY_NUISANCE"},
    "338": {"HURT", "PUBLIC_HEALTH_SAFETY_NUISANCE"},
}

# Special Acts, keyed by the normalised short name produced by PrecedentStatuteMatcher.normalize_act_name().
_SPECIAL_ACT_CATEGORY: Dict[str, str] = {
    "NDPS": "NARCOTICS", "PMLA": "MONEY_LAUNDERING", "PCA": "CORRUPTION", "UAPA": "TERRORISM",
    "POCSO": "SEXUAL_OFFENCE", "DPA": "MARRIAGE_CRUELTY", "SC/ST": "ATROCITIES", "IT": "CYBER",
    "JJ": "JUVENILE", "ARMS": "ARMS", "NI": "CHEQUE_DISHONOUR", "COMPANIES": "CORPORATE_FRAUD",
    "CUSTOMS": "CUSTOMS_SMUGGLING", "GST": "TAX_OFFENCE", "FEMA": "FOREIGN_EXCHANGE",
}
_SPECIAL_ACT_KEYWORDS: List[Tuple[str, str]] = [
    ("NEGOTIABLE INSTRUMENT", "CHEQUE_DISHONOUR"), ("NARCOTIC", "NARCOTICS"), ("MONEY LAUNDERING", "MONEY_LAUNDERING"),
    ("CORRUPTION", "CORRUPTION"), ("UNLAWFUL ACTIVITIES", "TERRORISM"), ("EXPLOSIVE", "ARMS"), ("ARMS ACT", "ARMS"),
    ("COMPANIES", "CORPORATE_FRAUD"), ("INFORMATION TECHNOLOGY", "CYBER"), ("CUSTOMS", "CUSTOMS_SMUGGLING"),
    ("GOODS AND SERVICES", "TAX_OFFENCE"), ("FOREIGN EXCHANGE", "FOREIGN_EXCHANGE"), ("DOWRY", "MARRIAGE_CRUELTY"),
    ("SEXUAL OFFENCES", "SEXUAL_OFFENCE"), ("SCHEDULED CASTES", "ATROCITIES"), ("JUVENILE", "JUVENILE"),
]

# Categories that frequently co-occur and carry little information about the nature of the case.
ANCILLARY = {"CONSPIRACY": 0.3, "ABETMENT": 0.3, "COMMON_INTENTION": 0.1, "ATTEMPT": 0.3}


def _numeric_part(section: str) -> Optional[int]:
    m = re.match(r"\s*(\d+)", str(section or ""))
    return int(m.group(1)) if m else None


def ipc_categories(section: str) -> Set[str]:
    sec = re.sub(r"[\s\-]", "", str(section or "").upper())
    base = re.sub(r"\(.*", "", sec)
    if base in _IPC_OVERRIDES:
        return set(_IPC_OVERRIDES[base])
    n = _numeric_part(base)
    if n is None:
        return set()
    cats = {c for lo, hi, c in _IPC_RANGES if lo <= n <= hi}
    return cats


def special_act_category(act_norm: str) -> Optional[str]:
    a = (act_norm or "").upper()
    if a in _SPECIAL_ACT_CATEGORY:
        return _SPECIAL_ACT_CATEGORY[a]
    for kw, cat in _SPECIAL_ACT_KEYWORDS:
        if kw in a:
            return cat
    return None


def categories_for(act_norm: str, section: str) -> Set[str]:
    """Categories for a CANONICAL (old-regime) statute reference. Procedural/evidence provisions give none."""
    a = (act_norm or "").upper()
    if a in ("IPC", "BNS"):
        return ipc_categories(section)
    if a in ("CRPC", "BNSS", "IEA", "BSA"):
        return set()
    cat = special_act_category(a)
    return {cat} if cat else set()


def category_vector(refs: Iterable[Tuple[str, str, float]]) -> Dict[str, float]:
    """[(act, section, weight)] -> {category: weight}; ancillary categories are down-weighted."""
    vec: Dict[str, float] = {}
    for act, sec, w in refs:
        for c in categories_for(act, sec):
            vec[c] = max(vec.get(c, 0.0), w * ANCILLARY.get(c, 1.0))
    return vec


# Sibling categories share a "family": a cheating precedent is partly relevant to a forgery input, a murder
# precedent is not. Family membership is part of the structure of the criminal law, not of any case.
_FAMILIES: Dict[str, Set[str]] = {
    "FAMILY_FRAUD": {"CHEATING", "FORGERY", "FRAUDULENT_TRANSFER", "MISAPPROPRIATION_BREACH_OF_TRUST",
                     "CORPORATE_FRAUD", "CHEQUE_DISHONOUR", "TRADEMARK_CURRENCY"},
    "FAMILY_VIOLENCE": {"HOMICIDE", "HURT", "RESTRAINT_ASSAULT", "MISCARRIAGE_CHILD"},
    "FAMILY_SEXUAL": {"SEXUAL_OFFENCE", "KIDNAPPING_TRAFFICKING"},
    "FAMILY_PROPERTY_CRIME": {"THEFT", "EXTORTION", "ROBBERY_DACOITY", "STOLEN_PROPERTY", "MISCHIEF", "TRESPASS"},
    "FAMILY_ECONOMIC_REGULATORY": {"MONEY_LAUNDERING", "CORRUPTION", "TAX_OFFENCE", "FOREIGN_EXCHANGE", "CUSTOMS_SMUGGLING"},
    "FAMILY_MARRIAGE": {"MARRIAGE_CRUELTY", "MARRIAGE_RELATED"},
}
FAMILY_CREDIT = 0.5


def _expand(vec: Dict[str, float]) -> Dict[str, float]:
    out = dict(vec)
    for fam, members in _FAMILIES.items():
        w = max((vec[c] for c in members if c in vec), default=0.0)
        if w:
            out[fam] = max(out.get(fam, 0.0), FAMILY_CREDIT * w)
    return out


def category_similarity(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Weighted Jaccard over categories (+ family credit), 0..1. Murder vs cheating -> 0; cheating vs forgery -> >0."""
    if not a or not b:
        return 0.0
    a, b = _expand(a), _expand(b)
    keys = set(a) | set(b)
    inter = sum(min(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    union = sum(max(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    return inter / union if union else 0.0


# ---------------------------------------------------------------------------
# Gravity from punishment (replaces per-section caps such as "423 -> 0.4")
# ---------------------------------------------------------------------------

def max_years_from_text(text: Optional[str]) -> Optional[float]:
    """'7 Years' -> 7, 'Life Imprisonment (or up to 10 Years)' -> 99, 'Death' -> 99, None -> None."""
    if not text:
        return None
    t = str(text).lower()
    if "life" in t or "death" in t:
        return 99.0
    m = re.findall(r"(\d+(?:\.\d+)?)\s*(?:year|yr)", t)
    if m:
        return max(float(x) for x in m)
    m = re.findall(r"(\d+(?:\.\d+)?)\s*month", t)
    if m:
        return max(float(x) for x in m) / 12.0
    return None


def gravity_factor(max_years: Optional[float]) -> float:
    """
    0.4 for <=2 years, rising linearly to 1.0 at >=7 years; unknown punishment -> 1.0 (no penalty).
    7 years is the CrPC 41A / Arnesh Kumar threshold, so it is a legal boundary, not a tuned constant.
    """
    if max_years is None:
        return 1.0
    if max_years >= 7:
        return 1.0
    if max_years <= 2:
        return 0.4
    return 0.4 + 0.6 * (max_years - 2) / 5.0


# ---------------------------------------------------------------------------
# Default argument themes per category (generic anticipatory-bail factors + category-specific hooks)
# ---------------------------------------------------------------------------
GENERIC_THEMES = {
    "prosecution": [
        "need for custodial interrogation / recovery",
        "gravity of the allegations and role of the accused",
        "risk of tampering with evidence or influencing witnesses",
        "antecedents and likelihood of absconding",
    ],
    "defense": [
        "no need for custodial interrogation; accused cooperating with investigation",
        "false implication / mala fides; personal liberty under Article 21",
        "no flight risk; roots in the community",
        "conditions can adequately protect the investigation",
    ],
}

CATEGORY_THEMES: Dict[str, Dict[str, List[str]]] = {
    "CHEATING": {
        "prosecution": ["dishonest intention at the inception of the transaction"],
        "defense": ["civil / commercial dispute given a criminal colour; no dishonest intention at inception"],
    },
    "FORGERY": {
        "prosecution": ["authenticity of documents and trail of the forged instrument"],
        "defense": ["genuineness of documents; documents already seized so custody is unnecessary"],
    },
    "MISAPPROPRIATION_BREACH_OF_TRUST": {
        "prosecution": ["entrustment and dishonest misappropriation; tracing funds"],
        "defense": ["accounting dispute between parties; repayment / settlement"],
    },
    "HOMICIDE": {
        "prosecution": ["gravity of offence against the person; role in the incident; recovery of weapon"],
        "defense": ["role not attributable; no motive or recovery requiring custody"],
    },
    "NARCOTICS": {
        "prosecution": ["statutory bail restrictions and commercial quantity"],
        "defense": ["quantity and compliance with procedural safeguards"],
    },
    "MARRIAGE_CRUELTY": {
        "prosecution": ["allegations of cruelty / dowry demand and entrustment of stridhan"],
        "defense": ["omnibus allegations against relatives; matrimonial discord; arrest safeguards"],
    },
    "CHEQUE_DISHONOUR": {
        "prosecution": ["dishonour and statutory presumption"],
        "defense": ["compoundable commercial dispute; legally enforceable debt"],
    },
}


def themes_for(categories: Iterable[str]) -> Dict[str, List[str]]:
    out = {"prosecution": list(GENERIC_THEMES["prosecution"]), "defense": list(GENERIC_THEMES["defense"])}
    for c in categories:
        for role in out:
            for t in CATEGORY_THEMES.get(c, {}).get(role, []):
                if t not in out[role]:
                    out[role].insert(0, t)
    return out
