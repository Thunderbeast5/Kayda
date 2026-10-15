"""
Precedent Statute Matcher for LexiGraphBE Precedent Retrieval Pipeline.

Provides robust statute matching with support for:
- IPC <-> BNS bidirectional equivalents      (StatuteRepository / Neo4j REPLACED_BY)
- CrPC <-> BNSS bidirectional equivalents    (StatuteRepository, bnss json `replaces_CrPC`)
- IEA <-> BSA bidirectional equivalents      (StatuteRepository, BSA->IEA map)
- Special Acts (POCSO, NDPS, SC/ST, PCA, UAPA, PMLA, IT, DPA, JJ, etc.)
- Formatting normalization (406-B, 406B, 406 B -> 406B)
- Parenthetical subsection handling (439(2) -> 439)
- Act name normalization (IPC 1860, Indian Penal Code -> IPC; "Dowry Prohibition Act, 1961" -> DPA)

CHANGES vs. previous version
- No hand-written equivalence dicts. The old CRPC_TO_BNSS / IEA_TO_BSA dicts disagreed with the
  Neo4j-backed maps used by Stage 3b/3c/4 (e.g. IEA 45 -> BSA 43 vs. the real BSA 39; CrPC 437 -> BNSS 479
  vs. the real BNSS 480). Everything is now derived from StatuteRepository.
- extract_statutes_from_stage4() reads the keys Stage 4 ACTUALLY emits
  (bnss_to_crpc_equivalents, bsa_to_iea_equivalents, act_router_output.act_routing/relevant_sections)
  and adds the bail provision implied by the requested relief (anticipatory bail -> CrPC 438 / BNSS 482)
  even when Stage 3c fails to return it.
- Every extracted statute carries `kind` (offence / procedure / evidence / special) and `weight`.
- match_statutes() records which INPUT statute each judgment statute satisfied (matched_via_*),
  so the retriever can weight matches instead of counting them.
- normalize_act_name() no longer leaves a trailing comma ("... ACT, 1961").
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .statute_repository import StatuteRepository
from .offence_taxonomy import gravity_factor, max_years_from_text


# Stage-4 prima facie strength -> weight of that offence in retrieval.
STRENGTH_WEIGHT = {"strong": 1.0, "moderate": 0.7, "weak": 0.3}

# Gravity is derived from the statute's own punishment (StatuteRepository / First Schedule), not from per-section
# constants: see offence_taxonomy.gravity_factor().
PROCEDURE_WEIGHT = 0.8
EVIDENCE_WEIGHT = 0.1
SPECIAL_ACT_WEIGHT = 1.0

# Used ONLY if the BNSS corpus (with `replaces_CrPC`) is not loaded in StatuteRepository.
# Each pair is confirmed by the Stage 3c output (e.g. BNSS 480 = bail in non-bailable offences).
_FALLBACK_CRPC_TO_BNSS = {
    "41": ["35"], "41A": ["35(3)"], "82": ["84"], "83": ["85"],
    "154": ["173"], "156": ["175"], "156(3)": ["175(3)"], "167": ["187"], "170": ["190"], "173": ["193"],
    "437": ["480"], "438": ["482"], "439": ["483"], "482": ["528"],
}

def detect_stage_mode(stage4_result: Optional[Dict], case_context: Optional[Dict] = None) -> str:
    """
    Returns 'anticipatory', 'regular' or 'unknown'.
    Prioritizes structured requested_relief / relief / procedural_stage fields,
    falling back to free-text inspection only when structured fields are absent.
    """
    # 1. Structured requested_relief / relief fields
    for src in (case_context or {}, stage4_result or {}):
        if not isinstance(src, dict):
            continue
        for k in ("requested_relief", "relief"):
            v = src.get(k)
            if isinstance(v, str) and v.strip():
                vl = v.lower()
                if "anticipatory" in vl or "pre-arrest" in vl or "pre arrest" in vl:
                    return "anticipatory"
                if "regular" in vl or "post-arrest" in vl or "post arrest" in vl:
                    return "regular"
                if "bail" in vl:
                    return "regular"

    # 2. Structured procedural_stage or case_profile
    for src in (case_context or {}, stage4_result or {}):
        if not isinstance(src, dict):
            continue
        ps = src.get("procedural_stage")
        if isinstance(ps, str) and ps.strip():
            psl = ps.lower()
            if psl in ("pre_arrest", "anticipatory", "anticipatory_cancel"):
                return "anticipatory"
            if psl in ("post_arrest_bail", "regular", "regular_bail"):
                return "regular"
        cp = src.get("case_profile")
        if isinstance(cp, dict):
            for k in ("requested_relief", "procedural_stage", "relief"):
                v = cp.get(k)
                if isinstance(v, str) and v.strip():
                    vl = v.lower()
                    if "anticipatory" in vl or "pre_arrest" in vl or "pre-arrest" in vl:
                        return "anticipatory"
                    if "regular" in vl or "post_arrest" in vl or "post-arrest" in vl:
                        return "regular"

    # 3. Fallback: free-text search in case facts / summary
    blobs: List[str] = []
    facts = (case_context or {}).get("case_facts") if isinstance(case_context, dict) else None
    if isinstance(facts, str):
        blobs.append(facts[:600].lower())
    text = " ".join(blobs)
    if "anticipatory" in text or "pre-arrest" in text or "apprehend" in text:
        return "anticipatory"
    if "bail" in text:
        return "regular"
    return "unknown"



class PrecedentStatuteMatcher:
    """
    Robust statute matcher for precedent retrieval.
    Handles formatting variations and bidirectional IPC/BNS/CrPC/BNSS/IEA/BSA equivalents.
    """

    def __init__(self):
        repo = StatuteRepository.get_instance()
        self.ipc_to_bns = repo.get_ipc_to_bns_map()
        self.bns_to_ipc = repo.get_bns_to_ipc_map()

        bnss_to_crpc = getattr(repo, "get_bnss_to_crpc_map", lambda: {})() or {}
        bsa_to_iea = getattr(repo, "get_bsa_to_iea_map", lambda: {})() or {}

        self._repo = repo
        self.crpc_to_bnss, self.bnss_to_crpc = self._build_pair_maps(bnss_to_crpc, _FALLBACK_CRPC_TO_BNSS)
        self.iea_to_bsa, self.bsa_to_iea = self._build_pair_maps(bsa_to_iea, {})

    # ------------------------------------------------------------------
    # Equivalence map helpers
    # ------------------------------------------------------------------

    @classmethod
    def _split_sections(cls, value: Any) -> List[str]:
        """'45, 45A' -> ['45', '45A'];  'Section 438' -> ['438']."""
        if not value:
            return []
        out = []
        for tok in re.split(r"[,;/]| and ", str(value)):
            tok = re.sub(r"(?i)^\s*(section|sec\.?|s\.)\s*", "", tok).strip()
            tok = cls.normalize_section_number(tok)
            if tok:
                out.append(tok)
        return out

    @classmethod
    def _build_pair_maps(
        cls, new_to_old: Dict[str, Any], fallback_old_to_new: Dict[str, List[str]]
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
        """Returns (old_to_new, new_to_old), each section -> list of sections."""
        old_to_new: Dict[str, List[str]] = {}
        new_map: Dict[str, List[str]] = {}
        for new, olds in (new_to_old or {}).items():
            new_n = cls.normalize_section_number(str(new))
            for old in cls._split_sections(olds):
                old_to_new.setdefault(old, [])
                if new_n not in old_to_new[old]:
                    old_to_new[old].append(new_n)
                new_map.setdefault(new_n, [])
                if old not in new_map[new_n]:
                    new_map[new_n].append(old)
        if not old_to_new:
            for old, news in fallback_old_to_new.items():
                old_to_new[old] = list(news)
                for n in news:
                    new_map.setdefault(n, []).append(old)
        return old_to_new, new_map

    @staticmethod
    def _lookup(mapping: Dict[str, Any], section: str) -> Any:
        """Exact lookup, then parent-section lookup (439(2) -> 439)."""
        if section in mapping:
            return mapping[section]
        parent = PrecedentStatuteMatcher.get_parent_section(section)
        if parent and parent in mapping:
            return mapping[parent]
        return None

    @staticmethod
    def _scan_prefix(mapping: Dict[str, Any], section: str) -> List[Any]:
        """BNS 318 has no row of its own when the graph stores 318(4); return all 318(...) rows."""
        prefix = section + "("
        return [v for k, v in mapping.items() if k.startswith(prefix)]

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_section_number(section: str) -> str:
        """
        Normalize section number to canonical form while preserving subsections.

            "406-B" -> "406B", "406 B" -> "406B", "120-B" -> "120B"
            "439(2)" -> "439(2)", "439 (2)" -> "439(2)", "498A" -> "498A"
        """
        if not section:
            return ""
        section = str(section).strip()
        section = re.sub(r"\s+\(", "(", section)
        section = re.sub(r"(\d)([-\s]+)([A-Z])\b", r"\1\3", section, flags=re.IGNORECASE)
        return section.upper()

    @staticmethod
    def normalize_act_name(act: str) -> str:
        """
        Normalize act name to canonical short form.

            "IPC 1860" -> "IPC", "Indian Penal Code" -> "IPC", "CrPC 1973" -> "CRPC",
            "The Dowry Prohibition Act, 1961" -> "DPA", "NDPS Act 1985" -> "NDPS"
        """
        if not act:
            return ""
        act_upper = act.strip().upper()
        # trailing year with optional comma/dash: "... ACT, 1961" -> "... ACT"
        act_upper = re.sub(r"[\s,\-]*\d{4}\s*$", "", act_upper)
        act_upper = re.sub(r"^THE\s+", "", act_upper)
        act_upper = re.sub(r"[\s,]+ACT\s*$", "", act_upper)

        act_map = {
            "INDIAN PENAL CODE": "IPC", "I.P.C": "IPC", "I.P.C.": "IPC", "PENAL CODE": "IPC",
            "BHARATIYA NYAYA SANHITA": "BNS", "BHARATIYA NYAYA SAMHITA": "BNS",
            "CODE OF CRIMINAL PROCEDURE": "CRPC", "CRIMINAL PROCEDURE CODE": "CRPC",
            "CR.P.C": "CRPC", "CR.P.C.": "CRPC", "CR P C": "CRPC",
            "BHARATIYA NAGARIK SURAKSHA SANHITA": "BNSS", "BHARATIYA NAGRIK SURAKSHA SANHITA": "BNSS",
            "INDIAN EVIDENCE ACT": "IEA", "I.E.A": "IEA", "I.E.A.": "IEA", "EVIDENCE ACT": "IEA",
            "BHARATIYA SAKSHYA ADHINIYAM": "BSA", "BHARATIYA SAKSHYA": "BSA",
            "PROTECTION OF CHILDREN FROM SEXUAL OFFENCES": "POCSO", "POCSO": "POCSO",
            "NARCOTIC DRUGS AND PSYCHOTROPIC SUBSTANCES": "NDPS", "N.D.P.S": "NDPS", "N.D.P.S.": "NDPS", "NDPS": "NDPS",
            "SCHEDULED CASTES AND SCHEDULED TRIBES (PREVENTION OF ATROCITIES)": "SC/ST",
            "SCHEDULED CASTES AND THE SCHEDULED TRIBES (PREVENTION OF ATROCITIES)": "SC/ST",
            "SC/ST POA": "SC/ST", "PREVENTION OF ATROCITIES": "SC/ST", "POA": "SC/ST",
            "PREVENTION OF CORRUPTION": "PCA", "P.C.A": "PCA", "PCA": "PCA",
            "UNLAWFUL ACTIVITIES (PREVENTION)": "UAPA", "UAPA": "UAPA", "U.A.P.A": "UAPA",
            "PREVENTION OF MONEY LAUNDERING": "PMLA", "PMLA": "PMLA", "P.M.L.A": "PMLA",
            "INFORMATION TECHNOLOGY": "IT", "IT ACT": "IT", "I.T.": "IT",
            "DOWRY PROHIBITION": "DPA",
            "JUVENILE JUSTICE": "JJ", "JJ ACT": "JJ",
            "JUVENILE JUSTICE (CARE AND PROTECTION OF CHILDREN)": "JJ",
        }
        return act_map.get(act_upper, act_upper)

    # ------------------------------------------------------------------
    # Equivalents
    # ------------------------------------------------------------------

    def get_equivalent_sections(self, act: str, section: str) -> List[Tuple[str, str]]:
        """
        All equivalent (act, section) tuples including the original.

            IPC 420   -> [(IPC, 420), (BNS, 318(4))]
            CrPC 438  -> [(CRPC, 438), (BNSS, 482)]
            BSA 39    -> [(BSA, 39), (IEA, 45), (IEA, 45A)]
        """
        act_norm = self.normalize_act_name(act)
        sec = self.normalize_section_number(section)
        eq: List[Tuple[str, str]] = [(act_norm, sec)]

        def add(a: str, secs: List[str]) -> None:
            for s in secs:
                t = (a, self.normalize_section_number(s))
                if t[1] and t not in eq:
                    eq.append(t)

        def bns_of(entry: Dict[str, Any]) -> str:
            return str(entry.get("bns_section_clean") or entry.get("bns_section_raw") or "")

        def ipc_of(entry: Dict[str, Any]) -> str:
            return str(entry.get("ipc_section") or entry.get("ipc_section_clean") or entry.get("ipc_section_raw") or "")

        if act_norm == "IPC":
            entry = self._lookup(self.ipc_to_bns, sec)
            if entry:
                add("BNS", [bns_of(entry)])
        elif act_norm == "BNS":
            entry = self.bns_to_ipc.get(sec)
            entries = [entry] if entry else self._scan_prefix(self.bns_to_ipc, sec)
            if not entries:
                parent_entry = self._lookup(self.bns_to_ipc, sec)
                entries = [parent_entry] if parent_entry else []
            add("IPC", [ipc_of(e) for e in entries])
        elif act_norm == "CRPC":
            add("BNSS", self._lookup(self.crpc_to_bnss, sec) or [])
        elif act_norm == "BNSS":
            add("CRPC", self._lookup(self.bnss_to_crpc, sec) or [])
        elif act_norm == "IEA":
            add("BSA", self._lookup(self.iea_to_bsa, sec) or [])
        elif act_norm == "BSA":
            add("IEA", self._lookup(self.bsa_to_iea, sec) or [])
        # Special acts have no equivalents.
        return eq

    def gravity(self, act: str, section: str) -> float:
        """0.4..1.0 from the offence's maximum punishment; 1.0 when the registry has no entry."""
        try:
            md = self._repo.get_first_schedule_metadata(str(section), self.normalize_act_name(act))
            return gravity_factor(max_years_from_text((md or {}).get("punishment_maximum")))
        except Exception:
            return 1.0

    @staticmethod
    def get_parent_section(section: str) -> Optional[str]:
        """'439(2)' -> '439';  '406' -> None."""
        m = re.match(r"^([A-Z0-9]+)\(", section or "")
        return m.group(1) if m else None

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def match_statutes(
        self,
        input_statutes: List[Dict[str, str]],
        judgment_statutes: List[Dict[str, str]],
        allow_parent_match: bool = True,
    ) -> Tuple[float, List[Dict[str, str]]]:
        """
        Match input case statutes against judgment statutes (logical OR).

        Returns (match_count, matches). Each match dict carries:
            judgment_act, judgment_section,
            matched_via_act, matched_via_section   -> the INPUT statute it satisfied (normalised),
            match_type ("exact" | "parent_match"), how_used, note
        """
        input_statute_set: Set[Tuple[str, str]] = set()
        origin: Dict[Tuple[str, str], Tuple[str, str]] = {}
        parent_origin: Dict[Tuple[str, str], Tuple[str, str]] = {}

        for statute in input_statutes:
            act = statute.get("act", "")
            section = statute.get("section", "")
            key = (self.normalize_act_name(act), self.normalize_section_number(section))
            for eq in self.get_equivalent_sections(act, section):
                input_statute_set.add(eq)
                origin.setdefault(eq, key)
                if allow_parent_match:
                    parent = self.get_parent_section(eq[1])
                    if parent:
                        parent_origin.setdefault((eq[0], parent), key)

        matches: List[Dict[str, str]] = []
        match_count = 0.0

        for js in judgment_statutes:
            j_act = js.get("act", "")
            j_section = js.get("section", "")
            j_eqs = self.get_equivalent_sections(j_act, j_section)

            hit_key: Optional[Tuple[str, str]] = None
            match_type = "exact"

            for eq in j_eqs:
                if eq in input_statute_set:
                    hit_key = origin[eq]
                    break

            if hit_key is None and allow_parent_match:
                for eq in j_eqs:
                    j_parent = self.get_parent_section(eq[1])
                    if j_parent and (eq[0], j_parent) in input_statute_set:
                        hit_key = origin[(eq[0], j_parent)]   # judgment cites 439(2); input has 439
                        match_type = "parent_match"
                        break
                    if eq in parent_origin:
                        hit_key = parent_origin[eq]           # judgment cites 318; input has 318(4)
                        match_type = "parent_match"
                        break

            if hit_key is not None:
                match_count += 1.0 if match_type == "exact" else 0.5
                raw_how = str(js.get("how_used") or "").strip().lower()
                j_sec_norm = self.normalize_section_number(j_section)
                j_act_norm = self.normalize_act_name(j_act)

                # Ensure procedural/process sections are NEVER tagged as substantive offences.
                # Decided strictly by statute/act: if CRPC or BNSS, it is procedure.
                if j_act_norm in ("CRPC", "BNSS") or "crpc" in j_act.lower() or "bnss" in j_act.lower():
                    if raw_how in ("charged", ""):
                        how_used = "procedure"
                    else:
                        how_used = raw_how
                else:
                    how_used = raw_how or "charged"

                # Dual citation derived dynamically from StatuteRepository equivalents
                eqs = [t for t in self.get_equivalent_sections(j_act_norm, j_sec_norm) if t[0] != j_act_norm]
                if eqs:
                    dual_cite = f"{j_act} {j_section} / {eqs[0][0]} {eqs[0][1]}"
                else:
                    dual_cite = f"{j_act} {j_section}"

                matches.append({
                    "judgment_act": j_act,
                    "judgment_section": j_section,
                    "matched_via_act": hit_key[0],
                    "matched_via_section": hit_key[1],
                    "match_type": match_type,
                    "how_used": how_used,
                    "dual_citation": dual_cite,
                    "note": js.get("note", ""),
                })

        return match_count, matches

    # ------------------------------------------------------------------
    # Stage 4 extraction
    # ------------------------------------------------------------------

    def _load_offence_inference_rules(self) -> List[Dict[str, Any]]:
        """Load offence inference rules from external JSON data file."""
        import os, json
        data_path = os.path.join(os.path.dirname(__file__), "data", "offence_inference_rules.json")
        if os.path.exists(data_path):
            try:
                with open(data_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return [
            {
                "rule_id": "valuable_security_forgery_467",
                "target_act": "IPC",
                "target_section": "467",
                "equivalent_section": "338",
                "fact_trigger_all_of": [
                    ["sale deed", "title deed", "valuable security", "conveyance", "will", "ownership document"],
                    ["forg", "fabricat", "fraudulent", "spurious"]
                ],
                "negative_triggers": ["pure money recovery", "commercial contract", "goods supply", "cheque bounce"],
                "kind": "possible_offence",
                "source": "inferred",
                "weight": 0.3,
                "strength": "Possible",
                "status": "Possible Additional Charge (Not in FIR - Inferred from Valuable Security)",
                "note": "Inferred from allegations involving forged/fabricated sale deed or valuable security. Not an FIR charge."
            }
        ]

    def extract_statutes_from_stage4(
        self,
        stage4_result: Dict,
        case_context: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """
        Statute references for retrieval, from everything Stage 4 (and the case context) provides.

        Each item: {act, section, kind, weight, [source, strength, status]}
          kind: offence | procedure | evidence | special | possible_offence
        """
        out: List[Dict[str, Any]] = []
        seen_equivalents: Set[Tuple[str, str]] = set()

        def add(act: str, section: Any, kind: str, weight: float, **extra: Any) -> None:
            section = str(section or "").strip()
            if not section or not act:
                return
            eqs = set(self.get_equivalent_sections(act, section))
            if eqs & seen_equivalents:        # e.g. BNSS 482 and CrPC 438 are the same provision
                return
            seen_equivalents.update(eqs)
            out.append({"act": act, "section": section, "kind": kind, "weight": weight, **extra})

        # 1. Offences (IPC/BNS) -- weighted by Stage 4 prima facie strength
        for off in stage4_result.get("verified_offences", []) or []:
            status = str(off.get("overall_status") or "")
            if status.strip().lower() == "not attracted":
                continue
            sec = str(off.get("section_number") or "")
            strength = str(off.get("overall_prima_facie_strength") or "").strip().lower()
            sec_norm = self.normalize_section_number(sec)
            weight = STRENGTH_WEIGHT.get(strength, 0.7)
            weight = round(weight * self.gravity(off.get("statute") or "IPC", sec_norm), 3)
            add(off.get("statute") or "IPC", sec, "offence", weight,
                strength=off.get("overall_prima_facie_strength"), status=status)

        # Check offence inference rules from external data file (e.g. valuable security / forged deed -> S.467)
        # Note: Inferred offences carry low weight (~0.3) and kind "possible_offence" so they never appear as charged FIR offences.
        facts_blobs = []
        if isinstance(case_context, dict):
            for k in ("case_facts", "factual_summary", "facts", "summary"):
                if case_context.get(k):
                    facts_blobs.append(str(case_context[k]))
        if isinstance(stage4_result, dict):
            for k in ("case_facts", "factual_summary"):
                if stage4_result.get(k):
                    facts_blobs.append(str(stage4_result[k]))
        full_facts = " ".join(facts_blobs).lower()

        inference_rules = self._load_offence_inference_rules()
        for rule in inference_rules:
            triggers_met = True
            for kw_group in rule.get("fact_trigger_all_of", []):
                if not any(w in full_facts for w in kw_group):
                    triggers_met = False
                    break
            if triggers_met:
                neg_triggers = rule.get("negative_triggers", [])
                if any(neg in full_facts for neg in neg_triggers):
                    continue
                target_act = rule.get("target_act", "IPC")
                target_sec = rule.get("target_section", "467")
                eq_sec = rule.get("equivalent_section", "338")
                if not any(s.get("section") in (target_sec, eq_sec) for s in out):
                    add(
                        target_act,
                        target_sec,
                        kind=rule.get("kind", "possible_offence"),
                        weight=float(rule.get("weight", 0.3)),
                        strength=rule.get("strength", "Possible"),
                        status=rule.get("status", "Possible Additional Charge (Not in FIR - Inferred from Valuable Security)"),
                        source=rule.get("source", "inferred"),
                        is_inferred=True,
                        note=rule.get("note", "")
                    )


        # 2. Bail provision implied by the requested relief -- never depends on Stage 3c succeeding
        mode = detect_stage_mode(stage4_result, case_context)
        if mode == "anticipatory":
            add("CrPC", "438", "procedure", PROCEDURE_WEIGHT, source="relief")
        elif mode == "regular":
            add("CrPC", "437", "procedure", PROCEDURE_WEIGHT, source="relief")
            add("CrPC", "439", "procedure", PROCEDURE_WEIGHT, source="relief")

        # 3. BNSS / CrPC sections returned by Stage 3c (real key + legacy key)
        for b in stage4_result.get("bnss_to_crpc_equivalents", []) or []:
            add("BNSS", b.get("bnss_section"), "procedure", PROCEDURE_WEIGHT, source="stage3c")
        legacy_bnss = stage4_result.get("bnss_output") or {}
        if isinstance(legacy_bnss, dict):
            for b in legacy_bnss.get("verified_sections", []) or []:
                add(b.get("statute") or "BNSS", b.get("section_number"), "procedure", PROCEDURE_WEIGHT, source="legacy")

        # 4. BSA / IEA sections (real key + legacy key) -- low weight, these rarely appear in bail judgments
        for b in stage4_result.get("bsa_to_iea_equivalents", []) or []:
            add("BSA", b.get("bsa_section"), "evidence", EVIDENCE_WEIGHT, source="stage3b")
        legacy_bsa = stage4_result.get("bsa_output") or {}
        if isinstance(legacy_bsa, dict):
            for b in legacy_bsa.get("verified_sections", []) or []:
                add(b.get("statute") or "BSA", b.get("section_number"), "evidence", EVIDENCE_WEIGHT, source="legacy")

        # 5. Special Acts: real shape (act_routing + relevant_sections) and legacy routing_decisions
        router = stage4_result.get("act_router_output") or {}
        if isinstance(router, dict):
            doc_to_title = {}
            for r in router.get("act_routing", []) or []:
                doc_to_title[r.get("document")] = r.get("act_title") or r.get("document") or ""
            for s in router.get("relevant_sections", []) or []:
                title = doc_to_title.get(s.get("act_document")) or s.get("act_title") or s.get("act_document") or ""
                add(self.normalize_act_name(title), s.get("section_number"), "special", SPECIAL_ACT_WEIGHT, source="act_router")
            for d in router.get("routing_decisions", []) or []:   # legacy
                act_norm = self.normalize_act_name(d.get("act_name", ""))
                for s in d.get("sections", []) or []:
                    add(act_norm, s.get("section_number") or s.get("section"), "special", SPECIAL_ACT_WEIGHT, source="legacy")

        # 6. Legacy fallback
        if not out:
            for s in stage4_result.get("verified_sections", []) or []:
                add(s.get("statute") or s.get("act") or "IPC", s.get("section_number"), "offence", 0.7, source="legacy")

        return out


def test_statute_matcher():
    """Smoke test (needs a loaded StatuteRepository)."""
    m = PrecedentStatuteMatcher()
    for a, s in [("IPC", "420"), ("BNS", "318"), ("CrPC", "438"), ("BNSS", "482"), ("BSA", "39"), ("IEA", "45A"), ("POCSO", "3")]:
        print(f"{a} {s:6} -> {m.get_equivalent_sections(a, s)}")
    print(m.normalize_act_name("The Dowry Prohibition Act, 1961"), m.normalize_act_name("CrPC 1973"))


if __name__ == "__main__":
    test_statute_matcher()