"""
Precedent Retrieval Engine.

Deterministic, role-aware candidate retrieval followed (elsewhere) by role-specific LLM evaluation.
"""

import json
import re as _re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .precedent_statute_matcher import PrecedentStatuteMatcher, detect_stage_mode
from .schemas import CaseRetrievalProfile
from lexigraphbe.offence_taxonomy import ANCILLARY, categories_for


# ----------------------------------------------------------------------------
# Scoring configuration (tune here)
# ----------------------------------------------------------------------------

WEIGHTS = {"stage": 0.30, "fact": 0.25, "statutory": 0.20, "principle": 0.15, "direction": 0.10}

STAGE_AFFINITY = {
    "anticipatory": {"pre_arrest": 1.0, "anticipatory_cancel": 0.8, "quashing": 0.5, "post_arrest_bail": 0.3, "other": 0.2},
    "regular":      {"post_arrest_bail": 1.0, "pre_arrest": 0.6, "anticipatory_cancel": 0.5, "quashing": 0.3, "other": 0.2},
    "unknown":      {"pre_arrest": 0.6, "post_arrest_bail": 0.6, "anticipatory_cancel": 0.5, "quashing": 0.4, "other": 0.3},
}

# Finer-grained stage compatibility keyed by (input_inferred_stage, candidate_corpus_stage).
# Used in _score() to override STAGE_AFFINITY where the semantic gap between stages matters.
#
# Key design choices:
#  - pre_arrest ↔ anticipatory_cancel = 0.55 (not 0.8): initial AB grant and AB revocation are
#    different legal questions — useful by analogy but NOT on-point for the grant question.
#  - anticipatory_cancel ↔ pre_arrest = 0.70: a revocation case CAN use grant-stage precedents
#    on the underlying merits, so it is somewhat closer the other way.
#  - Omitted pairs fall back to STAGE_AFFINITY (the broader stage_mode table).
STAGE_COMPATIBILITY: Dict[Tuple[str, str], float] = {
    # Input is an initial anticipatory bail application (pre_arrest)
    ("pre_arrest", "pre_arrest"):          1.00,
    ("pre_arrest", "anticipatory_cancel"): 0.55,  # different question: revoke != grant
    ("pre_arrest", "post_arrest_bail"):    0.30,
    ("pre_arrest", "quashing"):            0.50,
    ("pre_arrest", "other"):               0.20,
    # Input is an anticipatory bail cancellation (anticipatory_cancel)
    ("anticipatory_cancel", "pre_arrest"):          0.70,
    ("anticipatory_cancel", "anticipatory_cancel"): 1.00,
    ("anticipatory_cancel", "post_arrest_bail"):    0.35,
    ("anticipatory_cancel", "quashing"):            0.45,
    ("anticipatory_cancel", "other"):               0.25,
    # Input is regular / post-arrest bail
    ("post_arrest_bail", "post_arrest_bail"): 1.00,
    ("post_arrest_bail", "pre_arrest"):       0.40,
    ("post_arrest_bail", "anticipatory_cancel"): 0.30,
    ("post_arrest_bail", "quashing"):         0.35,
    ("post_arrest_bail", "other"):            0.20,
    # Input stage is unknown
    ("unknown", "pre_arrest"):          0.60,
    ("unknown", "post_arrest_bail"):    0.60,
    ("unknown", "anticipatory_cancel"): 0.50,
    ("unknown", "quashing"):            0.40,
    ("unknown", "other"):               0.30,
}

ANTICIPATORY_MARKERS = ("anticipatory bail", "pre-arrest bail", "section 438", "bnss 482", "s. 438")
CANCEL_MARKERS = ("cancel", "set aside", "setting aside", "quash the order granting")

# ----------------------------------------------------------------------------
# Facet detection — statute-anchored (primary) + keyword fallback (secondary)
# ----------------------------------------------------------------------------
# Each entry: (tuple of lowercase act-name fragments to match, regex for section, facet name)
# Extend this table when adding new domains; never add domain logic elsewhere.
STATUTE_FACET_MAP: List[Tuple[Tuple[str, ...], str, str]] = [
    # Violence / homicide
    (("ipc", "bns"),            r"^302$",       "violence"),
    (("ipc", "bns"),            r"^304$",       "violence"),        # culpable homicide
    (("ipc", "bns"),            r"^307$",       "violence"),
    (("ipc", "bns"),            r"^323$",       "violence"),
    (("ipc", "bns"),            r"^324$",       "violence"),
    # Negligent death / professional negligence — kept separate so medical cases are NOT disqualified
    (("ipc", "bns"),            r"^304[Aa]$",   "negligent_death"),
    (("ipc", "bns"),            r"^338$",       "grievous_negligence"),
    (("ipc", "bns"),            r"^336$",       "negligence"),
    (("ipc", "bns"),            r"^269$",       "negligence"),
    # Evidence / record tampering (common in medical negligence / corruption)
    (("ipc", "bns"),            r"^201$",       "evidence_tampering"),
    (("ipc", "bns"),            r"^202$",       "evidence_tampering"),
    (("ipc", "bns"),            r"^204$",       "evidence_tampering"),
    (("ipc", "bns"),            r"^197$",       "evidence_tampering"),
    # Sexual offences
    (("ipc", "bns"),            r"^376",        "sexual_offence"),
    (("ipc", "bns"),            r"^354",        "sexual_offence"),
    (("ipc", "bns"),            r"^493$",       "sexual_offence"),
    (("pocso",),                r".*",          "sexual_offence"),
    # Matrimonial / dowry
    (("ipc", "bns"),            r"^498[Aa]$",   "matrimonial"),
    (("ipc", "bns"),            r"^304[Bb]$",   "matrimonial"),
    (("dowry",),                r".*",          "matrimonial"),
    (("domestic violence",),    r".*",          "matrimonial"),
    # Documents / property fraud
    (("ipc", "bns"),            r"^420$",       "cheating"),
    (("ipc", "bns"),            r"^415$",       "cheating"),
    (("ipc", "bns"),            r"^406$",       "cheating"),
    (("ipc", "bns"),            r"^409$",       "cheating"),
    (("ipc", "bns"),            r"^467$",       "forgery"),
    (("ipc", "bns"),            r"^468$",       "forgery"),
    (("ipc", "bns"),            r"^471$",       "forgery"),
    (("ipc", "bns"),            r"^465$",       "forgery"),
    (("ipc", "bns"),            r"^463$",       "forgery"),
    (("ipc", "bns"),            r"^447$",       "immovable_property"),
    (("ipc", "bns"),            r"^448$",       "immovable_property"),
    # Abetment / conspiracy (not a standalone domain; combined with underlying offence facets)
    # Economic / special statutes — treated as disqualifying for ordinary IPC matters
    (("pmla", "prevention of money laundering"), r".*", "special_statute"),
    (("fema",),                 r".*",          "special_statute"),
    (("ndps",),                 r".*",          "special_statute"),
    (("uapa",),                 r".*",          "special_statute"),
    (("companies act",),        r".*",          "special_statute"),
    (("prevention of corruption", "pc act"),    r".*", "corruption"),
]

# Facets whose presence in a CANDIDATE disqualifies it unless the INPUT also has that facet.
# "violence" and "negligent_death" are intentionally NOT here — a death case can be relevant
# to another death case regardless of whether it was negligent or intentional, and the
# fact-score penalty handles the attenuation.
DISQUALIFYING_FACETS: Set[str] = {"sexual_offence", "matrimonial", "special_statute"}

# Groups of facets that are mutually relevant — a candidate from one group is not disqualified
# when the input has a facet from the same group.
DEATH_FACETS: Set[str] = {"violence", "negligent_death", "grievous_negligence", "negligence"}

# Keyword fallback — used ONLY when no statutes are tagged on the case.
_KW_FACET_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "immovable_property": ("land", "plot", "immovable", "agricultural", "property dispute", "possession of a property",
                           "premises", "hotel", "tenan", "inherit", "flat", "apartment", "revenue"),
    "forgery":            ("forged", "forgery", "fabricated", "counterfeit", "false document", "spurious"),
    "cheating":           ("cheat", "fraud", "deceiv", "dishonest", "misrepresent"),
    "negligent_death":    ("negligence", "negligent", "304a", "causing death by negligence", "medical negligence",
                           "standard of care", "duty of care", "reckless"),
    "evidence_tampering": ("destroy", "conceal", "tamper", "falsif", "alteration of record"),
    "matrimonial":        ("dowry", "matrimonial", "cruelty", "498a", "in-laws", "marriage dispute",
                           "domestic violence", "stridhan"),
    "sexual_offence":     ("rape", "sexual", "376", "modesty", "354", "promise of marriage",
                           "pretext of marriage", "pocso", "intercourse"),
    "violence":           ("murder", "homicide", "culpable homicide", "grievous hurt", "302", "307", "304",
                           "assault", "killing", "dead body"),
}

ROLE_THEMES: Dict[str, Tuple[str, ...]] = {
    "prosecution": ("custodial interrogation", "custodial", "gravity", "grave", "investigation",
                    "antecedent", "tamper", "recovery", "exceptional", "cancel", "suppress", "conceal",
                    "negligent", "reckless", "duty of care", "prima facie", "flight risk"),
    "defense":     ("civil", "prima facie", "personal liberty", "cooperat", "harass", "quash",
                    "bona fide", "vendetta", "malicious", "arrest is not", "not a right", "discretion",
                    "distinct", "bail", "liberty", "right to bail", "no prior"),
}
SIDE_OF_FAVORS = {"prosecution": "prosecution", "accused": "defense", "defense": "defense", "defence": "defense"}
ROLES = ("prosecution", "defense")


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def infer_case_stage(case: Dict[str, Any]) -> str:
    """pre_arrest | anticipatory_cancel | quashing | post_arrest_bail | other"""
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


def _statute_facets(statutes: List[Dict[str, Any]]) -> Set[str]:
    """Derive facets from charged/interpreted statutes — authoritative, no keyword guessing."""
    result: Set[str] = set()
    for st in statutes:
        act = str(st.get("act") or "").lower()
        sec = str(st.get("section") or "").strip()
        for act_frags, sec_pat, facet in STATUTE_FACET_MAP:
            if any(frag in act for frag in act_frags) and _re.match(sec_pat, sec, _re.I):
                result.add(facet)
    return result


def extract_facets(text: str) -> Set[str]:
    """Keyword-only facet extraction (fallback path — prefer _statute_facets when statutes are available)."""
    t = (text or "").lower()
    return {facet for facet, kws in _KW_FACET_KEYWORDS.items() if any(k in t for k in kws)}


def extract_case_facets(case: Dict[str, Any], doc_meta: Optional[Dict[str, Any]] = None) -> Set[str]:
    """
    Statute-anchored facets (primary, authoritative) with keyword fallback.

    Primary path: parse the case's charged statutes through STATUTE_FACET_MAP — this is
    unambiguous and covers the important domains.  Keyword scanning is used only when the
    case has no tagged statutes (e.g. an older corpus entry).
    """
    statutes = case.get("statutes") or []
    if statutes:
        facets = _statute_facets(statutes)
        # Also pull in any keyword facets for domains not covered by statute map
        # (e.g. "immovable_property" from abstract_facts when no property-trespass section was charged)
        if not facets:
            # No statute matched the map — fall back to keywords
            text_blob = " ".join([
                str(case.get("abstract_facts") or ""),
                str(case.get("disposition") or ""),
                " ".join(str(ot) for ot in (case.get("offence_types") or [])),
                " ".join(str(kw) for kw in (doc_meta or {}).get("keywords") or []),
            ])
            facets = extract_facets(text_blob)
    else:
        # No statute list at all — pure keyword fallback
        text_blob = " ".join([
            str(case.get("abstract_facts") or ""),
            str(case.get("disposition") or ""),
            " ".join(str(ot) for ot in (case.get("offence_types") or [])),
            " ".join(str(kw) for kw in (doc_meta or {}).get("keywords") or []),
        ])
        facets = extract_facets(text_blob)
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
    # Inferred corpus-level stage tag for the INPUT case — used for STAGE_COMPATIBILITY lookup.
    # Examples: "pre_arrest", "post_arrest_bail", "anticipatory_cancel", "quashing", "unknown"
    # Falls back to stage_mode if not set (for backward compatibility with old call sites).
    input_stage: str = "unknown"

    def summary(self) -> Dict[str, Any]:
        return {
            "stage_mode": self.stage_mode,
            "input_stage": self.input_stage,
            "facets": sorted(self.facets),
            "statutes": [f"{s['act']} {s['section']} ({s['kind']}, w={s['weight']})" for s in self.statutes],
        }


def build_case_retrieval_profile(
    stage4_result: Dict[str, Any],
    case_context: Optional[Dict[str, Any]] = None,
    matcher: Optional[PrecedentStatuteMatcher] = None,
) -> CaseRetrievalProfile:
    """
    Construct a CaseRetrievalProfile from Stage 4 output and optional case context.

    fact_patterns, prosecution_themes and defence_themes are derived from
    stage4_result["verified_offences"] — from offence titles, ingredient satisfaction
    status, and role-specific arguments — so the profile describes the actual case
    regardless of domain (medical negligence, property fraud, corruption, etc.).
    """
    if matcher is None:
        matcher = PrecedentStatuteMatcher()
    stage_mode = detect_stage_mode(stage4_result, case_context)
    procedural_stage = (
        "anticipatory_bail" if stage_mode == "anticipatory"
        else ("regular_bail" if stage_mode == "regular" else "bail_or_quashing")
    )
    legal_regime = stage4_result.get("legal_regime", "IPC + CrPC")

    offences: List[str] = []
    fact_patterns: List[str] = []
    prosecution_themes: List[str] = []
    defence_themes: List[str] = []

    for off in stage4_result.get("verified_offences", []) or []:
        # Offence section numbers
        sec = str(off.get("section_number") or "").strip()
        if sec and sec not in offences:
            offences.append(sec)

        # Fact patterns from offence title and a short description of what is alleged
        title = str(off.get("title") or off.get("offence_title") or "").strip()
        if title:
            fact_patterns.append(title)
        short_desc = str(off.get("short_description") or off.get("description") or "").strip()
        if short_desc and short_desc != title:
            fact_patterns.append(short_desc)

        # Prosecution themes: ingredients satisfied + explicit prosecution arguments
        for ing in off.get("ingredients", []) or []:
            satisfied = ing.get("satisfied")
            # Accept various truthy representations
            if satisfied in (True, "yes", "likely", "satisfied", "established"):
                desc = str(ing.get("description") or ing.get("ingredient") or "").strip()
                if desc:
                    prosecution_themes.append(desc)
        for arg in off.get("prosecution_arguments", []) or []:
            txt = str(arg).strip()
            if txt:
                prosecution_themes.append(txt)

        # Defence themes: disputed / unsatisfied ingredients + explicit defence arguments
        for ing in off.get("ingredients", []) or []:
            satisfied = ing.get("satisfied")
            if satisfied in (False, "no", "unlikely", "disputed", "not established", "absent"):
                desc = str(ing.get("description") or ing.get("ingredient") or "").strip()
                if desc:
                    defence_themes.append(f"disputed: {desc}")
        for arg in off.get("defence_arguments", []) or []:
            txt = str(arg).strip()
            if txt:
                defence_themes.append(txt)

    # Deduplicate while preserving order, cap length
    def _dedup(lst: List[str], cap: int = 8) -> List[str]:
        seen: Set[str] = set()
        out: List[str] = []
        for x in lst:
            if x not in seen:
                seen.add(x)
                out.append(x)
            if len(out) >= cap:
                break
        return out

    fact_patterns      = _dedup(fact_patterns)
    prosecution_themes = _dedup(prosecution_themes)
    defence_themes     = _dedup(defence_themes)

    # Fallbacks when Stage 4 didn't populate arguments (older pipeline versions)
    ctx = case_context if isinstance(case_context, dict) else {}
    if not prosecution_themes:
        facts = str(ctx.get("abstract_facts") or "")
        if facts:
            prosecution_themes = [f"prima facie case based on facts: {facts[:200]}"]
        else:
            prosecution_themes = [
                "gravity of the alleged offence",
                "necessity of custodial interrogation",
                "risk of evidence tampering",
            ]
    if not defence_themes:
        defence_themes = [
            "cooperation with investigation",
            "no flight risk",
            "custodial interrogation not required when documents already seized",
            "right to personal liberty under Article 21",
        ]
    if not fact_patterns and offences:
        fact_patterns = [f"offence under section {s}" for s in offences[:4]]

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

    # Build input-case facets from the actual charged statutes (statute-anchored, not keyword)
    ctx = case_context if isinstance(case_context, dict) else {}
    input_statutes_raw = []
    for off in stage4_result.get("verified_offences", []) or []:
        sec = str(off.get("section_number") or "").strip()
        statute = str(off.get("statute") or off.get("act") or "IPC")
        if sec:
            input_statutes_raw.append({"act": statute, "section": sec})
    # Also include statutes from case_context if available
    for st in ctx.get("statutes", []) or []:
        input_statutes_raw.append(st)

    facets = _statute_facets(input_statutes_raw) if input_statutes_raw else extract_facets(
        " ".join([_collect_text(ctx), _collect_text(stage4_result.get("verified_offences", []))])
    )
    # Remove disqualifying facets from the INPUT profile
    # (they are only used to gate candidates, not to describe the input itself)
    facets = facets - DISQUALIFYING_FACETS

    stage_mode = detect_stage_mode(stage4_result, case_context)
    # Derive a finer-grained input_stage corpus tag from case_context when available.
    # detect_stage_mode returns "anticipatory" | "regular" | "unknown" (broad buckets);
    # we map these to corpus-level tags so STAGE_COMPATIBILITY can apply.
    ctx_stage = str((case_context or {}).get("procedural_stage") or "").lower().strip() if case_context else ""
    if ctx_stage in ("pre_arrest", "anticipatory_cancel", "post_arrest_bail", "quashing", "other"):
        input_stage = ctx_stage
    elif stage_mode == "anticipatory":
        # Without a finer tag, assume the common case: an initial application (pre_arrest),
        # but keep anticipatory_cancel as-is if the context text signals it.
        ctx_text = " ".join([
            str((case_context or {}).get("case_summary", "")),
            str((case_context or {}).get("abstract_facts", "")),
        ]).lower()
        input_stage = "anticipatory_cancel" if any(m in ctx_text for m in CANCEL_MARKERS) else "pre_arrest"
    elif stage_mode == "regular":
        input_stage = "post_arrest_bail"
    else:
        input_stage = "unknown"

    return RetrievalProfile(
        statutes=statutes,
        weights=weights,
        kinds=kinds,
        facets=facets,
        stage_mode=stage_mode,
        total_weight=sum(weights.values()) or 1.0,
        input_stage=input_stage,
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

    inferred_stage: str = ""
    case_facets: List[str] = field(default_factory=list)
    score_breakdown: Dict[str, Any] = field(default_factory=dict)
    role_scores: Dict[str, float] = field(default_factory=dict)
    retrieval_score: float = 0.0

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
            "score_breakdown": self.score_breakdown,
            "role_scores": self.role_scores,
            "retrieval_score": self.retrieval_score,
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
            bail_data_dir = Path(__file__).resolve().parent.parent / "bail_data"
            if (bail_data_dir / "out").exists():
                chosen_dir = bail_data_dir / "out"
            elif (bail_data_dir / ".out").exists():
                chosen_dir = bail_data_dir / ".out"
            elif (bail_data_dir / "tagged").exists():
                chosen_dir = bail_data_dir / "tagged"
            else:
                chosen_dir = bail_data_dir / "out"

        self.precedent_dir = Path(chosen_dir)
        self.tagged_dir = self.precedent_dir
        if not self.precedent_dir.exists():
            raise FileNotFoundError(f"Precedent directory not found: {self.precedent_dir}")

        self._cache: Dict[str, Dict] = {}

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

    @staticmethod
    def _principle_and_direction(propositions: List[Dict[str, Any]], role: str) -> Tuple[float, float]:
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
    ) -> Dict[str, Any]:
        inferred = infer_case_stage(case)
        # Use fine-grained STAGE_COMPATIBILITY when we know the exact input stage;
        # fall back to the broader STAGE_AFFINITY keyed by stage_mode otherwise.
        input_stage = getattr(profile, "input_stage", None) or profile.stage_mode
        if (input_stage, inferred) in STAGE_COMPATIBILITY:
            stage = STAGE_COMPATIBILITY[(input_stage, inferred)]
        else:
            stage = STAGE_AFFINITY[profile.stage_mode].get(inferred, 0.2)

        case_facets = extract_case_facets(case, doc_meta)
        # Penalty is only applied for disqualifying facets that appear in the candidate
        # but not in the input — "violence" and death-related facets do NOT disqualify.
        disq_penalty = 0.4 * len((case_facets & DISQUALIFYING_FACETS) - profile.facets)
        if profile.facets:
            fact = max(0.0, len(profile.facets & case_facets) / len(profile.facets) - disq_penalty)
        else:
            # Input has no domain facets (e.g. pure procedural query) — use a neutral baseline
            # minus any disqualifying-facet mismatch penalty.
            fact = max(0.0, 0.3 - disq_penalty)

        origins: Set[Tuple[str, str]] = {(m["matched_via_act"], m["matched_via_section"]) for m in matched}
        exact_origins = {(m["matched_via_act"], m["matched_via_section"]) for m in matched if m.get("match_type") != "family"}
        # A same-family match counts half of an exact/parent section match.
        stat_weight = sum(profile.weights.get(o, 0.5) * (1.0 if o in exact_origins else 0.5) for o in origins)
        statutory = min(1.0, stat_weight / profile.total_weight)
        substantive = any(profile.kinds.get(o) in ("offence", "special") for o in origins)

        props = case.get("propositions", []) or []
        per_role: Dict[str, Dict[str, float]] = {}
        for role in ROLES:
            principle, direction = self._principle_and_direction(props, role)
            score = (WEIGHTS["stage"] * stage + WEIGHTS["fact"] * fact + WEIGHTS["statutory"] * statutory
                     + WEIGHTS["principle"] * principle + WEIGHTS["direction"] * direction)
            per_role[role] = {"principle": round(principle, 3), "direction": round(direction, 3), "score": round(score, 4)}

        neutral = round(sum(r["score"] for r in per_role.values()) / len(per_role), 4)
        return {
            "inferred_stage": inferred,
            "case_facets": sorted(case_facets),
            "substantive_match": substantive,
            "breakdown": {
                "stage": round(stage, 3), "fact": round(fact, 3), "statutory": round(statutory, 3),
                "matched_inputs": sorted(f"{a} {s}" for a, s in origins),
                "by_role": per_role,
            },
            "role_scores": {"prosecution": per_role["prosecution"]["score"], "defense": per_role["defense"]["score"], "neutral": neutral},
        }

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

        match_count, matched = self.matcher.match_statutes(input_statutes, judgment_statutes, allow_parent_match=True)

        # Offence-family match: a judgment charged under a different section of the same IPC offence
        # family (e.g. input 465, judgment 467/468/471 -> FORGERY) is a candidate even without an exact
        # section match. Families come from offence_taxonomy (IPC chapter structure); ancillary
        # families (abetment, conspiracy, common intention, attempt) never qualify on their own.
        matched_keys = {(m["judgment_act"], m["judgment_section"]) for m in matched}
        input_cats = []
        for st in input_statutes:
            if st.get("kind", "offence") != "offence":
                continue
            a = self.matcher.normalize_act_name(st.get("act", ""))
            s = self.matcher.normalize_section_number(str(st.get("section", "")))
            cats = categories_for(a, s) - set(ANCILLARY)
            if cats:
                input_cats.append(((a, s), cats))
        for js in judgment_statutes:
            if (js.get("act", ""), js.get("section", "")) in matched_keys:
                continue
            jcats = categories_for(self.matcher.normalize_act_name(js.get("act", "")),
                                   self.matcher.normalize_section_number(str(js.get("section", ""))))
            for (a, s), cats in input_cats:
                if cats & jcats:
                    matched.append({
                        "judgment_act": js.get("act", ""), "judgment_section": js.get("section", ""),
                        "matched_via_act": a, "matched_via_section": s, "match_type": "family",
                        "how_used": js.get("how_used", ""), "note": f"same offence family: {sorted(cats & jcats)}",
                    })
                    match_count += 0.5
                    break
        if match_count == 0:
            return None

        n_in = len(input_statutes)
        n_unique = len(matched)
        exact_ratio = (sum(1 for m in matched if m.get("match_type") == "exact") / n_unique) if n_unique else 0
        legacy_score = match_count + (n_unique / n_in if n_in else 0) * 0.5 + exact_ratio * 0.3

        meta = judgment_data.get("doc_meta", {})
        citation = (
            meta.get("citation_scr")
            or meta.get("citation_neutral")
            or meta.get("case_no")
            or None
        )

        scored: Dict[str, Any] = {}
        if profile is not None:
            scored = self._score(profile, case, matched, doc_meta=meta)
            cand_facets = set(scored.get("case_facets", []))

            # --- Gate filter: disqualify candidates whose domain is alien to the input ---
            # Hard disqualifying facets (sexual_offence, matrimonial, special_statute):
            # reject if candidate has them and input does not.
            disq_in_cand = cand_facets & DISQUALIFYING_FACETS
            if disq_in_cand and not (disq_in_cand & profile.facets):
                return None

            # Death facets (violence, negligent_death, grievous_negligence, negligence):
            # reject only if the candidate involves death/violence AND the input has NO death
            # facet at all — a murder case should not match a pure property fraud input.
            cand_death = cand_facets & DEATH_FACETS
            if cand_death and not (profile.facets & DEATH_FACETS):
                return None

            # Low-quality non-substantive candidates: drop if fact score is very low
            # AND stage score is not high with rich holdings.
            if not scored["substantive_match"]:
                j_acts = {str(s.get("act", "")).lower() for s in judgment_statutes}
                special_acts_restrictive = ("companies act", "ndps", "prevention of money laundering",
                                            "pmla", "uapa", "pocso")
                if any(sa in a for a in j_acts for sa in special_acts_restrictive):
                    return None

                has_rich_holdings = len([p for p in case.get("propositions", [])
                                         if p.get("is_holding") or p.get("kind") == "ratio"]) >= 4
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