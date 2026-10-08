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
                           "premises", "hotel", "tenan", "inherit", "flat", "apartment"),
    "deed": ("sale deed", "deed", "power of attorney", "gpa", "mutation", "agreement to sell", "registered document",
             "ownership document", "title document"),
    "forgery": ("forged", "forgery", "fabricated", "counterfeit", "false document", "spurious"),
    "cheating": ("cheat", "fraud", "deceiv", "dishonest", "misrepresent"),
    "title_dispute": ("title", "ownership", "owner", "civil dispute", "civil nature"),
    # facets that make a precedent factually DIFFERENT from a private land/forgery dispute
    "public_economic": ("public fund", "money laundering", "foreign investment", "corruption", "disproportionate assets",
                        "public servant", "bank fraud", "ponzi"),
    "matrimonial": ("dowry", "matrimonial", "cruelty", "498a", "husband", "in-laws"),
    "violence": ("murder", "homicide", "culpable homicide", "grievous hurt", "rape", "assault"),
}
DISQUALIFYING_FACETS = {"public_economic", "matrimonial", "violence"}

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

    def __init__(self, tagged_dir: Optional[Path] = None, max_candidates: int = 20):
        self.matcher = PrecedentStatuteMatcher()
        self.max_candidates = max_candidates

        if tagged_dir is None:
            tagged_dir = Path(__file__).parent.parent / "bail_data" / "tagged"
        self.tagged_dir = Path(tagged_dir)
        if not self.tagged_dir.exists():
            raise FileNotFoundError(f"Tagged directory not found: {self.tagged_dir}")

        self._cache: Dict[str, Dict] = {}

    # -- loading ------------------------------------------------------------

    def load_judgment(self, json_path: Path) -> Optional[Dict]:
        key = str(json_path)
        if key in self._cache:
            return self._cache[key]
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
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
    ) -> Dict[str, Any]:
        inferred = infer_case_stage(case)
        stage = STAGE_AFFINITY[profile.stage_mode].get(inferred, 0.2)

        case_facets = extract_facets(" ".join([str(case.get("abstract_facts") or "")] +
                                              [str(i.get("question") or "") for i in case.get("issues", []) or []]))
        penalty = 0.4 * len(case_facets & DISQUALIFYING_FACETS)
        if profile.facets:
            fact = max(0.0, len(profile.facets & case_facets) / len(profile.facets) - penalty)
        else:
            fact = max(0.0, 0.3 - penalty)   # no facts known: neutral-low, never enough to pass the gate alone

        origins: Set[Tuple[str, str]] = {(m["matched_via_act"], m["matched_via_section"]) for m in matched}
        stat_weight = sum(profile.weights.get(o, 0.5) for o in origins)
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

        match_count, matched = self.matcher.match_statutes(input_statutes, judgment_statutes, allow_parent_match=True)
        if match_count == 0:
            return None

        # legacy score, kept for backwards compatibility with anything that still reads it
        n_in = len(input_statutes)
        n_unique = len(matched)
        exact_ratio = (sum(1 for m in matched if m.get("match_type") == "exact") / n_unique) if n_unique else 0
        legacy_score = match_count + (n_unique / n_in if n_in else 0) * 0.5 + exact_ratio * 0.3

        scored: Dict[str, Any] = {}
        if profile is not None:
            scored = self._score(profile, case, matched)
            # procedure-only matches (e.g. just CrPC 438) are not enough
            if not scored["substantive_match"] and scored["breakdown"]["fact"] < 0.5:
                return None

        meta = judgment_data.get("doc_meta", {})
        return PrecedentCandidate(
            case_id=judgment_data.get("case_id", "unknown"),
            case_name=case.get("case_name", "Unknown Case"),
            court=case.get("court", "Unknown Court"),
            decided_on=meta.get("decided_on", ""),
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
        total = 0
        for json_file in sorted(self.tagged_dir.glob("tagged_*.json")):
            total += 1
            data = self.load_judgment(json_file)
            if data is None:
                continue
            cand = self.match_judgment(profile.statutes, data, profile)
            if cand:
                candidates.append(cand)
        print(f"[PrecedentRetriever] Scanned {total} judgments, {len(candidates)} passed the statutory/fact gate")
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