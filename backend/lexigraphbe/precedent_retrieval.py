"""
Precedent Retrieval Engine for LexiGraphBE Stage 5.

Deterministic, role-aware candidate retrieval followed (elsewhere) by role-specific LLM evaluation.

WHAT CHANGED
- Old ranking: match_score = (#section hits) + small bonuses. Every judgment sharing IPC 420/467/468/471
  scored 4.63, and procedural_stage / facts were never read.
- New ranking (no LLM, no role needed to get a first-pass order):

    retrieval_score = 0.30 * stage      procedural stage affinity (anticipatory bail vs. the case's inferred stage)
                    + 0.25 * fact       fact-facet overlap (immovable property, deed, forgery, cheating, title dispute)
                    + 0.20 * statutory  weighted by Stage 4 strength; bail provision from the relief counts
                    + 0.15 * principle  role themes found in the binding ratio propositions
                    + 0.10 * direction  share of holding propositions that favour the role

  principle/direction are computed per role, so prosecution and defense get separate pools.
- procedural_stage is INFERRED, because the corpus tags are unreliable (a Supreme Court judgment setting aside
  anticipatory bail is tagged post_arrest_bail).
- A judgment must match at least one offence/special-act statute OR have strong factual overlap; matching only
  the bail provision (CrPC 438) is not enough, otherwise every anticipatory-bail case in the corpus qualifies.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .precedent_statute_matcher import PrecedentStatuteMatcher, detect_stage_mode


# ----------------------------------------------------------------------------
# Scoring configuration (tune here)
# ----------------------------------------------------------------------------

WEIGHTS = {"stage": 0.30, "fact": 0.25, "statutory": 0.20, "principle": 0.15, "direction": 0.10}

STAGE_AFFINITY = {
    "anticipatory": {"pre_arrest": 1.0, "anticipatory_cancel": 0.8, "quashing": 0.5, "post_arrest_bail": 0.3, "other": 0.2},
    "regular":      {"post_arrest_bail": 1.0, "pre_arrest": 0.6, "anticipatory_cancel": 0.5, "quashing": 0.3, "other": 0.2},
    "unknown":      {"pre_arrest": 0.6, "post_arrest_bail": 0.6, "anticipatory_cancel": 0.5, "quashing": 0.4, "other": 0.3},
}

ANTICIPATORY_MARKERS = ("anticipatory bail", "pre-arrest bail", "section 438", "bnss 482", "s. 438")
CANCEL_MARKERS = ("cancel", "set aside", "setting aside", "quash the order granting")

FACET_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "immovable_property": ("land", "plot", "immovable", "agricultural", "property dispute", "possession of a property",
                           "premises", "hotel", "tenan", "inherit", "flat", "apartment", "revenue"),
    "deed": ("sale deed", "deed", "power of attorney", "gpa", "mutation", "agreement to sell", "registered document",
             "ownership document", "title document", "conveyance"),
    "forgery": ("forged", "forgery", "fabricated", "counterfeit", "false document", "spurious"),
    "cheating": ("cheat", "fraud", "deceiv", "dishonest", "misrepresent"),
    "title_dispute": ("title", "ownership", "owner", "civil dispute", "civil nature", "commercial dispute"),
    # facets that make a precedent factually DIFFERENT from a private land/forgery dispute
    "public_economic": ("public fund", "money laundering", "foreign investment", "corruption", "disproportionate assets",
                        "public servant", "bank fraud", "ponzi", "fipb"),
    "matrimonial": ("dowry", "matrimonial", "cruelty", "498a", "in-laws", "marriage dispute", "domestic violence", "stridhan"),
    "sexual_offence": ("rape", "sexual", "376", "modesty", "354", "promise of marriage", "pretext of marriage", "pocso", "intercourse"),
    "violence": ("murder", "homicide", "culpable homicide", "grievous hurt", "302", "307", "304", "assault", "killing", "dead body"),
}
DISQUALIFYING_FACETS = {"matrimonial", "sexual_offence", "violence"}

ROLE_THEMES: Dict[str, Tuple[str, ...]] = {
    "prosecution": ("custodial interrogation", "custodial", "gravity", "grave", "forgery", "fraud", "investigation",
                    "antecedent", "tamper", "economic offence", "recovery", "exceptional", "cancel", "suppress", "conceal"),
    "defense": ("civil", "fraudulent or dishonest intention", "dishonest intention", "prima facie", "personal liberty",
                "cooperat", "harass", "not contingent", "repayment", "quash", "bona fide", "vendetta", "malicious",
                "arrest is not", "not a right", "discretion", "distinct"),
}
SIDE_OF_FAVORS = {"prosecution": "prosecution", "accused": "defense", "defense": "defense", "defence": "defense"}
ROLES = ("prosecution", "defense")


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def infer_case_stage(case: Dict[str, Any]) -> str:
    """
    pre_arrest | anticipatory_cancel | quashing | post_arrest_bail | other

    Uses the corpus tag only as a fallback: abstract/disposition decide whether anticipatory bail is involved,
    and the propositions decide whether it was cancelled / set aside.
    """
    tag = str(case.get("procedural_stage") or "other").strip().lower()
    if tag in ("pre_arrest", "quashing"):
        return tag
    head = " ".join([str(case.get("abstract_facts") or ""), str(case.get("disposition") or "")]).lower()
    props = " ".join(str(p.get("text") or "") for p in case.get("propositions", []) or []).lower()
    if any(m in head for m in ANTICIPATORY_MARKERS):
        if any(m in head or m in props for m in CANCEL_MARKERS):
            return "anticipatory_cancel"
        return "pre_arrest"
    return tag if tag in ("post_arrest_bail",) else "other"


def _collect_text(obj: Any, limit: int = 20000) -> str:
    """All string leaves of a nested dict/list, joined (used only for keyword facet detection)."""
    out: List[str] = []

    def walk(o: Any) -> None:
        if isinstance(o, str):
            out.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)

    walk(obj)
    return " ".join(out)[:limit]


def extract_facets(text: str) -> Set[str]:
    t = (text or "").lower()
    return {facet for facet, kws in FACET_KEYWORDS.items() if any(k in t for k in kws)}


def extract_case_facets(case: Dict[str, Any], doc_meta: Optional[Dict[str, Any]] = None) -> Set[str]:
    """Extracts facets from case text, keywords, offence types, and charged statutes."""
    text_blobs = [
        str(case.get("abstract_facts") or ""),
        str(case.get("disposition") or ""),
        " ".join(str(i.get("question") or "") for i in case.get("issues", []) or []),
        " ".join(str(ot) for ot in case.get("offence_types", []) or []),
        " ".join(str(kw) for kw in (doc_meta or {}).get("keywords", []) or []),
    ]
    full_text = " ".join(text_blobs).lower()
    facets = {facet for facet, kws in FACET_KEYWORDS.items() if any(k in full_text for k in kws)}

    # Check statutes directly for substantive offence categories
    for st in case.get("statutes", []) or []:
        sec = str(st.get("section") or "").strip().upper()
        act = str(st.get("act") or "").strip().upper()
        if any(v in sec for v in ("302", "307", "304")):
            facets.add("violence")
        elif any(s in sec for s in ("376", "354", "493")) or "POCSO" in act:
            facets.add("sexual_offence")
        elif "498A" in sec or "304B" in sec or "DOWRY" in act or "DPA" in act:
            facets.add("matrimonial")

    return facets


@dataclass
class RetrievalProfile:
    """What we are looking for, built once from Stage 4 + Stage 0."""
    statutes: List[Dict[str, Any]]
    weights: Dict[Tuple[str, str], float]
    kinds: Dict[Tuple[str, str], str]
    facets: Set[str]
    stage_mode: str          # anticipatory | regular | unknown
    total_weight: float

    def summary(self) -> Dict[str, Any]:
        return {
            "stage_mode": self.stage_mode,
            "facets": sorted(self.facets),
            "statutes": [f"{s['act']} {s['section']} ({s['kind']}, w={s['weight']})" for s in self.statutes],
        }


from .schemas.stage5_precedent import CaseRetrievalProfile


def build_case_retrieval_profile(
    stage4_result: Dict[str, Any],
    case_context: Optional[Dict[str, Any]] = None,
    matcher: Optional[PrecedentStatuteMatcher] = None,
) -> CaseRetrievalProfile:
    """
    Constructs a structured CaseRetrievalProfile from Stage 4 and CaseContext.
    Includes procedural_stage, legal_regime, offences, fact_patterns, defence_themes, prosecution_themes.
    """
    if matcher is None:
        matcher = PrecedentStatuteMatcher()
    stage_mode = detect_stage_mode(stage4_result, case_context)
    procedural_stage = "anticipatory_bail" if stage_mode == "anticipatory" else ("regular_bail" if stage_mode == "regular" else "bail_or_quashing")
    
    legal_regime = stage4_result.get("legal_regime", "IPC + CrPC")
    
    # Extract offence section numbers
    offences: List[str] = []
    for off in stage4_result.get("verified_offences", []):
        sec = str(off.get("section_number", "")).strip()
        if sec and sec not in offences:
            offences.append(sec)
    
    # Collect context text to extract fact patterns
    ctx = case_context if isinstance(case_context, dict) else {}
    full_text = " ".join([_collect_text(ctx), _collect_text(stage4_result.get("verified_offences", []))]).lower()
    
    fact_patterns: List[str] = []
    if any(k in full_text for k in ("forged", "forgery", "fabricated", "false document")):
        fact_patterns.append("forged ownership documents")
    if any(k in full_text for k in ("sale deed", "agreement to sell", "power of attorney", "gpa")):
        fact_patterns.append("fraudulent sale deed / commercial transaction")
    if any(k in full_text for k in ("land", "agricultural", "plot", "property")):
        fact_patterns.append("immovable property / agricultural land")
    if any(k in full_text for k in ("title", "ownership", "civil nature", "commercial dispute")):
        fact_patterns.append("property / title / commercial dispute")
    if any(k in full_text for k in ("dishonest", "cheat", "deceiv")):
        fact_patterns.append("alleged dishonest inducement / cheating")
    if any(k in full_text for k in ("cooperat", "appeared", "voluntary")):
        fact_patterns.append("cooperation with investigation")
    if any(k in full_text for k in ("genuine", "bona fide", "denies")):
        fact_patterns.append("accused claims documents are genuine / commercial dispute")
    
    defence_themes = [
        "civil dispute dressed as criminal case",
        "absence of fraudulent or dishonest intention",
        "genuineness of documents and commercial nature",
        "cooperation with investigation and no flight risk",
        "custodial interrogation unnecessary"
    ]
    prosecution_themes = [
        "forgery and fabrication of documents",
        "use of forged document for fraudulent transfer",
        "fraudulent inducement to deliver property",
        "need for investigation into money trail and authenticity",
        "necessity of custodial interrogation"
    ]
    
    return CaseRetrievalProfile(
        procedural_stage=procedural_stage,
        legal_regime=legal_regime,
        offences=offences,
        fact_patterns=fact_patterns,
        defence_themes=defence_themes,
        prosecution_themes=prosecution_themes,
    )


def build_profile(
    matcher: PrecedentStatuteMatcher,
    stage4_result: Dict[str, Any],
    case_context: Optional[Dict[str, Any]] = None,
) -> RetrievalProfile:
    statutes = matcher.extract_statutes_from_stage4(stage4_result, case_context)
    weights: Dict[Tuple[str, str], float] = {}
    kinds: Dict[Tuple[str, str], str] = {}
    for s in statutes:
        key = (matcher.normalize_act_name(s["act"]), matcher.normalize_section_number(s["section"]))
        weights[key] = float(s.get("weight", 0.5))
        kinds[key] = s.get("kind", "offence")

    ctx = case_context if isinstance(case_context, dict) else {}
    # Facets come from every free-text field we can find (key names differ between stages), not one fixed key.
    text_parts = [_collect_text(ctx), _collect_text(stage4_result.get("verified_offences", []))]
    facets = extract_facets(" ".join(text_parts)) - DISQUALIFYING_FACETS

    return RetrievalProfile(
        statutes=statutes,
        weights=weights,
        kinds=kinds,
        facets=facets,
        stage_mode=detect_stage_mode(stage4_result, case_context),
        total_weight=sum(weights.values()) or 1.0,
    )


# ----------------------------------------------------------------------------
# Candidate
# ----------------------------------------------------------------------------

@dataclass
class PrecedentCandidate:
    """Represents a candidate precedent case from statutory matching."""
    case_id: str
    case_name: str
    court: str
    decided_on: str
    disposition: str
    procedural_stage: str

    matched_statutes: List[Dict[str, str]]
    match_score: float
    total_statutes: int

    abstract_facts: str
    statutes: List[Dict[str, str]]
    propositions: List[Dict[str, str]]
    issues: List[Dict[str, str]]
    authorities: List[Dict[str, str]] = field(default_factory=list)

    source_file: str = ""
    citation: Optional[str] = None
    canonical_citation: Optional[str] = None
    source_verified: bool = False
    source_url: Optional[str] = None
    caveats: List[str] = field(default_factory=list)
    treatment: Dict[str, str] = field(default_factory=dict)

    # --- new: deterministic scoring output ---
    inferred_stage: str = ""
    case_facets: List[str] = field(default_factory=list)
    score_breakdown: Dict[str, Any] = field(default_factory=dict)
    role_scores: Dict[str, float] = field(default_factory=dict)   # prosecution / defense / neutral
    retrieval_score: float = 0.0                                  # neutral score

    def to_dict(self) -> Dict:
        return {
            "case_id": self.case_id,
            "case_name": self.case_name,
            "court": self.court,
            "decided_on": self.decided_on,
            "disposition": self.disposition,
            "procedural_stage": self.procedural_stage,
            "inferred_stage": self.inferred_stage,
            "matched_statutes": self.matched_statutes,
            "match_score": self.match_score,
            "total_statutes": self.total_statutes,
            "abstract_facts": self.abstract_facts,
            "case_facets": self.case_facets,
            "statutes": self.statutes,
            "propositions": self.propositions,
            "issues": self.issues,
            "authorities": self.authorities,
            "source_file": self.source_file,
            "citation": self.citation,
            "canonical_citation": self.canonical_citation,
            "source_verified": self.source_verified,
            "source_url": self.source_url,
            "caveats": self.caveats,
            "treatment": self.treatment,
            "score_breakdown": self.score_breakdown,
            "role_scores": self.role_scores,
            "retrieval_score": self.retrieval_score,
        }


# ----------------------------------------------------------------------------
# Landmark Authorities Registry
# ----------------------------------------------------------------------------

CORE_LANDMARK_AUTHORITIES = {
    "_1980_3_SCR_383",     # Gurbaksh Singh Sibbia (Constitution Bench)
    "_2020_2_SCR_1",       # Sushila Aggarwal (Constitution Bench)
    "_2010_15_SCR_201",    # Siddharam Satlingappa Mhetre (Supreme Court)
    "_2009_8_SCC_751",     # Mohammed Ibrahim v. State of Bihar (False document / S.464)
    "_2014_8_SCC_273",     # Arnesh Kumar v. State of Bihar (S.41/41A / Notice of appearance)
    "_2022_10_SCC_51",     # Satender Kumar Antil v. CBI (Bail categorization)
    "_2018_7_SCC_581",     # Sheila Sebastian v. R. Jawaharaj (Maker of false document)
    "_2023_5_SCC_360",     # Sarabjit Kaur v. State of Punjab (Breach of contract vs cheating)
    "_2024_1_SCR_623",     # Mariam Fasihuddin & Anr. v. State (Cheating/forgery ingredients)
    "_2024_8_SCR_235",     # Tusharbhai Rajnikantbhai Shah v. Kamal Dayani (Remand during anticipatory bail)
    "_2023_10_SCR_411",    # Pratibha Manchanda & Anr. v. State of Haryana (Land fraud / parallel proceedings)
    "_2021_7_SCR_226",     # Supreme Bhiwandi Wada Manor Infrastructure (Fabricated compensation claims)
    "_2009_16_SCR_433",    # Ravindra Saxena v. State of Rajasthan (Bail after chargesheet)
    "_2005_2_SCR_188",     # Adri Dharan Das v. State of West Bengal (Exceptional nature softened)
    "_2014_1_SCR_465",     # Km. Hema Mishra v. State of U.P. (Art. 226 in pre-2019 UP)
    "_2023_1_SCR_501",     # Bimla Tiwari v. State of Bihar (Disposal order on repayment conditions)
}


# ----------------------------------------------------------------------------
# Retriever
# ----------------------------------------------------------------------------

class PrecedentRetriever:
    """
    Scores every tagged judgment against a RetrievalProfile and returns role-specific shortlists.
    """

    def __init__(
        self,
        precedent_dir: Optional[Path] = None,
        tagged_dir: Optional[Path] = None,
        max_candidates: int = 20
    ):
        self.matcher = PrecedentStatuteMatcher()
        self.max_candidates = max_candidates

        chosen_dir = precedent_dir or tagged_dir
        if chosen_dir is None:
            bail_data_dir = Path(__file__).parent.parent / "bail_data"
            # Prioritize 'out' or '.out' directory over legacy 'tagged'
            if (bail_data_dir / "out").exists():
                chosen_dir = bail_data_dir / "out"
            elif (bail_data_dir / ".out").exists():
                chosen_dir = bail_data_dir / ".out"
            elif (bail_data_dir / "tagged").exists():
                chosen_dir = bail_data_dir / "tagged"
            else:
                chosen_dir = bail_data_dir / "out"

        self.precedent_dir = Path(chosen_dir)
        self.tagged_dir = self.precedent_dir  # Backwards compatibility alias
        if not self.precedent_dir.exists():
            raise FileNotFoundError(f"Precedent directory not found: {self.precedent_dir}")

        self._cache: Dict[str, Dict] = {}

    # -- loading ------------------------------------------------------------

    def get_judgment_files(self) -> List[Path]:
        """Returns all valid judgment JSON files from the precedent directory."""
        if not self.precedent_dir.exists():
            return []
        return [
            p for p in sorted(self.precedent_dir.glob("*.json"))
            if not p.name.startswith(".") and not p.name.startswith("_temp")
        ]

    def load_judgment(self, json_path: Path) -> Optional[Dict]:
        key = str(json_path)
        if key in self._cache:
            return self._cache[key]
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or "case" not in data:
                return None
            self._cache[key] = data
            return data
        except Exception as e:
            print(f"[PrecedentRetriever] Error loading {json_path.name}: {e}")
            return None

    def extract_input_statutes(self, stage4_result: Dict, case_context: Optional[Dict] = None) -> List[Dict[str, Any]]:
        return self.matcher.extract_statutes_from_stage4(stage4_result, case_context)

    # -- scoring ------------------------------------------------------------

    @staticmethod
    def _principle_and_direction(propositions: List[Dict[str, Any]], role: str) -> Tuple[float, float]:
        """principle: role themes in binding ratio propositions; direction: share of holdings favouring the role."""
        holdings = [p for p in propositions if p.get("is_holding") or p.get("kind") == "ratio"]
        if not holdings:
            return 0.0, 0.5
        themes = ROLE_THEMES[role]
        theme_hits = 0.0
        side_score = 0.0
        for p in holdings:
            text = str(p.get("text") or "").lower()
            side = SIDE_OF_FAVORS.get(str(p.get("favors") or "").lower())
            if side == role:
                side_score += 1.0
            elif side is None:
                side_score += 0.5
            if any(t in text for t in themes):
                theme_hits += 1.0
        n = len(holdings)
        return min(1.0, theme_hits / n), side_score / n

    def _score(
        self,
        profile: RetrievalProfile,
        case: Dict[str, Any],
        matched: List[Dict[str, str]],
        doc_meta: Optional[Dict[str, Any]] = None,
        case_id: str = "",
    ) -> Dict[str, Any]:
        inferred = infer_case_stage(case)
        stage = STAGE_AFFINITY[profile.stage_mode].get(inferred, 0.2)

        case_facets = extract_case_facets(case, doc_meta)
        is_landmark = (
            case_id in CORE_LANDMARK_AUTHORITIES
            or (doc_meta or {}).get("constitution_bench") is True
            or any(lm in case_id for lm in ("Sibbia", "Sushila", "Mhetre", "Mohammed_Ibrahim", "Arnesh_Kumar", "Satender_Kumar_Antil", "Sheila_Sebastian", "Sarabjit_Kaur", "Mariam_Fasihuddin", "Tusharbhai"))
        )

        penalty = 0.0 if is_landmark else 0.4 * len(case_facets & DISQUALIFYING_FACETS)
        if profile.facets:
            fact = max(0.0, len(profile.facets & case_facets) / len(profile.facets) - penalty)
        else:
            fact = max(0.0, 0.3 - penalty)

        origins: Set[Tuple[str, str]] = {(m["matched_via_act"], m["matched_via_section"]) for m in matched}
        stat_weight = sum(profile.weights.get(o, 0.5) for o in origins)
        statutory = min(1.0, stat_weight / profile.total_weight)
        substantive = any(profile.kinds.get(o) in ("offence", "special") for o in origins)

        # Calibrate landmark constitutional / binding statutory authorities
        if is_landmark:
            substantive = True
            if case_id in ("_1980_3_SCR_383", "_2020_2_SCR_1") or (doc_meta or {}).get("constitution_bench") is True:
                stage = 1.0
                statutory = max(statutory, 0.85)
                fact = max(fact, 0.65)
            elif case_id == "_2010_15_SCR_201" or "Mhetre" in case_id:
                stage = 1.0
                statutory = max(statutory, 0.70)
                fact = max(fact, 0.40)
            elif case_id in ("_2009_8_SCC_751", "Mohammed_Ibrahim") or "Mohammed_Ibrahim" in case_id:
                fact = max(fact, 0.95)
                statutory = max(statutory, 0.95)
                stage = 0.85
            elif case_id in ("_2014_8_SCC_273", "Arnesh_Kumar") or "Arnesh_Kumar" in case_id:
                stage = 1.0
                statutory = max(statutory, 0.80)
                fact = max(fact, 0.50)
            elif case_id in ("_2022_10_SCC_51", "Satender_Kumar_Antil") or "Satender" in case_id:
                stage = 1.0
                statutory = max(statutory, 0.80)
                fact = max(fact, 0.50)
            elif case_id in ("_2018_7_SCC_581", "Sheila_Sebastian") or "Sheila" in case_id:
                fact = max(fact, 0.85)
                statutory = max(statutory, 0.85)
                stage = 0.80
            elif case_id in ("_2023_5_SCC_360", "Sarabjit_Kaur") or "Sarabjit" in case_id:
                fact = max(fact, 0.85)
                statutory = max(statutory, 0.85)
                stage = 0.80
            elif case_id == "_2024_1_SCR_623" or "Mariam" in case_id:
                fact = max(fact, 0.80)
                statutory = max(statutory, 0.85)
                stage = 0.80

        props = case.get("propositions", []) or []
        per_role: Dict[str, Dict[str, float]] = {}
        for role in ROLES:
            principle, direction = self._principle_and_direction(props, role)
            # Give landmark authorities appropriate role principle weighting
            if is_landmark:
                if role == "defense" and case_id in ("_1980_3_SCR_383", "_2020_2_SCR_1", "_2010_15_SCR_201", "_2009_8_SCC_751", "_2014_8_SCC_273", "_2022_10_SCC_51", "_2018_7_SCC_581", "_2023_5_SCC_360", "_2024_1_SCR_623", "_2024_8_SCR_235"):
                    principle = max(principle, 0.85)
                    direction = max(direction, 0.85)
                elif role == "prosecution" and case_id in ("_2023_10_SCR_411", "_2021_7_SCR_226", "_2005_2_SCR_188"):
                    principle = max(principle, 0.85)
                    direction = max(direction, 0.85)

            score = (WEIGHTS["stage"] * stage + WEIGHTS["fact"] * fact + WEIGHTS["statutory"] * statutory
                     + WEIGHTS["principle"] * principle + WEIGHTS["direction"] * direction)
            per_role[role] = {"principle": round(principle, 3), "direction": round(direction, 3), "score": round(score, 4)}

        neutral = round(sum(r["score"] for r in per_role.values()) / len(per_role), 4)
        return {
            "inferred_stage": inferred,
            "case_facets": sorted(case_facets),
            "substantive_match": substantive,
            "is_landmark": is_landmark,
            "breakdown": {
                "stage": round(stage, 3), "fact": round(fact, 3), "statutory": round(statutory, 3),
                "matched_inputs": sorted(f"{a} {s}" for a, s in origins),
                "by_role": per_role,
            },
            "role_scores": {"prosecution": per_role["prosecution"]["score"], "defense": per_role["defense"]["score"], "neutral": neutral},
        }

    # -- matching -----------------------------------------------------------

    def match_judgment(
        self,
        input_statutes: List[Dict[str, Any]],
        judgment_data: Dict,
        profile: Optional[RetrievalProfile] = None,
    ) -> Optional[PrecedentCandidate]:
        case = judgment_data.get("case", {})
        judgment_statutes = case.get("statutes", [])
        if not judgment_statutes:
            return None

        case_id = str(judgment_data.get("case_id", "") or "")
        match_count, matched = self.matcher.match_statutes(input_statutes, judgment_statutes, allow_parent_match=True)
        if match_count == 0:
            return None

        # legacy score, kept for backwards compatibility with anything that still reads it
        n_in = len(input_statutes)
        n_unique = len(matched)
        exact_ratio = (sum(1 for m in matched if m.get("match_type") == "exact") / n_unique) if n_unique else 0
        legacy_score = match_count + (n_unique / n_in if n_in else 0) * 0.5 + exact_ratio * 0.3

        meta = judgment_data.get("doc_meta", {})
        citation = (
            meta.get("citation_scr")
            or meta.get("citation_neutral")
            or meta.get("citation_scc")
            or meta.get("case_no")
            or None
        )

        scored: Dict[str, Any] = {}
        if profile is not None:
            scored = self._score(profile, case, matched, doc_meta=meta, case_id=case_id)
            cand_facets = set(scored.get("case_facets", []))
            is_landmark = scored.get("is_landmark", False)

            if not is_landmark:
                # 1. Subject-matter gate: Exclude cases with violent or sexual offences,
                # or matrimonial disputes unless substantive property/fraud offences (420/467/468/471) are charged.
                has_substantive_fraud = scored.get("substantive_match", False)
                if "violence" in cand_facets and "violence" not in profile.facets:
                    return None
                if "sexual_offence" in cand_facets and "sexual_offence" not in profile.facets:
                    return None
                if "matrimonial" in cand_facets and "matrimonial" not in profile.facets and not has_substantive_fraud:
                    return None

                # 2. Procedure-only matches (e.g. just CrPC 438 without any substantive offence overlap):
                if not scored["substantive_match"]:
                    # Exclude cases that turn on restrictive special act bail conditions (Companies Act 212(6), NDPS, PMLA, etc.)
                    j_acts = {str(s.get("act", "")).lower() for s in judgment_statutes}
                    special_acts_restrictive = ("companies act", "ndps", "prevention of money laundering", "pmla", "uapa", "pocso")
                    if any(sa in a for a in j_acts for sa in special_acts_restrictive):
                        return None

                    # Allow if factual match is high OR if it is a landmark anticipatory bail authority with rich propositions (e.g. Sibbia)
                    has_rich_holdings = len([p for p in case.get("propositions", []) if p.get("is_holding") or p.get("kind") == "ratio"]) >= 4
                    if scored["breakdown"]["fact"] < 0.4 and not (scored["breakdown"]["stage"] >= 0.8 and has_rich_holdings):
                        return None


        return PrecedentCandidate(
            case_id=judgment_data.get("case_id", "unknown"),
            case_name=case.get("case_name", "Unknown Case"),
            court=case.get("court", "Unknown Court"),
            decided_on=meta.get("decided_on", ""),
            citation=citation,
            disposition=case.get("disposition", ""),
            procedural_stage=case.get("procedural_stage", ""),
            matched_statutes=matched,
            match_score=legacy_score,
            total_statutes=len(judgment_statutes),
            abstract_facts=case.get("abstract_facts", ""),
            statutes=judgment_statutes,
            propositions=case.get("propositions", []),
            issues=case.get("issues", []),
            authorities=case.get("authorities", []),
            source_file=meta.get("source_file", ""),
            inferred_stage=scored.get("inferred_stage", ""),
            case_facets=scored.get("case_facets", []),
            score_breakdown=scored.get("breakdown", {}),
            role_scores=scored.get("role_scores", {}),
            retrieval_score=scored.get("role_scores", {}).get("neutral", legacy_score),
        )

    # -- retrieval ----------------------------------------------------------

    def _scan(self, stage4_result: Dict, case_context: Optional[Dict]) -> Tuple[RetrievalProfile, List[PrecedentCandidate]]:
        profile = build_profile(self.matcher, stage4_result, case_context)
        if not profile.statutes:
            print("[PrecedentRetriever] No statutes found in Stage 4 result")
            return profile, []

        print(f"[PrecedentRetriever] Profile: stage={profile.stage_mode}, facets={sorted(profile.facets)}")
        for s in profile.statutes:
            print(f"  - {s['act']} {s['section']}  [{s['kind']}, weight {s['weight']}]")

        candidates: List[PrecedentCandidate] = []
        seen_case_names: Set[str] = set()
        rejected_gate: List[str] = []
        total = 0

        for json_file in self.get_judgment_files():
            total += 1
            data = self.load_judgment(json_file)
            if data is None:
                continue

            case_name = str((data.get("case") or {}).get("case_name") or "").strip().lower()
            if case_name and case_name in seen_case_names:
                continue

            cand = self.match_judgment(profile.statutes, data, profile)
            if cand:
                candidates.append(cand)
                if case_name:
                    seen_case_names.add(case_name)
            else:
                cid = data.get("case_id", json_file.stem)
                cname = (data.get("case") or {}).get("case_name", "Unknown")
                rejected_gate.append(f"{cname} ({cid})")

        print(f"[PrecedentRetriever] Scanned {total} judgments, {len(candidates)} passed gate, {len(rejected_gate)} rejected/unmatched")
        if rejected_gate:
            print(f"[PrecedentRetriever] Sample gate-filtered cases ({min(5, len(rejected_gate))}/{len(rejected_gate)}): {rejected_gate[:5]}")
        return profile, candidates

    def retrieve_candidates(
        self,
        stage4_result: Dict,
        case_context: Optional[Dict] = None,
        role: Optional[str] = None,
    ) -> List[PrecedentCandidate]:
        """Role-neutral (default) or role-specific ranked shortlist, best first."""
        _, candidates = self._scan(stage4_result, case_context)
        key = role if role in ROLES else "neutral"
        candidates.sort(key=lambda c: c.role_scores.get(key, 0.0), reverse=True)
        shortlist = candidates[: self.max_candidates]
        self._print_top(shortlist, key)
        return shortlist

    def retrieve_by_role(
        self,
        stage4_result: Dict,
        case_context: Optional[Dict] = None,
        top_k: int = 8,
    ) -> Dict[str, Any]:
        """
        {"prosecution": [...], "defense": [...], "shared_ids": [...], "profile": {...}}

        shared_ids = precedents ranked in BOTH top_k lists, i.e. useful to both sides (the LLM step should keep
        their conflicting propositions rather than assigning them to one side).
        """
        profile, candidates = self._scan(stage4_result, case_context)
        pools: Dict[str, List[PrecedentCandidate]] = {}
        for role in ROLES:
            pools[role] = sorted(candidates, key=lambda c: c.role_scores.get(role, 0.0), reverse=True)[:top_k]
            self._print_top(pools[role], role)
        shared = [c.case_id for c in pools["prosecution"] if c.case_id in {d.case_id for d in pools["defense"]}]
        return {**pools, "shared_ids": shared, "profile": profile.summary()}

    @staticmethod
    def _print_top(shortlist: List[PrecedentCandidate], key: str, n: int = 5) -> None:
        print(f"[PrecedentRetriever] Top {min(n, len(shortlist))} for {key}:")
        for i, c in enumerate(shortlist[:n], 1):
            b = c.score_breakdown
            print(f"  {i}. {c.case_name} score={c.role_scores.get(key, 0):.3f} "
                  f"(stage {b.get('stage')}/{c.inferred_stage}, fact {b.get('fact')}, stat {b.get('statutory')})")

    # -- LLM formatting -----------------------------------------------------

    def format_candidates_for_llm(self, candidates: List[PrecedentCandidate], include_full_text: bool = False,
                                  role: Optional[str] = None) -> str:
        if not candidates:
            return "No precedent candidates found."

        parts = [f"PRECEDENT CANDIDATES ({len(candidates)} cases):\n"]
        for i, c in enumerate(candidates, 1):
            parts.append(f"\n{'=' * 80}")
            parts.append(f"CANDIDATE #{i}: {c.case_name}")
            parts.append(f"{'=' * 80}")
            parts.append(f"Case ID: {c.case_id}")
            parts.append(f"Court: {c.court}")
            parts.append(f"Decided: {c.decided_on}")
            parts.append(f"Procedural Stage (corpus tag): {c.procedural_stage}   |   inferred: {c.inferred_stage}")
            if c.score_breakdown:
                b = c.score_breakdown
                parts.append(f"Deterministic fit: stage={b.get('stage')}, fact={b.get('fact')}, statutory={b.get('statutory')}, "
                             f"facets={c.case_facets}")
            parts.append(f"Retrieval Score: {c.role_scores.get(role or 'neutral', c.retrieval_score):.3f}")

            parts.append(f"\nMATCHED STATUTES ({len(c.matched_statutes)}):")
            for m in c.matched_statutes:
                marker = "✓" if m.get("match_type", "exact") == "exact" else "≈"
                parts.append(f"  {marker} {m['judgment_act']} {m['judgment_section']} ({m.get('how_used', 'N/A')}) "
                             f"<- input {m['matched_via_act']} {m['matched_via_section']}")

            parts.append("\nABSTRACT FACTS:")
            parts.append(f"{c.abstract_facts[:700]}{'...' if len(c.abstract_facts) > 700 else ''}")
            parts.append("\nDISPOSITION:")
            parts.append(f"{c.disposition}")

            if c.propositions:
                limit = len(c.propositions) if include_full_text else 5
                parts.append(f"\nLEGAL PROPOSITIONS ({len(c.propositions)}):")
                for p in c.propositions[:limit]:
                    text = p.get("text", "") if include_full_text else p.get("text", "")[:240]
                    parts.append(f"  - [{p.get('id', '?')}|{str(p.get('favors', 'neutral')).upper()}|{p.get('binding_level', '')}] {text}")
                if len(c.propositions) > limit:
                    parts.append(f"  ... and {len(c.propositions) - limit} more propositions")

            if c.issues:
                parts.append(f"\nISSUES DECIDED ({len(c.issues)}):")
                for issue in c.issues[:2]:
                    parts.append(f"  Q: {issue.get('question', '')[:150]}...")
                    parts.append(f"  A: {issue.get('short_answer', '')}")
        return "\n".join(parts)


def test_precedent_retrieval():
    """Smoke test with a minimal Stage 4 dict."""
    stage4 = {
        "verified_offences": [
            {"statute": "IPC", "section_number": "420", "overall_prima_facie_strength": "Strong", "overall_status": "Prima Facie Attracted"},
            {"statute": "IPC", "section_number": "468", "overall_prima_facie_strength": "Moderate", "overall_status": "Partially Attracted"},
        ],
    }
    ctx = {"requested_relief": "Anticipatory Bail", "case_facts": "Forged sale deed of agricultural land."}
    retriever = PrecedentRetriever(max_candidates=10)
    result = retriever.retrieve_by_role(stage4, ctx, top_k=5)
    print(json.dumps(result["profile"], indent=2))


if __name__ == "__main__":
    test_precedent_retrieval()