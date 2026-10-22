"""
Precedent Retrieval Engine for LexiGraphBE Stage 5 (generic, index-backed).

Works for any anticipatory-bail input (any offence, any act) and scales with the corpus: queries are answered from
PrecedentIndex (statute postings + sparse TF-IDF spaces + citation graph), not by opening every judgment.

Per candidate (all signals are corpus- or statute-derived; there are no case names, section lists or keyword lists):

    relevance = 0.30 stage        procedural-stage affinity (stage inferred from provisions interpreted, not just tags)
              + 0.25 fact         cosine(input facts, abstract_facts), scaled by the corpus-calibrated "close" cosine
              + 0.20 statutory    0.6 * weighted exact/parent statute match  +  0.4 * offence-category similarity
              + 0.15 issue        cosine(input legal issues, judgment issues + holdings)
              + 0.10 authority    court level x in-corpus citation count (log-scaled)
    role_score = 0.85 * relevance + 0.15 * share of holdings favouring that role

Two channels decide whether a judgment may appear at all:
    case       offence-category compatible with the input (a murder precedent is not a cheating precedent), or an
               exact charged-statute match;
    principle  different offence, but its issues/holdings are a very close match to a legal issue the input raises
               (kept to a few, ranked by issue match x authority). It is never forced in: an input that does not raise
               the issue never sees it.
"""

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .offence_taxonomy import category_similarity, category_vector, themes_for, CATEGORY_THEMES
from .precedent_index import PrecedentIndex, infer_case_stage, tokenize, Record  # noqa: F401  (re-exported)
from .precedent_statute_matcher import PrecedentStatuteMatcher, detect_stage_mode
from .schemas.stage5_precedent import CaseRetrievalProfile


# ----------------------------------------------------------------------------
# Configuration (structure of the score, not facts of a case)
# ----------------------------------------------------------------------------

WEIGHTS = {"stage": 0.30, "fact": 0.25, "statutory": 0.20, "issue": 0.15, "authority": 0.10}
DIRECTION_WEIGHT = 0.15

STAGE_AFFINITY = {
    "anticipatory": {"pre_arrest": 1.0, "anticipatory_cancel": 0.8, "quashing": 0.5, "post_arrest_bail": 0.3, "other": 0.2},
    "regular":      {"post_arrest_bail": 1.0, "pre_arrest": 0.6, "anticipatory_cancel": 0.5, "quashing": 0.3, "other": 0.2},
    "unknown":      {"pre_arrest": 0.6, "post_arrest_bail": 0.6, "anticipatory_cancel": 0.5, "quashing": 0.4, "other": 0.3},
}
ROLES = ("prosecution", "defense")


@dataclass
class RetrievalConfig:
    min_category_similarity: float = 0.2     # "case" channel: offence compatibility
    principle_z: float = 3.0                 # "principle" channel: issue similarity must be this many std-devs above the
                                             # mean similarity of the query to the whole corpus (corpus-size independent)
    principle_min_raw: float = 0.12          # ... and at least this raw cosine, so a flat distribution cannot qualify
    max_principle: int = 4
    stage_floor: float = 0.3                 # drop judgments whose stage affinity is below this (e.g. 'other')
    shortlist_size: int = 20                 # statute shortlist: max candidates sent to the LLM
    shortlist_rel_cut: float = 0.4           # ... keep only cases scoring >= this fraction of the best case
    ubiquitous_df: float = 0.3               # a statute key found in more than this share of judgments is 'generic'
                                             # (e.g. CrPC 438 in an anticipatory-bail corpus): it can add score but
                                             # a case cannot qualify on generic keys alone
    top_fact_neighbours: int = 150           # extra recall channel: closest by facts even without a statute hit


# ----------------------------------------------------------------------------
# Profile
# ----------------------------------------------------------------------------

def _collect_text(obj: Any, limit: int = 20000) -> str:
    """All string leaves of a nested dict/list, joined."""
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


def _issue_list(ctx: Dict[str, Any]) -> List[str]:
    """Legal issues the input raises: from Stage 1 / Stage 0 if present (several possible key names)."""
    issues: List[str] = []
    for k in ("legal_issues", "legal_questions", "issues", "legal_query", "queries"):
        v = ctx.get(k)
        if isinstance(v, str) and v.strip():
            issues.append(v.strip())
        elif isinstance(v, (list, tuple)):
            issues.extend(_collect_text(x).strip() for x in v if _collect_text(x).strip())
        elif isinstance(v, dict):
            t = _collect_text(v).strip()
            if t:
                issues.append(t)
    return issues


@dataclass
class RetrievalProfile:
    """What we are looking for, built once from Stage 4 + Stage 0/1."""
    statutes: List[Dict[str, Any]]
    key_weights: Dict[str, float]            # canonical statute key -> weight (offence, special, procedure)
    key_kinds: Dict[str, str]
    categories: Dict[str, float]             # offence category vector of the charged offences
    fact_text: str
    issues: List[str]
    stage_mode: str                          # anticipatory | regular | unknown
    themes: Dict[str, List[str]]
    total_weight: float

    def summary(self) -> Dict[str, Any]:
        return {
            "stage_mode": self.stage_mode,
            "categories": self.categories,
            "issues": self.issues[:5],
            "statutes": [f"{s['act']} {s['section']} ({s['kind']}, w={s['weight']})" for s in self.statutes],
        }


def build_profile(
    matcher: PrecedentStatuteMatcher,
    index: PrecedentIndex,
    stage4_result: Dict[str, Any],
    case_context: Optional[Dict[str, Any]] = None,
) -> RetrievalProfile:
    ctx = case_context if isinstance(case_context, dict) else {}
    statutes = matcher.extract_statutes_from_stage4(stage4_result, ctx)
    key_weights: Dict[str, float] = {}
    key_kinds: Dict[str, str] = {}
    refs: List[Tuple[str, str, float]] = []
    for s in statutes:
        if s["kind"] == "evidence":
            continue       # evidence-law sections almost never appear in bail judgments; they must not dilute matching
        main, _ = index.canonical_keys(s["act"], s["section"])
        key_weights[main] = max(key_weights.get(main, 0.0), float(s.get("weight", 0.5)))
        key_kinds[main] = s["kind"]
        if s["kind"] in ("offence", "special"):
            act_c, sec_c = main.split(":", 1)
            refs.append((act_c, sec_c, float(s.get("weight", 0.5))))
    categories = category_vector(refs)
    fact_text = " ".join([_collect_text(ctx), _collect_text(stage4_result.get("verified_offences", []))])
    return RetrievalProfile(
        statutes=statutes, key_weights=key_weights, key_kinds=key_kinds, categories=categories,
        fact_text=fact_text, issues=_issue_list(ctx), stage_mode=detect_stage_mode(stage4_result, ctx),
        themes=themes_for(categories), total_weight=sum(key_weights.values()) or 1.0,
    )


def build_case_retrieval_profile(
    stage4_result: Dict[str, Any],
    case_context: Optional[Dict[str, Any]] = None,
    index: Optional[PrecedentIndex] = None,
    matcher: Optional[PrecedentStatuteMatcher] = None,
) -> CaseRetrievalProfile:
    """
    Structured profile for the output object. Offences, fact patterns and argument themes are DERIVED from the
    input (charged offence categories, distinctive terms in the facts) instead of a fixed list of phrases.
    """
    matcher = matcher or PrecedentStatuteMatcher()
    mode = detect_stage_mode(stage4_result, case_context)
    procedural_stage = "anticipatory_bail" if mode == "anticipatory" else ("regular_bail" if mode == "regular" else "bail_or_quashing")

    offences: List[str] = []
    refs: List[Tuple[str, str, float]] = []
    for off in stage4_result.get("verified_offences", []) or []:
        sec = str(off.get("section_number", "")).strip()
        if sec and sec not in offences:
            offences.append(sec)
        refs.append((matcher.normalize_act_name(off.get("statute") or "IPC"), sec, 1.0))
    # offence categories use the canonical (old-regime) section; BNS inputs are mapped back through the matcher
    canon_refs = []
    for act, sec, w in refs:
        eq = {a: s for a, s in matcher.get_equivalent_sections(act, sec)}
        canon_refs.append(("IPC", eq["IPC"], w) if "IPC" in eq else (act, sec, w))
    categories = category_vector(canon_refs)

    text = _collect_text(case_context if isinstance(case_context, dict) else {})
    toks = tokenize(text)
    if index is not None:
        scored = sorted({t for t in toks if t in index.fact_idf}, key=lambda t: -index.fact_idf[t])[:8]
    else:
        scored = [t for t, _ in sorted(((t, toks.count(t)) for t in set(toks)), key=lambda x: -x[1])[:8]]
    fact_patterns = [c.replace("_", " ").lower() for c in sorted(categories, key=lambda c: -categories[c])] + scored

    themes = themes_for(categories)
    return CaseRetrievalProfile(
        procedural_stage=procedural_stage,
        legal_regime=stage4_result.get("legal_regime", "IPC + CrPC"),
        offences=offences,
        fact_patterns=fact_patterns,
        defence_themes=themes["defense"],
        prosecution_themes=themes["prosecution"],
    )


# ----------------------------------------------------------------------------
# Candidate
# ----------------------------------------------------------------------------

@dataclass
class PrecedentCandidate:
    """Represents a candidate precedent case from retrieval."""
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
    case_facets: List[str] = field(default_factory=list)          # offence categories of the precedent
    score_breakdown: Dict[str, Any] = field(default_factory=dict)
    role_scores: Dict[str, float] = field(default_factory=dict)   # prosecution / defense / neutral
    retrieval_score: float = 0.0
    channel: str = "case"                                         # "case" | "principle"
    offence_types: List[str] = field(default_factory=list)
    dispute_nature: str = ""
    lower_court_outcome: str = ""
    verdicts: Dict[str, Any] = field(default_factory=dict)        # per-proposition tagging verdicts, if present

    @property
    def is_principle(self) -> bool:
        return self.channel == "principle"

    def to_dict(self) -> Dict:
        return {
            "case_id": self.case_id, "case_name": self.case_name, "court": self.court, "decided_on": self.decided_on,
            "disposition": self.disposition, "procedural_stage": self.procedural_stage, "inferred_stage": self.inferred_stage,
            "matched_statutes": self.matched_statutes, "match_score": self.match_score, "total_statutes": self.total_statutes,
            "abstract_facts": self.abstract_facts, "case_facets": self.case_facets, "statutes": self.statutes,
            "propositions": self.propositions, "issues": self.issues, "authorities": self.authorities,
            "source_file": self.source_file, "score_breakdown": self.score_breakdown, "role_scores": self.role_scores,
            "retrieval_score": self.retrieval_score, "channel": self.channel,
        }


# ----------------------------------------------------------------------------
# Retriever
# ----------------------------------------------------------------------------

class PrecedentRetriever:
    """Scores judgments from the PrecedentIndex against a RetrievalProfile; returns role-specific shortlists."""

    def __init__(self, precedent_dir: Optional[Path] = None, tagged_dir: Optional[Path] = None,
                 max_candidates: int = 20, config: Optional[RetrievalConfig] = None, embedder: Any = None,
                 cache_path: Optional[Path] = None):
        self.matcher = PrecedentStatuteMatcher()
        self.max_candidates = max_candidates
        self.config = config or RetrievalConfig()

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
        self.index = PrecedentIndex(self.precedent_dir, self.matcher, cache_path=cache_path, embedder=embedder)

    def get_judgment_files(self) -> List[Path]:
        """All judgment JSON files in the precedent directory (same rule the index uses)."""
        return [Path(r.path) for r in self.index.records]

    def refresh_index(self) -> None:
        """Call after adding/removing tagged files (only changed files are re-parsed)."""
        self.index.refresh()

    def extract_input_statutes(self, stage4_result: Dict, case_context: Optional[Dict] = None) -> List[Dict[str, Any]]:
        return self.matcher.extract_statutes_from_stage4(stage4_result, case_context)

    # -- scoring (index records only; no file I/O) ----------------------------

    def _score_all(self, profile: RetrievalProfile) -> List[Dict[str, Any]]:
        ix, cfg = self.index, self.config
        affinity = STAGE_AFFINITY[profile.stage_mode]

        fact_sims = ix.similarity(profile.fact_text, "fact") if profile.fact_text.strip() else {}
        issue_sims: Dict[int, float] = {}
        issue_hit: Set[int] = set()          # judgments that are statistical outliers for at least one input issue
        for text in (profile.issues or [profile.fact_text]):
            if not text.strip():
                continue
            sims = ix.similarity(text, "issue")
            vals = list(sims.values())
            if profile.issues and len(vals) >= 5:
                mu = sum(vals) / len(vals)
                sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5
                cut = max(cfg.principle_min_raw, mu + cfg.principle_z * sd)
                issue_hit.update(i for i, c in sims.items() if c >= cut)
            for i, c in sims.items():
                issue_sims[i] = max(issue_sims.get(i, 0.0), c)

        substantive_keys = [k for k, kind in profile.key_kinds.items() if kind in ("offence", "special")]
        cand: Set[int] = ix.candidates_by_keys(substantive_keys)
        cand.update(sorted(fact_sims, key=fact_sims.get, reverse=True)[: cfg.top_fact_neighbours])
        if profile.issues:
            cand.update(issue_hit)

        scored: List[Dict[str, Any]] = []
        for i in cand:
            r = ix.records[i]
            stage = affinity.get(r.stage, 0.2)
            if stage < cfg.stage_floor:
                continue
            fact = min(1.0, fact_sims.get(i, 0.0) / ix.fact_scale)
            issue = min(1.0, issue_sims.get(i, 0.0) / ix.issue_scale)
            cat_sim = category_similarity(profile.categories, r.categories) if profile.categories else 0.0

            matched_w = 0.0
            matched_keys: List[str] = []
            for k, w in profile.key_weights.items():
                if k in r.keys:
                    matched_w += w
                    matched_keys.append(k)
                else:
                    parent = re.sub(r"\(.*", "", k) if "(" in k else None
                    if parent and parent in r.keys:
                        matched_w += 0.5 * w
                        matched_keys.append(parent)
            exact = min(1.0, matched_w / profile.total_weight)
            substantive_hit = any(k in r.substantive_keys for k in substantive_keys)
            statutory = 0.6 * exact + 0.4 * cat_sim

            if profile.categories:
                case_ok = cat_sim >= cfg.min_category_similarity or substantive_hit
            else:
                case_ok = fact >= 0.5 or substantive_hit      # no offence categories known: fall back to facts
            principle_ok = (not case_ok) and (i in issue_hit)
            if not (case_ok or principle_ok):
                continue

            authority = ix.authority(i)
            relevance = (WEIGHTS["stage"] * stage + WEIGHTS["fact"] * fact + WEIGHTS["statutory"] * statutory
                         + WEIGHTS["issue"] * issue + WEIGHTS["authority"] * authority)
            per_role = {
                role: {"principle": round(issue, 3), "direction": round(r.direction.get(role, 0.5), 3),
                       "score": round((1 - DIRECTION_WEIGHT) * relevance + DIRECTION_WEIGHT * r.direction.get(role, 0.5), 4)}
                for role in ROLES
            }
            scored.append({
                "idx": i, "channel": "case" if case_ok else "principle", "relevance": relevance,
                "breakdown": {
                    "stage": round(stage, 3), "fact": round(fact, 3), "statutory": round(statutory, 3),
                    "category_similarity": round(cat_sim, 3), "issue": round(issue, 3), "authority": authority,
                    "matched_inputs": sorted(matched_keys), "by_role": per_role,
                },
                "role_scores": {**{r_: per_role[r_]["score"] for r_ in ROLES}, "neutral": round(relevance, 4)},
            })
        return scored

    # -- materialisation (loads full JSON only for returned cases) ---------------

    def _materialise(self, row: Dict[str, Any], input_statutes: List[Dict[str, Any]]) -> Optional[PrecedentCandidate]:
        rec = self.index.records[row["idx"]]
        data = self.index.load_full(rec)
        if data is None:
            return None
        case = data.get("case", {}) or {}
        meta = data.get("doc_meta", {}) or {}
        jstat = case.get("statutes", []) or []
        match_count, matched = self.matcher.match_statutes(input_statutes, jstat, allow_parent_match=True)
        n_unique = len(matched)
        exact_ratio = (sum(1 for m in matched if m.get("match_type") == "exact") / n_unique) if n_unique else 0
        legacy = match_count + (n_unique / len(input_statutes) if input_statutes else 0) * 0.5 + exact_ratio * 0.3
        citation = meta.get("citation_scr") or meta.get("citation_neutral") or meta.get("case_no") or None
        return PrecedentCandidate(
            case_id=data.get("case_id", rec.case_id), case_name=case.get("case_name", "Unknown Case"),
            court=case.get("court", "Unknown Court"), decided_on=meta.get("decided_on", ""), citation=citation,
            disposition=case.get("disposition", ""), procedural_stage=case.get("procedural_stage", ""),
            matched_statutes=matched, match_score=legacy, total_statutes=len(jstat),
            abstract_facts=case.get("abstract_facts", ""), statutes=jstat, propositions=case.get("propositions", []),
            issues=case.get("issues", []), authorities=case.get("authorities", []), source_file=meta.get("source_file", ""),
            inferred_stage=rec.stage, case_facets=sorted(rec.categories), score_breakdown=row["breakdown"],
            role_scores=row["role_scores"], retrieval_score=row["role_scores"]["neutral"], channel=row["channel"],
            offence_types=[str(x) for x in (case.get("offence_types") or [])],
            dispute_nature=str(case.get("dispute_nature") or ""),
            lower_court_outcome=str(case.get("lower_court_outcome") or ""),
            verdicts=data.get("verdicts") or {},
        )

    def _profile(self, stage4_result: Dict, case_context: Optional[Dict]) -> RetrievalProfile:
        return build_profile(self.matcher, self.index, stage4_result, case_context)

    def _scan(self, stage4_result: Dict, case_context: Optional[Dict]) -> Tuple[RetrievalProfile, List[Dict[str, Any]]]:
        profile = self._profile(stage4_result, case_context)
        if not profile.statutes:
            print("[PrecedentRetriever] No statutes found in Stage 4 result")
            return profile, []
        print(f"[PrecedentRetriever] Profile: stage={profile.stage_mode}, categories={sorted(profile.categories)}")
        for s in profile.statutes:
            print(f"  - {s['act']} {s['section']}  [{s['kind']}, weight {s['weight']}]")
        rows = self._score_all(profile)
        n = len(self.index.records)
        print(f"[PrecedentRetriever] {n} judgments indexed, {len(rows)} passed (case: "
              f"{sum(r['channel']=='case' for r in rows)}, principle: {sum(r['channel']=='principle' for r in rows)})")
        return profile, rows

    # -- public API ------------------------------------------------------------

    def shortlist_by_statutes(self, stage4_result: Dict, case_context: Optional[Dict] = None,
                              n: Optional[int] = None) -> Dict[str, Any]:
        """
        Deterministic first step (no LLM). Cross-checks the statutes of Stage 4 (IPC/BNS, CrPC/BNSS, IEA/BSA and special
        Acts, all mapped to one regime) against the `statutes` of every judgment.

            score = sum(weight * idf of matched keys) / sum(weight * idf of all input keys)

        IDF is computed on the corpus, so a section present in almost every judgment (CrPC 438 in an anticipatory-bail
        corpus) contributes almost nothing. Threshold: a judgment must match at least one non-generic key (document
        frequency <= cfg.ubiquitous_df), and must score >= cfg.shortlist_rel_cut x the best score. If every input key is
        generic, the non-generic requirement is dropped. Ties are broken by stage affinity, then fact similarity.
        """
        cfg, ix = self.config, self.index
        n = n or cfg.shortlist_size
        profile = self._profile(stage4_result, case_context)
        N = max(1, len(ix.records))
        weights = {k: w for k, w in profile.key_weights.items() if w > 0}
        if not weights:
            print("[PrecedentRetriever] No statutes found in Stage 4 result")
            return {"candidates": [], "profile": profile.summary(), "stats": {"scanned": N, "passed": 0}}

        def idf(k: str) -> float:
            return math.log(1.0 + N / (1.0 + len(ix.key_postings.get(k, ()))))

        def df_share(k: str) -> float:
            return len(ix.key_postings.get(k, ())) / N

        specific = {k for k in weights if df_share(k) <= cfg.ubiquitous_df}
        denom = sum(w * idf(k) for k, w in weights.items()) or 1.0
        parents = {k: re.sub(r"\(.*", "", k) for k in weights if "(" in k}
        cand: Set[int] = ix.candidates_by_keys(list(weights) + list(parents.values()))
        fact_sims = ix.similarity(profile.fact_text, "fact") if profile.fact_text.strip() else {}
        affinity = STAGE_AFFINITY[profile.stage_mode]
        rows: List[Dict[str, Any]] = []
        for i in cand:
            r = ix.records[i]
            got, matched, hit_specific = 0.0, [], False
            for k, w in weights.items():
                if k in r.keys:
                    got += w * idf(k); matched.append(k); hit_specific |= k in specific
                elif k in parents and parents[k] in r.keys:
                    got += 0.5 * w * idf(k); matched.append(parents[k]); hit_specific |= k in specific
            if not matched or (specific and not hit_specific):
                continue
            score = got / denom
            stage = affinity.get(r.stage, 0.2)
            fact = min(1.0, fact_sims.get(i, 0.0) / ix.fact_scale)
            rows.append({"idx": i, "score": score, "stage": stage, "fact": fact, "matched": sorted(set(matched))})
        if not rows:
            return {"candidates": [], "profile": profile.summary(), "stats": {"scanned": N, "passed": 0}}
        best = max(x["score"] for x in rows)
        rows = [x for x in rows if x["score"] >= cfg.shortlist_rel_cut * best]
        rows.sort(key=lambda x: (round(x["score"], 3), x["stage"], x["fact"]), reverse=True)
        rows = rows[:n]
        out: List[PrecedentCandidate] = []
        for x in rows:
            r = ix.records[x["idx"]]
            authority = ix.authority(x["idx"])
            cat_sim = category_similarity(profile.categories, r.categories) if profile.categories else 0.0
            per_role = {role: {"principle": 0.4, "direction": round(r.direction.get(role, 0.5), 3),
                               "score": round(x["score"], 4)} for role in ROLES}
            row = {"idx": x["idx"], "channel": "case", "relevance": x["score"],
                   "breakdown": {"stage": round(x["stage"], 3), "fact": round(x["fact"], 3),
                                 "statutory": round(x["score"], 3), "category_similarity": round(cat_sim, 3),
                                 "issue": 0.0, "authority": authority, "matched_inputs": x["matched"], "by_role": per_role},
                   "role_scores": {**{r_: round(x["score"], 4) for r_ in ROLES}, "neutral": round(x["score"], 4)}}
            c = self._materialise(row, profile.statutes)
            if c:
                out.append(c)
        print(f"[PrecedentRetriever] Statute shortlist: {len(cand)} judgments share a key, {len(rows)} kept "
              f"(generic keys: {sorted(set(weights) - specific)})")
        for i, c in enumerate(out[:8], 1):
            print(f"  {i}. {c.case_name} score={c.retrieval_score:.3f} matched={c.score_breakdown['matched_inputs']}")
        return {"candidates": out, "profile": profile.summary(),
                "stats": {"scanned": N, "passed": len(rows), "generic_keys": sorted(set(weights) - specific)}}

    def retrieve_candidates(self, stage4_result: Dict, case_context: Optional[Dict] = None,
                            role: Optional[str] = None) -> List[PrecedentCandidate]:
        profile, rows = self._scan(stage4_result, case_context)
        key = role if role in ROLES else "neutral"
        rows = sorted((r for r in rows if r["channel"] == "case"), key=lambda r: r["role_scores"][key], reverse=True)
        out = [c for c in (self._materialise(r, profile.statutes) for r in rows[: self.max_candidates]) if c]
        self._print_top(out, key)
        return out

    def retrieve_by_role(self, stage4_result: Dict, case_context: Optional[Dict] = None, top_k: int = 8) -> Dict[str, Any]:
        """
        {"prosecution": [...], "defense": [...], "shared_ids": [...], "principle_ids": [...], "profile": {...}}

        Each pool = top_k "case" candidates for that role + the (few) "principle" candidates whose issues match an
        issue raised by the input. Principle candidates are evaluated for both sides.
        """
        profile, rows = self._scan(stage4_result, case_context)
        case_rows = [r for r in rows if r["channel"] == "case"]
        pr_rows = sorted((r for r in rows if r["channel"] == "principle"),
                         key=lambda r: r["breakdown"]["issue"] * (0.5 + r["breakdown"]["authority"]), reverse=True)[: self.config.max_principle]
        cache: Dict[int, Optional[PrecedentCandidate]] = {}

        def mat(r: Dict[str, Any]) -> Optional[PrecedentCandidate]:
            if r["idx"] not in cache:
                cache[r["idx"]] = self._materialise(r, profile.statutes)
            return cache[r["idx"]]

        principle = [c for c in (mat(r) for r in pr_rows) if c]
        pools: Dict[str, List[PrecedentCandidate]] = {}
        for role in ROLES:
            top = sorted(case_rows, key=lambda r: r["role_scores"][role], reverse=True)[:top_k]
            pools[role] = [c for c in (mat(r) for r in top) if c] + principle
            self._print_top(pools[role], role)
        if principle:
            print(f"[PrecedentRetriever] Principle-channel cases (issue-matched): {[c.case_name for c in principle]}")
        shared = [c.case_id for c in pools["prosecution"] if c.case_id in {d.case_id for d in pools["defense"]}]
        return {**pools, "shared_ids": shared, "principle_ids": [c.case_id for c in principle], "profile": profile.summary()}

    @staticmethod
    def _print_top(shortlist: List[PrecedentCandidate], key: str, n: int = 5) -> None:
        print(f"[PrecedentRetriever] Top {min(n, len(shortlist))} for {key}:")
        for i, c in enumerate(shortlist[:n], 1):
            b = c.score_breakdown
            print(f"  {i}. {c.case_name} score={c.role_scores.get(key, 0):.3f} [{c.channel}] "
                  f"(stage {b.get('stage')}/{c.inferred_stage}, fact {b.get('fact')}, cat {b.get('category_similarity')}, "
                  f"issue {b.get('issue')}, auth {b.get('authority')})")

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
    stage4 = {"verified_offences": [
        {"statute": "IPC", "section_number": "420", "overall_prima_facie_strength": "Strong", "overall_status": "Prima Facie Attracted"}]}
    ctx = {"requested_relief": "Anticipatory Bail", "case_facts": "Allegation of cheating in a commercial transaction."}
    retriever = PrecedentRetriever(max_candidates=10)
    result = retriever.retrieve_by_role(stage4, ctx, top_k=5)
    print(json.dumps(result["profile"], indent=2))


if __name__ == "__main__":
    test_precedent_retrieval()