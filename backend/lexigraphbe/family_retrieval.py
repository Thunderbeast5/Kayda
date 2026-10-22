"""
Family-constrained statutory retrieval (replaces heading-anchored concept labels and the
deterministic sub-query expander).

Division of labour
------------------
* Stage 1 (LLM) only does two constrained things:
    1. extracts factual allegations as VERBATIM quotes from the narrative, and
    2. tags them with offence FAMILIES chosen from a closed list (OFFENCE_FAMILIES), plus a
       short conduct phrase used only to rank sections inside that family.
  It never names sections or section headings.
* This module (Python, 0 LLM calls):
    - validates the Stage 1 output (quotes really occur in the narrative, family codes are in
      the closed list, fact ids exist, ACT facts are covered by some family);
    - ranks IPC sections inside each chosen family against the quoted facts (BM25);
    - runs a family-independent safety-net search on every charge-bearing fact, so an offence
      the LLM overlooked can still surface;
    - links definition sections to their punishment sections using ipc.json's own
      "Punishment for/of ..." headings (e.g. 107 -> 109, 120A -> 120B, 503 -> 506).

Families come from lexigraphbe.offence_taxonomy, which is derived from the IPC's chapter
structure; nothing here is specific to a case.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .classifier_prefilter import (
    CandidateSectionMatch,
    StatuteClassifierPrefilter,
    _QUERY_ONLY_STOP_STEMS,
    _tokenize,
)
from .offence_taxonomy import ipc_categories
from .statute_repository import StatuteRepository

# ---------------------------------------------------------------------------
# Closed list of offence families shown to the Stage 1 LLM.
# Keys are the category codes produced by offence_taxonomy.ipc_categories (IPC chapter structure);
# descriptions are generic legal descriptions of the family, not of any case.
# ---------------------------------------------------------------------------
OFFENCE_FAMILIES: Dict[str, str] = {
    "HOMICIDE": "causing death: murder, culpable homicide, death by rash or negligent act, dowry death, abetment of suicide, attempt to murder",
    "HURT": "causing bodily pain, injury or grievous hurt, including with weapons, acid or dangerous means; endangering life or personal safety",
    "RESTRAINT_ASSAULT": "wrongful restraint or confinement, criminal force, assault, outraging the modesty of a woman",
    "SEXUAL_OFFENCE": "rape and sexual assault, sexual harassment, voyeurism, stalking",
    "KIDNAPPING_TRAFFICKING": "kidnapping, abduction, trafficking, wrongful concealment of a kidnapped person",
    "MISCARRIAGE_CHILD": "causing miscarriage, injury to unborn child, exposure or abandonment of a child",
    "THEFT": "dishonestly taking movable property out of another's possession",
    "EXTORTION": "obtaining property by putting a person in fear of injury",
    "ROBBERY_DACOITY": "theft or extortion with violence or threat of instant violence, by one person or a gang",
    "MISAPPROPRIATION_BREACH_OF_TRUST": "dishonest misappropriation of property, criminal breach of trust by an entrusted person",
    "STOLEN_PROPERTY": "receiving or retaining stolen property",
    "CHEATING": "deceiving a person to deliver property or to act to their harm, including by personation",
    "FRAUDULENT_TRANSFER": "fraudulent deeds and dispositions of property, removal or concealment of property to defeat creditors",
    "MISCHIEF": "destroying or damaging property, including by fire or explosive",
    "TRESPASS": "entering or remaining on property or in a house in another's possession with intent to commit an offence, intimidate, insult or annoy",
    "FORGERY": "making a false document or electronic record, forgery, using a forged document as genuine, falsification of accounts",
    "TRADEMARK_CURRENCY": "false property or trade marks, counterfeit currency or bank notes",
    "FALSE_EVIDENCE_JUSTICE": "false evidence, fabricating evidence, destroying evidence or documents, false information about an offence, screening an offender, offences against public justice",
    "CONTEMPT_OF_AUTHORITY": "disobeying or obstructing public servants, absconding from summons, false statements to public servants",
    "CORRUPTION": "offences by or relating to public servants, bribery, election offences",
    "PUBLIC_ORDER": "unlawful assembly, rioting, affray, promoting enmity between groups",
    "PUBLIC_HEALTH_SAFETY_NUISANCE": "spreading infectious disease, adulteration of food or drugs, rash driving, dangerous handling of fire, poison or explosives, obscenity, public nuisance",
    "RELIGION": "injuring places of worship, outraging religious feelings, disturbing religious assembly",
    "MARRIAGE_CRUELTY": "cruelty to a wife by husband or relatives, dowry harassment",
    "MARRIAGE_RELATED": "bigamy, deceitful marriage, adultery-related offences",
    "DEFAMATION": "making or publishing imputations harming a person's reputation",
    "INTIMIDATION_INSULT": "criminal intimidation by threats, intentional insult to provoke breach of peace, words or gestures insulting a woman's modesty",
    "OFFENCE_AGAINST_STATE": "waging war, sedition, offences against the State",
    "COUNTERFEIT_COIN_STAMPS": "counterfeiting coins or government stamps",
    "ABETMENT": "instigating, engaging in a conspiracy for, or intentionally aiding another's offence",
    "CONSPIRACY": "agreement between two or more persons to commit an offence or an illegal act",
    "COMMON_INTENTION": "an act done by several persons in furtherance of their common intention",
    "ATTEMPT": "attempting to commit an offence",
}

_TIERS = {"PRIMARY", "SECONDARY", "CONDITIONAL"}
_CHARGE_BEARING = {"ACT", "OMISSION", "RESULT", "CONDITION"}
_GENERIC_PUNISHMENT_SECTIONS = {"2", "3", "72", "511"}


def family_prompt_block() -> str:
    """Compact closed-list block injected into the Stage 1 prompt (~350 tokens)."""
    return "\n".join(f"- {code}: {desc}" for code, desc in OFFENCE_FAMILIES.items())


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _obj(o: Any, name: str, default: Any = None) -> Any:
    if isinstance(o, dict):
        return o.get(name, default)
    return getattr(o, name, default)


# ---------------------------------------------------------------------------
# Validation of Stage 1 output (deterministic)
# ---------------------------------------------------------------------------
@dataclass
class DecompositionCheck:
    ok: bool
    issues: List[str] = field(default_factory=list)
    ungrounded_fact_ids: List[str] = field(default_factory=list)
    invalid_families: List[str] = field(default_factory=list)
    uncovered_fact_ids: List[str] = field(default_factory=list)


def validate_decomposition(narrative: str, facts: Iterable[Any], families: Iterable[Any]) -> DecompositionCheck:
    facts = list(facts or [])
    families = list(families or [])
    issues: List[str] = []
    norm_narr = _norm_ws(narrative)
    fact_ids = {str(_obj(f, "fact_id", "")) for f in facts}

    ungrounded = []
    if norm_narr:
        for f in facts:
            quote = _norm_ws(_obj(f, "verbatim_quote") or "")
            if not quote or quote not in norm_narr:
                ungrounded.append(str(_obj(f, "fact_id", "?")))
    if ungrounded:
        issues.append(f"Facts without a verbatim quote found in the narrative: {ungrounded}")

    invalid, covered = [], set()
    for fam in families:
        code = str(_obj(fam, "family", "")).strip().upper()
        if code not in OFFENCE_FAMILIES:
            invalid.append(code)
            continue
        refs = [str(x) for x in (_obj(fam, "fact_ids", []) or [])]
        missing = [x for x in refs if x not in fact_ids]
        if not refs or missing:
            issues.append(f"Family {code} cites unknown or no fact ids: {missing or 'none'}")
        covered.update(refs)
    if invalid:
        issues.append(f"Families outside the closed list were rejected: {invalid}")

    uncovered = [str(_obj(f, "fact_id", "")) for f in facts
                 if str(_obj(f, "conduct_type", "")).upper() in {"ACT", "OMISSION"}
                 and str(_obj(f, "fact_id", "")) not in covered]
    if uncovered:
        issues.append(f"Alleged acts not covered by any offence family (safety-net retrieval still runs): {uncovered}")

    return DecompositionCheck(ok=not (ungrounded or invalid), issues=issues,
                              ungrounded_fact_ids=ungrounded, invalid_families=invalid,
                              uncovered_fact_ids=uncovered)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def reciprocal_rank_fusion(
    rankings: List[List[Tuple[int, float, List[str], float]]],
    k: int = 60,
) -> List[Tuple[int, float, List[str], float]]:
    """
    Combines multiple independent rankings using Reciprocal Rank Fusion (RRF).
    Formula: RRF_score(d) = sum_{r in rankings} 1.0 / (k + rank_r(d))
    """
    rrf_scores: Dict[int, float] = {}
    doc_matched: Dict[int, Set[str]] = {}
    doc_mass: Dict[int, float] = {}

    for ranking in rankings:
        for rank_idx, (doc_idx, _score, matched, mass) in enumerate(ranking, start=1):
            rrf_scores[doc_idx] = rrf_scores.get(doc_idx, 0.0) + (1.0 / (k + rank_idx))
            doc_matched.setdefault(doc_idx, set()).update(matched)
            doc_mass[doc_idx] = max(doc_mass.get(doc_idx, 0.0), mass)

    fused = [
        (doc_idx, rrf_score, sorted(doc_matched[doc_idx]), doc_mass[doc_idx])
        for doc_idx, rrf_score in rrf_scores.items()
    ]
    fused.sort(key=lambda x: x[1], reverse=True)
    return fused


class FamilyRetriever:
    def __init__(self, prefilter: Optional[StatuteClassifierPrefilter] = None):
        self.pf = prefilter or StatuteClassifierPrefilter()
        self.records = self.pf.sections_db
        self.idx_by_sec = {r["section_number"]: i for i, r in enumerate(self.records)}
        self.family_members: Dict[str, List[int]] = {}
        for i, r in enumerate(self.records):
            if self.pf._is_non_offence_section(r):
                continue
            for cat in ipc_categories(r["section_number"]):
                self.family_members.setdefault(cat, []).append(i)
        # Short offence titles ("mischief", "public nuisance") name the base offence that derived sections build on.
        self.offence_names: Dict[str, str] = {}
        for r in self.records:
            if self.pf._is_non_offence_section(r):
                continue
            title = (r.get("title") or "").strip().lower().rstrip(".")
            if title and len(title.split()) <= 3 and not title.startswith("punishment"):
                self.offence_names.setdefault(title, r["section_number"])
        self.punishment_links = self._build_punishment_links()
        self._add_reference_links()
        self.negligence_sections = self._build_negligence_sections()

    def _add_reference_links(self) -> None:
        """Links a "Punishment ..." section to the definition its ingredients cite when the heading match found
        none (290 "Punishment for public nuisance ..." cites s. 268, 22 sections earlier)."""
        try:
            statute_db = StatuteRepository.get_instance().get_statute_db() or {}
        except Exception:
            return
        for rec in self.records:
            sec = rec["section_number"]
            if sec in self.punishment_links or not re.match(r"(?i)\s*punishment\s", rec.get("title") or ""):
                continue
            ings = " ".join(str(i) for i in ((statute_db.get(f"IPC_{sec}") or {}).get("ingredients") or []))
            for ref in re.findall(r"\b(?:section|s\.)\s*(\d+[A-Z]*)", ings, re.IGNORECASE):
                ref = ref.upper()
                if ref in self.idx_by_sec and ref != sec and ref not in _GENERIC_PUNISHMENT_SECTIONS:
                    self.punishment_links.setdefault(sec, set()).add(ref)
                    self.punishment_links.setdefault(ref, set()).add(sec)

    def _build_negligence_sections(self) -> Set[str]:
        """Sections whose fault element is rashness or negligence, read from their title and ingredients."""
        try:
            statute_db = StatuteRepository.get_instance().get_statute_db() or {}
        except Exception:
            statute_db = {}
        out: Set[str] = set()
        for rec in self.records:
            sec = rec["section_number"]
            ext = statute_db.get(f"IPC_{sec}") or {}
            text = " ".join([rec.get("title") or ""] + [str(i) for i in (ext.get("ingredients") or [])])
            if re.search(r"\b(rash\w*|negligen\w*)\b", text, re.IGNORECASE):
                out.add(sec)
        return out

    # -- definition <-> punishment links, derived from ipc.json headings --
    def _build_punishment_links(self) -> Dict[str, Set[str]]:
        """
        Pairs each "Punishment for/of X" section with the preceding section(s) in the same chapter
        whose heading best matches X (highest Jaccard over stemmed heading tokens; ties kept).
        A definition is linked only to the nearest punishment section that chose it, so
        107 -> 109 (not 110), 442 -> 448, 321 -> 323, 191/192 -> 193.
        """
        best_defs: Dict[str, List[str]] = {}
        for i, rec in enumerate(self.records):
            sec, head = rec["section_number"], rec.get("title") or ""
            m = re.match(r"(?i)\s*punishment\s+(?:for|of)\s+(.*)", head)
            if not m or sec in _GENERIC_PUNISHMENT_SECTIONS:
                continue
            target = set(_tokenize(m.group(1)))
            if not target:
                continue
            scored = []
            for j in range(max(0, i - 15), i):
                cand = self.records[j]
                if cand.get("chapter") != rec.get("chapter"):
                    continue
                if re.match(r"(?i)\s*punishment\s", cand.get("title") or ""):
                    continue
                ctoks = set(_tokenize(cand.get("title") or ""))
                if not ctoks:
                    continue
                inter = len(target & ctoks)
                coverage = inter / len(ctoks)          # how much of the definition heading is named
                jac = inter / len(target | ctoks)      # tie-breaker
                if coverage >= 0.5:
                    scored.append(((coverage, jac), cand["section_number"]))
            if scored:
                top = max(s for s, _ in scored)
                best_defs[sec] = [d for s, d in scored if s == top]

        links: Dict[str, Set[str]] = {}
        claimed: Set[str] = set()
        for psec, defs in best_defs.items():  # records order == statute order
            links.setdefault(psec, set()).update(defs)
            for d in defs:
                if d not in claimed:
                    links.setdefault(d, set()).add(psec)
                    claimed.add(d)
        return links

    def _score(self, idxs: Iterable[int], text: str) -> List[Tuple[int, float, List[str], float]]:
        """Returns [(record index, bm25 score, matched terms, coverage of query IDF mass)] best-first."""
        bm25 = self.pf._get_bm25()
        weights = {t: 1.0 for t in set(_tokenize(text)) - _QUERY_ONLY_STOP_STEMS}
        total = bm25.total_mass(weights) if weights else 0.0
        if total <= 0:
            return []
        out = []
        for i in idxs:
            raw, matched, mass = bm25.score(i, weights)
            if raw > 0:
                out.append((i, raw, matched, mass / total))
        out.sort(key=lambda x: x[1], reverse=True)
        return out

    def retrieve(
        self,
        facts: Iterable[Any],
        families: Iterable[Any],
        per_family: int = 3,
        family_min_rel: float = 0.5,
        per_fact_safety_net: int = 2,
        safety_net_min_coverage: float = 0.5,
        per_negligent: int = 2,
    ) -> Tuple[List[CandidateSectionMatch], Dict[str, Any]]:
        facts = list(facts or [])
        fact_text = {str(_obj(f, "fact_id", "")): (_obj(f, "verbatim_quote") or _obj(f, "description") or "")
                     for f in facts}
        chosen: Dict[str, Dict[str, Any]] = {}
        diag: Dict[str, Any] = {"by_family": {}, "safety_net": {}, "linked": {}}

        def add(i: int, score: float, matched: List[str], via: str, classification: str = "PRIMARY") -> None:
            rec = self.records[i]
            key = rec["section_number"]
            if key not in chosen or score > chosen[key]["score"]:
                chosen[key] = {
                    "rec": rec,
                    "score": score,
                    "matched": matched,
                    "via": [via],
                    "classification": classification,
                }
            elif via not in chosen[key]["via"]:
                chosen[key]["via"].append(via)

        # 1. Family-restricted ranking with Reciprocal Rank Fusion across 3 query views
        for fam in families or []:
            code = str(_obj(fam, "family", "")).strip().upper()
            if code not in OFFENCE_FAMILIES:
                continue
            members = self.family_members.get(code, [])
            if not members:
                diag["by_family"][code] = []
                continue

            refs = [str(x) for x in (_obj(fam, "fact_ids", []) or [])]
            phrase = str(_obj(fam, "conduct_phrase", "") or "")
            text = " ".join(fact_text.get(r, "") for r in refs) + " " + phrase

            # View 1: Combined family facts + conduct phrase
            r_combined = self._score(members, text)
            rankings = [r_combined] if r_combined else []

            # View 2: Individual facts
            if len(refs) > 1:
                for r in refs:
                    r_indiv = self._score(members, fact_text.get(r, ""))
                    if r_indiv:
                        rankings.append(r_indiv)

            # View 3: the conduct phrase on its own. The generic family description is not used as a
            # query: its example words ("acid", "fire") outranked the facts (e.g. 326A for a bridge collapse).
            if phrase:
                r_phrase = self._score(members, phrase)
                if r_phrase:
                    rankings.append(r_phrase)

            if not rankings or not rankings[0]:
                diag["by_family"][code] = []
                continue

            # Fuse rankings using RRF
            fused = reciprocal_rank_fusion(rankings, k=60)
            if not fused:
                diag["by_family"][code] = []
                continue

            top_rrf = fused[0][1]
            picked = [x for x in fused[:per_family] if x[1] / top_rrf >= family_min_rel]

            diag["by_family"][code] = [self.records[i]["section_number"] for i, *_ in picked]
            for i, rrf_score, matched, _cov in picked:
                norm_score = round(min(1.0, rrf_score / top_rrf), 3)
                add(i, norm_score, matched, f"family:{code}", classification="PRIMARY")

            # Rash / negligent forms of the family are ranked separately so that intention-based sections
            # cannot crowd them out (a collapse injuring people must surface 337/338, not only 323-326).
            # Whether the conduct was in fact rash or negligent is decided in Stage 4.
            fault = str(_obj(fam, "fault_mode", "UNSTATED") or "UNSTATED").upper()
            neg_members = [i for i in members if self.records[i]["section_number"] in self.negligence_sections]
            if neg_members and fault not in {"INTENTIONAL", "KNOWING"}:
                r_neg = self._score(neg_members, text)
                for i, raw, matched, _cov in r_neg[:per_negligent]:
                    add(i, round(min(1.0, raw / r_neg[0][1]) * 0.8, 3), matched, f"family:{code}", classification="PRIMARY")
                    if self.records[i]["section_number"] not in diag["by_family"][code]:
                        diag["by_family"][code].append(self.records[i]["section_number"])

        # 2. Family-independent safety net over every charge-bearing fact
        all_idx = [i for members in self.family_members.values() for i in members]
        all_idx = sorted(set(all_idx))
        for f in facts:
            if str(_obj(f, "conduct_type", "ACT")).upper() not in _CHARGE_BEARING:
                continue
            fid = str(_obj(f, "fact_id", ""))
            ranked = self._score(all_idx, fact_text.get(fid, ""))
            if not ranked:
                continue
            top = ranked[0][1]
            # Noise control: require >= 2 distinct matched terms and IDF mass coverage >= 0.6
            picked = [x for x in ranked[:per_fact_safety_net]
                      if x[3] >= max(safety_net_min_coverage, 0.6) and len(set(x[2])) >= 2]
            diag["safety_net"][fid] = [self.records[i]["section_number"] for i, *_ in picked]
            for i, raw, matched, _cov in picked:
                add(i, round(0.5 * raw / top, 3), matched, f"fact:{fid}", classification="CONDITIONAL")

        # 3. Definition <-> punishment links (data-derived)
        for sec in list(chosen):
            for linked in sorted(self.punishment_links.get(sec, ())):
                if linked not in chosen and linked in self.idx_by_sec:
                    i = self.idx_by_sec[linked]
                    add(i, chosen[sec]["score"], ["linked"], f"linked:{sec}", classification="AUGMENTED")
                    diag["linked"].setdefault(sec, []).append(linked)

        matches = [
            CandidateSectionMatch(
                section_identifier=v["rec"]["identifier"], statute=v["rec"]["statute"],
                section_number=k, title=v["rec"]["title"], chapter=v["rec"]["chapter"],
                score=v["score"], matched_terms=v["matched"][:5], matched_concepts=v["via"],
                classification=v.get("classification", "PRIMARY"),
            )
            for k, v in chosen.items()
        ]
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches, diag


# ---------------------------------------------------------------------------
# Deterministic top-up of the LLM's family tagging (no case-specific rules)
# ---------------------------------------------------------------------------
_JOINT_FAMILIES = (
    ("COMMON_INTENTION", "whether the accused shared a common intention"),
    ("ABETMENT", "whether one accused instigated or intentionally aided the other"),
    ("CONSPIRACY", "whether there was an agreement between the accused"),
)
_ACTOR_SPLIT = re.compile(r"\s*(?:,|;|&|\band\b|\balong with\b|\btogether with\b)\s*", re.IGNORECASE)

_RETRIEVER_SINGLETON: Optional["FamilyRetriever"] = None


def get_family_retriever() -> "FamilyRetriever":
    global _RETRIEVER_SINGLETON
    if _RETRIEVER_SINGLETON is None:
        _RETRIEVER_SINGLETON = FamilyRetriever()
    return _RETRIEVER_SINGLETON


def augment_families(
    facts: Iterable[Any],
    families: Iterable[Any],
    retriever: Optional["FamilyRetriever"] = None,
    top_n: int = 3,
    min_coverage: float = 0.5,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Adds offence families the LLM did not tag, from two structural signals:
      1. retrieval: a charge-bearing fact's quote strongly matches sections of a family
         (coverage of the quote's distinctive vocabulary >= min_coverage and >= 2 matched terms);
         the family is the matched section's IPC chapter category;
      2. joint conduct: a fact's actor field names two or more persons -> joint-liability families
         as CONDITIONAL, with the unestablished element recorded.
    Returns (families as dicts, notes). Never removes or edits what the LLM produced.
    """
    r = retriever or get_family_retriever()
    facts = list(facts or [])
    fams: List[Dict[str, Any]] = []
    for f in families or []:
        d = f.model_dump() if hasattr(f, "model_dump") else dict(f)
        d["family"] = str(d.get("family", "")).upper()
        d.setdefault("fact_ids", [])
        fams.append(d)
    by_code = {d["family"]: d for d in fams}
    notes: List[str] = []

    def ensure(code: str, fid: str, tier: str, unresolved: Optional[List[str]] = None, why: str = "",
               phrase: str = "") -> None:
        if code not in OFFENCE_FAMILIES:
            return
        if code in by_code:
            if fid not in by_code[code]["fact_ids"]:
                by_code[code]["fact_ids"].append(fid)
            return
        d = {"family": code, "fact_ids": [fid], "tier": tier, "conduct_phrase": phrase,
             "unresolved_elements": list(unresolved or [])}
        fams.append(d)
        by_code[code] = d
        notes.append(f"Family {code} added for {fid} ({why}).")

    all_idx = sorted({i for members in r.family_members.values() for i in members})
    for f in facts:
        fid = str(_obj(f, "fact_id", ""))
        if str(_obj(f, "conduct_type", "ACT")).upper() not in _CHARGE_BEARING:
            continue
        text = _obj(f, "verbatim_quote") or _obj(f, "description") or ""
        n_tokens = len(set(_tokenize(text)) - _QUERY_ONLY_STOP_STEMS)
        ranked = r._score(all_idx, text)[:8]
        if n_tokens == 1:
            # A one-word act ("abused") supports only its single best match.
            hits = ranked[:1]
        else:
            hits = [x for x in ranked if len(set(x[2])) >= 2]
        fam_score: Dict[str, float] = {}
        fam_hits: Dict[str, List[str]] = {}
        for i, raw, matched, cov in hits:
            sec = r.records[i]["section_number"]
            for code in ipc_categories(sec):
                fam_score[code] = fam_score.get(code, 0.0) + raw
                fam_hits.setdefault(code, []).append(sec)
        if fam_score:
            best = max(fam_score.values())
            for code, sc in fam_score.items():
                # Multiple independent signals required: >= 2 distinct section hits
                # and substantial score relative to best family (>= 0.5 * best).
                # Eliminates single-best-family false positive noise.
                if len(fam_hits[code]) >= 2 and sc >= 0.5 * best:
                    ensure(code, fid, "SECONDARY", why=f"quote matches IPC {', '.join(fam_hits[code][:3])}")

        actors = [a for a in _ACTOR_SPLIT.split(str(_obj(f, "actor", "") or "")) if a.strip()]
        if len(actors) >= 2:
            for code, element in _JOINT_FAMILIES:
                # The fact quote describes the underlying act, not the joint conduct, so the family's
                # generic description supplies the vocabulary that ranks sections inside the family.
                ensure(code, fid, "CONDITIONAL", [element], why=f"joint actors: {', '.join(actors)}",
                       phrase=OFFENCE_FAMILIES[code])
    return fams, notes


# ---------------------------------------------------------------------------
# Deterministic Stage 2 mapping for family-tagged queries (0 LLM calls)
# ---------------------------------------------------------------------------
def build_family_mapping(
    query_obj: Any,
    retriever: Optional["FamilyRetriever"] = None,
    nominations: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """
    Builds a Stage2BatchedMappingResponse-shaped dict from family retrieval:
      * one mapping per Stage 1 sub-query (one sub-query per family, same order);
      * a section retrieved inside a family goes to that family's sub-query with the family's tier;
      * with LLM nominations for a family (section_nominator), the nominations decide which of that family's
        sections pass and each carries its own tier; BM25 hits that were not nominated are dropped (listed in
        "retrieval_only_not_nominated"), and nominated sections BM25 missed are added;
      * a section linked from another (definition <-> punishment) follows its source section;
      * a section found only by the fact-level safety net goes to the first sub-query citing that
        fact, as CONDITIONAL (its family was not chosen, so applicability is open).
    Applicability is decided in Stage 4.
    """
    r = retriever or get_family_retriever()
    families = list(_obj(query_obj, "offence_families", []) or [])
    sub_queries = list(_obj(query_obj, "sub_queries", []) or [])
    facts = list(_obj(query_obj, "factual_allegations", []) or [])
    matches, _diag = r.retrieve(facts, families)

    nominations = {k.upper(): v for k, v in (nominations or {}).items() if v}
    nom_by_family: Dict[str, Dict[str, Dict[str, Any]]] = {
        code: {n["section"]: n for n in noms} for code, noms in nominations.items()
    }
    dropped: List[str] = []
    if nom_by_family:
        kept = []
        for m in matches:
            fam_vias = [v.partition(":")[2] for v in m.matched_concepts if v.startswith("family:")]
            judged = [c for c in fam_vias if c in nom_by_family]
            if judged and not any(m.section_number in nom_by_family[c] for c in judged):
                dropped.append(m.section_number)
                continue
            kept.append(m)
        matches = kept
        present = {m.section_number for m in matches}
        for code, noms in nom_by_family.items():
            for sec in noms:
                for s, via in [(sec, f"family:{code}")] + [(l, f"linked:{sec}") for l in sorted(r.punishment_links.get(sec, ()))]:
                    if s in present or s not in r.idx_by_sec:
                        continue
                    rec = r.records[r.idx_by_sec[s]]
                    matches.append(CandidateSectionMatch(
                        section_identifier=rec["identifier"], statute=rec["statute"], section_number=s,
                        title=rec["title"], chapter=rec["chapter"], score=0.0, matched_terms=[], matched_concepts=[via],
                    ))
                    present.add(s)

    sq_by_family: Dict[str, Any] = {}
    for fam, sq in zip(families, sub_queries):
        sq_by_family[str(_obj(fam, "family", "")).upper()] = (fam, sq)
    fact_to_sq: Dict[str, Any] = {}
    for fam, sq in zip(families, sub_queries):
        for fid in _obj(fam, "fact_ids", []) or []:
            fact_to_sq.setdefault(str(fid), (fam, sq))

    mappings: Dict[str, Dict[str, Any]] = {}
    for fam, sq in zip(families, sub_queries):
        sid = _obj(sq, "id", "")
        mappings[sid] = {
            "sub_query_id": sid, "sub_query_text": _obj(sq, "query", ""),
            "target_parties": list(_obj(sq, "target_parties", []) or []),
            "facts_extracted": [], "ingredients_matched": [],
            "candidate_chapters": [str(_obj(fam, "family", ""))],
            "primary_candidate_sections": [], "secondary_candidate_sections": [],
            "conditional_candidate_sections": [], "not_triggered_sections": [],
            "candidate_sections": [], "relevance_reasoning": f"Family-constrained retrieval ({_obj(fam, 'family', '')}).",
        }

    placed: Dict[str, Tuple[str, str]] = {}  # section -> (sub_query_id, tier)
    pending = list(matches)
    for _ in range(3):  # linked sections follow their source, which may be placed in an earlier pass
        rest = []
        for m in pending:
            target = None
            for via in m.matched_concepts:
                kind, _, val = via.partition(":")
                if kind == "family" and val in sq_by_family:
                    fam, sq = sq_by_family[val]
                    nom = nom_by_family.get(val, {}).get(m.section_number)
                    if nom:
                        missing = [nom["missing_element"]] if nom.get("missing_element") else []
                        target = (_obj(sq, "id", ""), nom["tier"], missing, nom)
                    elif val in nom_by_family:
                        continue  # this family was judged and did not nominate the section
                    else:
                        target = (_obj(sq, "id", ""), str(_obj(fam, "tier", "PRIMARY")).upper(), list(_obj(fam, "unresolved_elements", []) or []), None)
                    break
                if kind == "linked" and val in placed:
                    sid, tier = placed[val]
                    target = (sid, tier, [], None)
                    break
                if kind == "fact" and val in fact_to_sq:
                    fam, sq = fact_to_sq[val]
                    target = (_obj(sq, "id", ""), "CONDITIONAL", ["Offence family not tagged in Stage 1; applicability to be established"], None)
                    break
            if target is None:
                rest.append(m)
                continue
            sid, tier, unresolved, nom = target
            placed[m.section_number] = (sid, tier)
            key = {"PRIMARY": "primary_candidate_sections", "SECONDARY": "secondary_candidate_sections"}.get(tier, "conditional_candidate_sections")
            if nom:
                why = f"Nominated ({tier}) from the family's full section list: {nom.get('reason', '')}"
                if m.score:
                    why += f" [also BM25-retrieved, score {m.score}]"
            else:
                why = "Retrieved via " + ", ".join(m.matched_concepts) + (f"; matched terms: {', '.join(m.matched_terms)}" if m.matched_terms else "")
            mappings[sid][key].append({
                "section_number": m.section_number, "section_title": m.title, "statute": m.statute,
                "candidate_type": tier, "score": float(m.score),
                "score_breakdown": {"retrieval_score": float(m.score)},
                "ingredients_matched": list(nom.get("fact_ids", [])) if nom else [], "missing_facts": unresolved,
                "relevance_reasoning": why,
            })
            mappings[sid]["candidate_sections"].append(m.section_number)
        pending = rest
        if not pending:
            break
    result = {"schema_version": "1.0", "mappings": list(mappings.values())}
    if nom_by_family:
        result["retrieval_only_not_nominated"] = sorted(set(dropped))
    return result


# ---------------------------------------------------------------------------
# Clause backstop: retrieval granularity must not depend on how finely the LLM split facts
# ---------------------------------------------------------------------------
_CLAUSE_SPLIT = re.compile(r",\s*(?:and\s+)?|;\s*|\s+and\s+(?=[a-z]+(?:ed|ing)\b)", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def clause_backstop(narrative: str, facts: Iterable[Any], min_words: int = 2) -> List[Dict[str, Any]]:
    """
    For every narrative sentence that contains an alleged (charge-bearing) fact quote, splits the sentence
    into clauses and returns clauses not already covered by an existing fact as new facts. Clauses are
    verbatim spans of the narrative, and only allegation sentences are used (sentences the LLM itself
    grounded an act/omission/result in), so defence statements are not turned into allegations.
    """
    facts = list(facts or [])
    quotes = [(f, _norm_ws(_obj(f, "verbatim_quote") or "")) for f in facts
              if str(_obj(f, "conduct_type", "")).upper() in _CHARGE_BEARING and _obj(f, "verbatim_quote")]
    if not narrative or not quotes:
        return []
    existing_tokens = [set(_tokenize(q)) for _, q in quotes]
    existing_ids = {str(_obj(f, "fact_id", "")) for f in facts if _obj(f, "fact_id", "")}
    new: List[Dict[str, Any]] = []
    n = 0
    for sent in _SENTENCE_SPLIT.split(narrative):
        ns = _norm_ws(sent)
        anchors = [f for f, q in quotes if q and q in ns]
        if not anchors:
            continue
        # Only the part of the sentence from the first alleged act onwards (skip preambles such as
        # "The complainant, a relative of the deceased, alleges that ...").
        start = min(ns.find(q) for f, q in quotes if q and q in ns)
        region = re.sub(r"\s+", " ", sent).strip()[start:]
        for clause in _CLAUSE_SPLIT.split(region):
            clause = clause.strip(" .")
            if len(clause.split()) < min_words:
                continue
            ctoks = set(_tokenize(clause))
            if not ctoks:
                continue
            # Covered only if an existing quote is about this clause (inside it, or nearly the same
            # words) - not merely because a broad quote spanning several acts contains it.
            covered = any(
                (q and q in _norm_ws(clause)) or (et and len(ctoks & et) / len(ctoks | et) >= 0.6)
                for (_, q), et in zip(quotes, existing_tokens)
            )
            if covered:
                continue
            n += 1
            cand_id = f"CB{n}"
            while cand_id in existing_ids:
                n += 1
                cand_id = f"CB{n}"
            existing_ids.add(cand_id)
            # The clause keeps the type and actor of the fact whose quote contains it (a split RESULT is a RESULT).
            ncl = _norm_ws(clause)
            parent = next((f for f, q in quotes if f is not None and q and ncl in q), None)
            ctype = str(_obj(parent, "conduct_type", "ACT") or "ACT").upper() if parent is not None else "ACT"
            new.append({
                "fact_id": cand_id, "verbatim_quote": clause, "conduct_type": ctype, "factual_status": "ALLEGED",
                "description": f"Separate {ctype.lower()} split from a compound allegation (clause backstop)",
                "actor": _obj(parent, "actor", None) if parent is not None else None,
                "affected_party_or_object": None,
            })
            existing_tokens.append(ctoks)
            quotes.append((None, _norm_ws(clause)))
    return new
