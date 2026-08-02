import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

try:
    from .services.query_understanding_service import QueryUnderstandingService
    from .services.query_decomposition_service import QueryDecompositionService, NON_OFFENCE_TYPES
    from .services.embedding_service import EmbeddingService
    from .services.pinecone_service import PineconeService
    from .services.case_retrieval_service import CaseRetrievalService
    from .services.merge_service import MergeService
    from .services.verification_service import VerificationService
    from .services.reranking_service import RerankingService
    from .services.legal_reasoning_service import LegalReasoningService
    from .services.community_retrieval_service import CommunityRetrievalService
    from .services.fact_extractor_service import FactExtractorService
    from .services.ingredient_validator_service import IngredientValidatorService
    from .services.evidence_ranking_service import EvidenceRankingService
    from .services.pipeline_debug_service import PipelineDebugService
    from .services.precedent_ranking_service import PrecedentRankingService
except ImportError:
    from services.query_understanding_service import QueryUnderstandingService
    from services.query_decomposition_service import QueryDecompositionService, NON_OFFENCE_TYPES
    from services.embedding_service import EmbeddingService
    from services.pinecone_service import PineconeService
    from services.case_retrieval_service import CaseRetrievalService
    from services.merge_service import MergeService
    from services.verification_service import VerificationService
    from services.reranking_service import RerankingService
    from services.legal_reasoning_service import LegalReasoningService
    from services.community_retrieval_service import CommunityRetrievalService
    from services.fact_extractor_service import FactExtractorService
    from services.ingredient_validator_service import IngredientValidatorService
    from services.evidence_ranking_service import EvidenceRankingService
    from services.pipeline_debug_service import PipelineDebugService
    from services.precedent_ranking_service import PrecedentRankingService

# Section Identifier Regex Compilation (IPC, BNS, CrPC, BNSS, IEA, BSA, POCSO, DPA)
_IPC_ID_RE = re.compile(r"^IPC_\d+[A-Za-z]*$", re.IGNORECASE)
_BNS_ID_RE = re.compile(r"^BNS_\d+[A-Za-z]*$", re.IGNORECASE)
_CRPC_ID_RE = re.compile(r"^CRPC_\d+[A-Za-z]*$", re.IGNORECASE)
_BNSS_ID_RE = re.compile(r"^BNSS_\d+[A-Za-z]*$", re.IGNORECASE)
_IEA_ID_RE = re.compile(r"^IEA_\d+[A-Za-z]*$", re.IGNORECASE)
_BSA_ID_RE = re.compile(r"^BSA_\d+[A-Za-z]*$", re.IGNORECASE)
_POCSO_ID_RE = re.compile(r"^POCSO_\d+[A-Za-z]*$", re.IGNORECASE)
_DPA_ID_RE = re.compile(r"^(DPA|DOWRY)_\d+[A-Za-z]*$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^\d+[A-Za-z]*$")


def _is_legal_section_hit(match_id: str, meta: Dict[str, Any]) -> bool:
    """Check if the vector match corresponds to a statutory provision across acts."""
    patterns = [
        _IPC_ID_RE, _BNS_ID_RE, _CRPC_ID_RE, _BNSS_ID_RE,
        _IEA_ID_RE, _BSA_ID_RE, _POCSO_ID_RE, _DPA_ID_RE
    ]
    if any(p.match(match_id) for p in patterns):
        return True
    sec = str(meta.get("section", ""))
    sec_num = str(meta.get("section_num", ""))
    return bool((sec and _SECTION_RE.match(sec)) or (sec_num and _SECTION_RE.match(sec_num)))


def _normalize_section_params(act: str, section_num: str) -> Tuple[str, str]:
    """Standardizes string formats for sections and statutory acts."""
    act = str(act or "").strip().upper()
    section_num = str(section_num or "").strip()
    clean_sec = section_num.replace("_", " ")
    parts = clean_sec.split()

    known_acts = ("BNS", "IPC", "BNSS", "CRPC", "BSA", "IEA", "POCSO", "DPA", "DOWRY")
    if len(parts) >= 2:
        prefix = parts[0].upper()
        suffix = parts[1]
        if prefix in known_acts:
            act = prefix
            section_num = suffix
        elif prefix.lower() == "section":
            section_num = suffix
    else:
        upper_sec = section_num.upper()
        for k_act in known_acts:
            if upper_sec.startswith(k_act):
                act = k_act
                section_num = upper_sec.replace(k_act, "").replace("_", "").strip()
                break

    if section_num.lower().startswith("section"):
        section_num = section_num[7:].strip()

    for k_act in known_acts:
        if section_num.upper().startswith(k_act):
            section_num = section_num[len(k_act):].replace("_", "").strip()

    section_num = section_num.replace("_", "").strip()
    if act in ("DOWRY", "DPA"):
        act = "DPA"
    return act, section_num


# Below this vector similarity score, a Pinecone hit is treated as noise.
CANDIDATE_SIMILARITY_THRESHOLD = 0.55

ROLE_BIAS_CONFIG: Dict[str, Dict[str, Any]] = {
    "prosecutor": {
        "expansion_angles": [
            "custodial interrogation necessity for recovery of evidence",
            "flight risk and likelihood of tampering with evidence or witnesses",
            "gravity of the offence and non-bailable nature",
        ],
        "favorable_stance_values": {"prosecution", "state", "denied_bail", "anticipatory_bail_rejected"},
        "score_boost": 0.08,
    },
    "defense": {
        "expansion_angles": [
            "anticipatory bail granted personal liberty article 21",
            "cooperation with investigation no flight risk documentary evidence only",
        ],
        "favorable_stance_values": {"accused", "defense", "granted_bail", "anticipatory_bail_allowed"},
        "score_boost": 0.08,
    },
    "neutral": {
        "expansion_angles": [],
        "favorable_stance_values": set(),
        "score_boost": 0.0,
    },
}


def _role_config(role: str) -> Dict[str, Any]:
    return ROLE_BIAS_CONFIG.get((role or "neutral").lower(), ROLE_BIAS_CONFIG["neutral"])


# Preferred act when two entries are equivalent (successor beats predecessor).
# Lower index = higher preference.
_ACT_PREFERENCE = ["BNS", "BNSS", "BSA", "IPC", "CRPC", "IEA", "POCSO", "DPA"]

def _act_rank(act: str) -> int:
    """Lower rank = more preferred (current law beats legacy act)."""
    try:
        return _ACT_PREFERENCE.index(act.upper())
    except ValueError:
        return len(_ACT_PREFERENCE)


def _deduplicate_equivalent_candidates(candidates: List[Dict[str, Any]], verification_service) -> List[Dict[str, Any]]:
    """
    When a BNS section and its IPC predecessor (or BNSS/CrPC, BSA/IEA) are both
    present in the candidate list, keep only the preferred one.

    Strategy:
      - For every candidate, look up its equivalent mapping (REPLACES / REPLACED_BY).
      - Build equivalence groups using union-find.
      - Within each group, keep only the candidate whose act has the highest
        preference rank (i.e. the current statute, not the legacy one).

    Deduplication is ONLY performed across known act crosswalk pairs:
        IPC ↔ BNS,  CrPC ↔ BNSS,  IEA ↔ BSA.
    Two sections from the SAME act (e.g. BNS 351 and BNS 351(2)) are NEVER
    collapsed, even when a subsection suffix appears in the equivalent-mapping
    string — they are distinct nodes with different legal effect.
    """
    # Map section-key → candidate
    key_to_cand: Dict[str, Dict[str, Any]] = {c["section"]: c for c in candidates}

    # Known act-family crosswalk pairs. Dedup is only valid across these pairs.
    _CROSSWALK_PAIRS: set = {
        frozenset({"BNS", "IPC"}),
        frozenset({"BNSS", "CRPC"}),
        frozenset({"BSA", "IEA"}),
    }

    # Union-Find to group equivalent sections
    parent: Dict[str, str] = {k: k for k in key_to_cand}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # subsection-stripping regex — used ONLY as a last-resort fallback (see below)
    _subsection_re = re.compile(r"\(\w+\)\s*$")

    for key, cand in key_to_cand.items():
        eq = cand.get("equivalent_mapping")
        if not (eq and isinstance(eq, dict)):
            continue

        eq_act = eq.get("act", "")
        eq_sec = eq.get("section", "")
        if not eq_act or not eq_sec:
            continue

        # Guard: only union across known act crosswalk pairs.
        # Same-act entries (e.g. BNS 351 and BNS 351(2)) must never be merged.
        source_act = cand["act"]
        if frozenset({source_act, eq_act}) not in _CROSSWALK_PAIRS:
            continue

        # --- Strategy: exact match first, subsection-stripped fallback second ---
        #
        # "Exact match first" handles the normal case: IPC 498A's mapping says
        # BNS 85, and "BNS 85" is exactly a key in key_to_cand → union them.
        #
        # "Subsection-stripped fallback" handles the edge case where the graph
        # stores the mapping at subsection granularity but retrieval keyed the
        # candidate at the base section level.  For example, if IPC 506's
        # mapping is stored as "BNS 351(2)" but the Pinecone hit was indexed as
        # "BNS 351", the exact key "BNS 351(2)" won't be in key_to_cand, so we
        # strip to "BNS 351" and try again.
        #
        # Crucially, this fallback is safe ONLY because of the crosswalk-pair
        # guard above: we already know eq_act ≠ source_act (different act
        # families), so "BNS 351" cannot be confused with "BNS 351(2)" when
        # source_act is IPC and eq_act is BNS — that collision would require
        # source_act == eq_act == "BNS", which the guard rejects.
        eq_key_exact = f"{eq_act} {eq_sec}".strip()
        if eq_key_exact in key_to_cand:
            union(key, eq_key_exact)
        else:
            eq_sec_base = _subsection_re.sub("", eq_sec).strip()
            eq_key_base = f"{eq_act} {eq_sec_base}".strip()
            if eq_key_base in key_to_cand:
                union(key, eq_key_base)

    # Group candidates by root
    groups: Dict[str, List[str]] = {}
    for key in key_to_cand:
        root = find(key)
        groups.setdefault(root, []).append(key)

    kept: List[Dict[str, Any]] = []
    for group_keys in groups.values():
        if len(group_keys) == 1:
            kept.append(key_to_cand[group_keys[0]])
        else:
            # Pick the candidate whose act is most preferred
            best_key = min(group_keys, key=lambda k: _act_rank(key_to_cand[k]["act"]))
            kept.append(key_to_cand[best_key])
            dropped = [k for k in group_keys if k != best_key]
            print(f"[LexiGraphAgent] Dedup: keeping {best_key}, dropping equivalent(s): {dropped}")

    # Preserve original ordering (by position of first occurrence)
    original_order = {c["section"]: i for i, c in enumerate(candidates)}
    kept.sort(key=lambda c: original_order.get(c["section"], 999))
    return kept


class LexiGraphAgent:
    """
    LexiGraphAgent - Comprehensive Retrieval Engine for Anticipatory Bail
    Handles IPC/BNS, CrPC/BNSS, IEA/BSA, POCSO, and Dowry Prohibition Act provisions.
    """

    def __init__(self):
        self.query_understanding_service = QueryUnderstandingService()
        self.query_decomposition_service = QueryDecompositionService()
        self.embedding_service = EmbeddingService()
        self.pinecone_service = PineconeService()
        self.case_retrieval_service = CaseRetrievalService()
        self.merge_service = MergeService()
        self.verification_service = VerificationService()
        self.community_retrieval_service = CommunityRetrievalService()
        self.reranking_service = RerankingService()
        self.legal_reasoning_service = LegalReasoningService()
        self.fact_extractor_service = FactExtractorService()
        self.ingredient_validator_service = IngredientValidatorService(self.verification_service.neo4j_service)
        self.evidence_ranking_service = EvidenceRankingService()
        self.pipeline_debug_service = PipelineDebugService()
        self.precedent_ranking_service = PrecedentRankingService()

    def process_query(self, query: str, debug: bool = False, role: str = "prosecutor") -> Dict[str, Any]:
        if debug:
            self.pipeline_debug_service.enable()
            self.pipeline_debug_service.reset()

        role_cfg = _role_config(role)

        # Cache the set of relationship types that actually exist in this Neo4j
        # database, fetched once per query run.  Used downstream to build
        # Cypher patterns that only reference existing rel-types — avoids the
        # Neo4j GQL notification spam that fires when a query references an
        # unknown relationship type (e.g. PREDICATE_OF, CONDITIONED_ON).
        _existing_rel_types: set = set()
        try:
            _rel_rows = self.verification_service.neo4j_service.run_query(
                "CALL db.relationshipTypes()", {}
            )
            for _r in _rel_rows:
                _existing_rel_types.add(_r.get("relationshipType", ""))
        except Exception:
            pass  # proceed with empty set; callers fall back to act-level map

        # STEP 1: Fact Extraction, Query Understanding & Typed Decomposition
        print(f"\n[LexiGraphAgent] Step 1: Fact Extraction & Query Understanding...")
        extracted_facts = self.fact_extractor_service.extract_facts(query)
        qu_result = self.query_understanding_service.analyze_query(query)

        # QueryDecompositionService replaces QueryExpansionService.
        # It produces typed sub-queries; the type drives the retrieval path below.
        decomp_result = self.query_decomposition_service.decompose(qu_result, query, role)
        sub_queries = decomp_result.get("sub_queries") or []

        # Separate sub-queries by type so retrieval is routed correctly.
        # PROCEDURAL sub-queries never hit Pinecone — they are auto-resolved in Step 3.
        # All other types go to Pinecone, but carry their type so Step 4 knows
        # whether to run ingredient validation on their results.
        pinecone_sub_queries = [sq for sq in sub_queries if sq["type"] != "PROCEDURAL"]

        # For case retrieval (precedents), use OFFENCE + AGGRAVATION queries only
        # since those are the ones that relate to actual facts, not procedural law.
        case_retrieval_queries = [sq for sq in sub_queries if sq["type"] in ("OFFENCE", "AGGRAVATION", "MITIGATION")]

        # Build the flat search_queries list the embedding service expects,
        # but tag each entry so we can propagate the type to merged candidates.
        # Format: {"search_queries": [...]} for embedding service compatibility.
        pinecone_query_strings = [sq["query"] for sq in pinecone_sub_queries]

        self.pipeline_debug_service.log_query(
            original_query=query,
            expanded_queries=pinecone_query_strings,
            intent=qu_result.get("primary_intent_community", ""),
            keywords=qu_result.get("keywords", [])
        )

        # STEP 2: Type-Aware Vector Search
        print("[LexiGraphAgent] Step 2: Type-Aware Vector Search (Pinecone Legal Sections + Precedents)...")

        # Embed only the non-procedural sub-queries
        emb_input = {"search_queries": pinecone_query_strings}
        emb_result = self.embedding_service.generate_embeddings(emb_input)

        # Annotate each embedding with its sub-query type so results carry type metadata
        sq_type_by_query = {sq["query"]: sq["type"] for sq in pinecone_sub_queries}
        for emb_item in (emb_result.get("embeddings") or []):
            emb_item["sub_query_type"] = sq_type_by_query.get(emb_item.get("query", ""), "OFFENCE")

        # For case retrieval use the OFFENCE/AGGRAVATION-only embedding subset
        case_query_strings = [sq["query"] for sq in case_retrieval_queries]
        case_emb_input = {"search_queries": case_query_strings}
        case_emb_result = self.embedding_service.generate_embeddings(case_emb_input)

        retrieval_res = self.pinecone_service.query_index(emb_result, top_k=15, namespace="legal_sections")
        top_similar_cases = self.case_retrieval_service.retrieve_cases(case_emb_result, top_k=10)

        top_similar_cases = self.precedent_ranking_service.rank_cases(
            cases=top_similar_cases,
            query=query,
            offence_sections=[],
            debug=debug
        )

        merge_res = self.merge_service.merge_results(retrieval_res)
        merged_candidates = merge_res.get("merged_candidates") or []

        self.pipeline_debug_service.log_stage(
            "Step 2: Vector Search",
            input_count=len(pinecone_query_strings),
            output_count=len(merged_candidates),
            metadata={"similar_cases_retrieved": len(top_similar_cases)}
        )

        # Build raw candidates, carrying the sub_query_type from whichever
        # sub-query contributed the highest-scoring hit for this candidate.
        # The type is used in Step 4 to decide whether ingredient validation runs.
        raw_candidates = []
        for mc in merged_candidates:
            norm_act, norm_sec_num = _normalize_section_params(mc["act"], mc["section_num"])
            # Determine the dominant type: if any OFFENCE sub-query hit this candidate,
            # mark it OFFENCE (strictest validation). Otherwise use the actual type.
            source_types = set()
            for src in (mc.get("sources") or []):
                t = sq_type_by_query.get(src, None)
                if t:
                    source_types.add(t)

            # Prior logic forced OFFENCE onto a candidate whenever ANY OFFENCE
            # sub-query hit it at all — even a low-similarity, incidental hit.
            # That's how an Evidence Act section (e.g. BSA 118) retrieved
            # mainly by the narrow EVIDENCE_PRESUMPTION query, but also
            # picked up loosely by a broad OFFENCE query, got forced into
            # full ingredient validation and rejected as a false negative.
            # A narrow, purpose-built sub-query type hitting a candidate is a
            # more trustworthy signal than incidental overlap from a broad
            # OFFENCE concept search, so a non-OFFENCE type present alongside
            # OFFENCE now wins instead of being overridden.
            non_offence_hits = source_types - {"OFFENCE"}
            if not source_types:
                dominant_type = "OFFENCE"
            elif non_offence_hits:
                dominant_type = "AGGRAVATION" if "AGGRAVATION" in non_offence_hits else next(iter(non_offence_hits))
            else:
                dominant_type = "OFFENCE"

            # Intrinsic act-family override: some acts can never contain an
            # offence-creating provision regardless of which sub-query
            # surfaced them, so this is authoritative over the retrieval-based
            # guess above. BSA/IEA are Evidence Acts (no substantive offences
            # live there); BNSS/CRPC are Procedure Acts. This is a structural
            # legal fact about the act itself, not a keyword/section hardcode.
            if norm_act in ("BSA", "IEA"):
                dominant_type = "EVIDENCE_PRESUMPTION"
            elif norm_act in ("BNSS", "CRPC"):
                dominant_type = "PROCEDURAL"
            # Substantive criminal act sections (IPC/BNS/DPA) must always go
            # through ingredient validation — they cannot be auto-accepted on
            # vector similarity alone, regardless of which sub-query surfaced
            # them. This prevents a misclassified sub_query_type from bypassing
            # the hard rejection that catches sections like IPC 304B (Dowry
            # Death) when no death is present in the facts.
            elif norm_act in ("IPC", "BNS", "DPA", "DOWRY", "POCSO"):
                if dominant_type not in ("OFFENCE", "PUNISHMENT_QUANTUM"):
                    dominant_type = "OFFENCE"

            raw_candidates.append({
                "section": f"{norm_act} {norm_sec_num}",
                "act": norm_act,
                "section_num": norm_sec_num,
                "title": mc["metadata"].get("title") or "",
                "punishment": mc["metadata"].get("punishment") or "",
                "vector_similarity": mc["best_similarity"],
                "sub_query_type": dominant_type,
                "metadata": mc["metadata"],
                "sources": mc["sources"]
            })

        # --- RAW CANDIDATE ACT-FAMILY NORMALISATION ---
        # Pinecone stores both old-law (IPC/CrPC/IEA) and new-law (BNS/BNSS/BSA)
        # embeddings in the same index. Whichever version scores highest for a
        # given query becomes the raw candidate — this is non-deterministic across
        # queries, causing inconsistent graph lookups (sometimes requesting BNS
        # first, sometimes IPC first, with the other appearing as a crosswalk
        # printout).
        #
        # We normalise here: if a raw candidate comes back from the legacy act,
        # look up its current-act equivalent from the graph and swap it in before
        # any node lookups or deduplication happen.  This means Step 3 always
        # works from the current statute, producing one consistent crosswalk lookup
        # per section instead of one from each direction.
        #
        # Normalisation is driven ENTIRELY by the graph (REPLACES/REPLACED_BY
        # edges), not by any hardcoded section lists, so it works for every
        # section in every act family automatically.
        #
        # Acts that have no counterpart (POCSO, DPA) are left untouched — the
        # fixed verification_service.get_equivalent_ipc_section now returns None
        # for unknown acts rather than guessing "IPC".
        _LEGACY_ACTS = {"IPC", "CRPC", "IEA"}

        normalised_raw: List[Dict[str, Any]] = []
        for c in raw_candidates:
            if c["act"] not in _LEGACY_ACTS:
                normalised_raw.append(c)
                continue
            # Ask the graph for the current-act equivalent
            eq = self.verification_service.get_equivalent_ipc_section(c["act"], c["section_num"])
            if eq and eq.get("act") and eq.get("section"):
                promoted = dict(c)
                promoted["act"] = eq["act"]
                promoted["section_num"] = eq["section"]
                promoted["section"] = f"{eq['act']} {eq['section']}"
                promoted["_promoted_from"] = f"{c['act']} {c['section_num']}"
                normalised_raw.append(promoted)
            else:
                # No graph mapping found — keep original and let Step 3 handle it
                normalised_raw.append(c)
        raw_candidates = normalised_raw

        # STEP 3: Verification & Cross-Mapping
        print("[LexiGraphAgent] Step 3: Graph Verification & Code Cross-Mapping...")
        consolidated_candidates: Dict[str, Dict[str, Any]] = {}

        # Always include anticipatory bail provisions — typed as PROCEDURAL so
        # Step 4 auto-accepts them without ingredient validation.
        for p_act, p_sec in (("BNSS", "482"), ("CRPC", "438")):
            node_info = self.verification_service.get_node_info(p_act, p_sec)
            if node_info:
                key = f"{p_act} {p_sec}"
                consolidated_candidates[key] = {
                    "section": key,
                    "title": node_info.get("title", f"{p_act} Section {p_sec}"),
                    "description": node_info.get("description", ""),
                    "punishment": "",
                    "act": p_act,
                    "section_num": p_sec,
                    "vector_similarity": 0.70,
                    "sub_query_type": "PROCEDURAL",
                    "graph_verified": True,
                    "metadata": node_info,
                    "sources": ["Anticipatory bail provision - the specific relief sought"]
                }

        FALLBACK_MIN_CANDIDATES = 5
        candidates_above_threshold = [c for c in raw_candidates if c["vector_similarity"] >= CANDIDATE_SIMILARITY_THRESHOLD]
        if candidates_above_threshold:
            filtered_candidates = candidates_above_threshold
        else:
            sorted_by_similarity = sorted(raw_candidates, key=lambda c: c["vector_similarity"], reverse=True)
            filtered_candidates = sorted_by_similarity[:FALLBACK_MIN_CANDIDATES]
            if raw_candidates:
                print(f"[LexiGraphAgent] WARNING: no candidates cleared threshold; falling back to top {len(filtered_candidates)}.")

        # Known punishment-only section patterns: sections whose title or category
        # signal they are purely a quantum-of-punishment provision, not a definitional
        # offence section. These should never enter ingredient validation independently.
        # They are surfaced as paired metadata on their parent definition section.
        _PUNISHMENT_TITLE_SIGNALS = re.compile(
            r"\bpunishment\s+for\b|\bpenalty\s+for\b|\bsentence\s+for\b",
            re.IGNORECASE
        )

        for c in filtered_candidates:
            act, sec_num = c["act"], c["section_num"]
            node_info = self.verification_service.get_node_info(act, sec_num)
            if not node_info:
                continue

            eq_result = self.verification_service.get_equivalent_ipc_section(act, sec_num)
            cand_key = f"{act} {sec_num}"

            # Detect punishment-quantum sections.
            # A section is a punishment-quantum provision (not a standalone
            # definable offence) if:
            #   (a) its title starts with "Punishment for ..." — the canonical
            #       IPC drafting pattern for quantum sections (IPC 506, 304B
            #       heading etc.), OR
            #   (b) it is a subsection node (section identifier contains a
            #       parenthetical suffix like "351(2)") whose parent section
            #       is already in the candidate list as a definition section.
            # These sections are re-tagged PUNISHMENT_QUANTUM so Step 4
            # accepts them without ingredient validation, and the render step
            # surfaces them as punishment metadata on their parent offence.
            title_str = node_info.get("title") or c.get("title") or ""
            is_subsection = bool(re.search(r"\(\w+\)\s*$", sec_num))
            is_punishment_title = bool(_PUNISHMENT_TITLE_SIGNALS.search(title_str))
            is_punishment_section = is_punishment_title or is_subsection

            dominant_type = c.get("sub_query_type", "OFFENCE")
            if is_punishment_section:
                dominant_type = "PUNISHMENT_QUANTUM"

            consolidated_candidates[cand_key] = {
                "section": cand_key,
                "title": node_info.get("title", c["title"]),
                "description": node_info.get("description", ""),
                "punishment": node_info.get("punishment", ""),
                "act": act,
                "section_num": sec_num,
                "vector_similarity": c["vector_similarity"],
                "sub_query_type": dominant_type,
                "graph_verified": True,
                "equivalent_mapping": eq_result,
                "metadata": node_info,
                "sources": c["sources"]
            }

        verified_candidates_list = list(consolidated_candidates.values())

        # Deduplicate: if a BNS section and its IPC predecessor are both present,
        # keep only the preferred one (current statute beats legacy act).
        verified_candidates_list = _deduplicate_equivalent_candidates(
            verified_candidates_list, self.verification_service
        )

        print(f"[LexiGraphAgent] Step 3 candidates entering validation: {[c['section'] for c in verified_candidates_list]}")

        # STEP 4: Type-Aware Ingredient Validation + Graph Enrichment
        #
        # Routing rules:
        #   OFFENCE candidates         → full ingredient validation; no-ingredient fallback
        #                                is treated as REJECTION (not a free pass).
        #   PROCEDURAL candidates      → auto-accepted; skip validation entirely.
        #   EVIDENCE_PRESUMPTION,
        #   CONSTITUTIONAL,
        #   AGGRAVATION candidates     → accepted on vector similarity alone (no offence
        #                                ingredients to satisfy); skip validation.
        print("[LexiGraphAgent] Step 4: Type-Aware Ingredient Validation & Graph Enrichment...")
        unranked = []
        rejected = []

        for cand in verified_candidates_list:
            cand_type = cand.get("sub_query_type", "OFFENCE")
            sec_label = cand.get("section", "?")

            # --- PROCEDURAL: relevance-gated accept ---
            #
            # Two classes of PROCEDURAL sections reach this point:
            #
            #   (a) Auto-injected bail provisions (BNSS 482 / CRPC 438) — these
            #       are unconditionally relevant to every anticipatory bail matter
            #       and were explicitly injected in Step 3.  They always pass.
            #
            #   (b) Pinecone-retrieved BNSS/CRPC sections — the act-family override
            #       in Step 2 force-types every BNSS/CRPC hit as PROCEDURAL, but
            #       many of these sections (summons, execution of warrants, trial
            #       procedure, etc.) have nothing to do with bail.  A high vector
            #       similarity to "anticipatory bail application" is not sufficient
            #       evidence that a section like BNSS 502 (or any other procedural
            #       section) is actually cited in bail proceedings.
            #
            # Gate: for retrieved sections, ask the graph whether the section has
            # any relationship to bail-related nodes (BailProvision, BailCondition,
            # or is linked to BNSS 482 / CRPC 438 via RELATED_TO / APPLIES_WITH /
            # MENTIONED_WITH / PRECONDITION_FOR).  If the graph has no bail edges
            # for this section, reject it.  If the graph schema has none of those
            # rel-types yet, fall back to a vector-similarity floor: only accept
            # retrieved procedural sections whose similarity is high enough to
            # suggest they are genuinely about bail (≥ 0.72).
            if cand_type == "PROCEDURAL":
                _auto_injected_bail = {"BNSS 482", "CRPC 438"}
                _is_auto_injected = cand.get("section") in _auto_injected_bail

                if _is_auto_injected:
                    # Always valid — this is the specific relief the applicant seeks
                    cand["is_valid"] = True
                    cand["validation_reason"] = "Anticipatory bail provision — auto-injected; unconditionally relevant."
                    cand["ingredient_confidence"] = cand.get("vector_similarity", 0.70)
                    unranked.append(cand)
                    self.pipeline_debug_service.log_section_decision(
                        section=cand["section_num"], act=cand["act"], title=cand.get("title", ""),
                        decision="included", stage="Step 4: Procedural (auto-injected bail provision)",
                        reason=cand["validation_reason"],
                        scores={"vector_similarity": cand.get("vector_similarity", 0.0), "ingredient_confidence": cand["ingredient_confidence"]}
                    )
                    continue

                # Retrieved procedural section — check bail-domain relevance via graph.
                _bail_rel_candidates = [
                    "RELATED_TO", "APPLIES_WITH", "MENTIONED_WITH", "PRECONDITION_FOR",
                    "BAIL_CONDITION", "APPLIES_TO"
                ]
                _available_bail_rels = [
                    r for r in _bail_rel_candidates if r in _existing_rel_types
                ]

                bail_relevant = False
                bail_relevance_source = ""

                if _available_bail_rels:
                    try:
                        _bail_rel_pattern = "|".join(f"`{r}`" for r in _available_bail_rels)
                        bail_rows = self.verification_service.neo4j_service.run_query(
                            f"""
                            MATCH (n:LawSection {{act: $act, section: $section}})
                                  -[:{_bail_rel_pattern}]-(bail:LawSection)
                            WHERE (bail.act = 'BNSS' AND bail.section = '482')
                               OR (bail.act = 'CRPC' AND bail.section = '438')
                               OR bail:BailProvision
                            RETURN bail.act AS act, bail.section AS section
                            LIMIT 1
                            """,
                            {"act": cand["act"], "section": cand["section_num"]}
                        )
                        if bail_rows:
                            bail_relevant = True
                            bail_relevance_source = "graph-linked to bail provision"
                    except Exception:
                        pass

                if not bail_relevant:
                    # Graph check inconclusive (no rels or no result) — fall back
                    # to a similarity floor.  The threshold (0.72) is deliberately
                    # higher than the general retrieval threshold (0.55) because
                    # procedural sections routinely score well on bail-adjacent
                    # vocabulary without being genuinely applicable.
                    _PROCEDURAL_SIMILARITY_FLOOR = 0.72
                    if cand.get("vector_similarity", 0.0) >= _PROCEDURAL_SIMILARITY_FLOOR:
                        bail_relevant = True
                        bail_relevance_source = f"high vector similarity ({cand['vector_similarity']:.3f} ≥ {_PROCEDURAL_SIMILARITY_FLOOR})"

                if bail_relevant:
                    cand["is_valid"] = True
                    cand["validation_reason"] = f"Procedural provision accepted — {bail_relevance_source}."
                    cand["ingredient_confidence"] = cand.get("vector_similarity", 0.65)
                    unranked.append(cand)
                    self.pipeline_debug_service.log_section_decision(
                        section=cand["section_num"], act=cand["act"], title=cand.get("title", ""),
                        decision="included", stage="Step 4: Procedural (bail-relevance gate passed)",
                        reason=cand["validation_reason"],
                        scores={"vector_similarity": cand.get("vector_similarity", 0.0), "ingredient_confidence": cand["ingredient_confidence"]}
                    )
                else:
                    _proc_reason = (
                        f"PROCEDURAL section {sec_label} is not graph-linked to a bail provision "
                        f"and its vector similarity ({cand.get('vector_similarity', 0.0):.3f}) is "
                        f"below the procedural floor — rejected as not directly relevant to bail proceedings."
                    )
                    cand["is_valid"] = False
                    cand["validation_reason"] = _proc_reason
                    rejected.append({"section": cand["section"], "reason": _proc_reason})
                    self.pipeline_debug_service.log_section_decision(
                        section=cand["section_num"], act=cand["act"], title=cand.get("title", ""),
                        decision="rejected", stage="Step 4: Procedural (bail-relevance gate failed)",
                        reason=_proc_reason,
                        scores={"vector_similarity": cand.get("vector_similarity", 0.0), "ingredient_confidence": 0.0}
                    )
                    print(f"[LexiGraphAgent] REJECT (procedural, not bail-relevant): {sec_label}")
                continue

            # --- PUNISHMENT_QUANTUM: accepted without ingredient validation.
            #     These are punishment-quantum provisions (e.g. IPC 506 / BNS 351(2))
            #     that prescribe the sentence for an offence defined in a sibling
            #     or parent section. They have no independent actus reus or mens rea
            #     ingredients. Once the definition section (IPC 503 / BNS 351) is
            #     validated, the punishment section is automatically co-applicable. ---
            if cand_type == "PUNISHMENT_QUANTUM":
                cand["is_valid"] = True
                cand["validation_reason"] = (
                    "Punishment-quantum provision — co-applicable once the definition "
                    "section is validated; no independent ingredient validation required."
                )
                cand["ingredient_confidence"] = cand.get("vector_similarity", 0.65)
                unranked.append(cand)
                self.pipeline_debug_service.log_section_decision(
                    section=cand["section_num"], act=cand["act"], title=cand.get("title", ""),
                    decision="included", stage="Step 4: Punishment-quantum (auto-accept)",
                    reason=cand["validation_reason"],
                    scores={"vector_similarity": cand.get("vector_similarity", 0.0), "ingredient_confidence": cand["ingredient_confidence"]}
                )
                continue

            # --- NON-OFFENCE (EVIDENCE_PRESUMPTION / CONSTITUTIONAL / AGGRAVATION):
            #     accepted on vector similarity, no ingredient validation ---
            #
            # EXCEPTION — predicate-conditioned presumption sections:
            # Certain evidence-presumption sections are legally conditional: they
            # can only operate if a specific predicate offence has also been
            # established on the facts.  They must NOT be accepted merely because
            # their vector similarity is high — the predicate section must itself
            # have passed ingredient validation.
            #
            # This is driven by the graph, not by a hardcoded section list.
            # We query the graph for any PREDICATE_OF / CONDITIONED_ON /
            # REQUIRES_SECTION relationships on the candidate node.  If any
            # predicate sections are found, at least one must be present in the
            # already-accepted unranked set.  If the graph has no such edges,
            # the section is unconditionally accepted (existing behaviour).
            #
            # Fallback: for acts / sections where graph edges may be missing,
            # we additionally maintain a small map of well-known act-level
            # predicate rules (e.g. dowry-death presumption sections require a
            # dowry-death offence section).  This map is keyed on the ACT of
            # the predicate section, not specific section numbers, so it remains
            # valid as the statute set grows.
            if cand_type in NON_OFFENCE_TYPES:
                # Build the set of predicate section keys already validated
                validated_keys: set = {
                    f"{u['act']} {u['section_num']}" for u in unranked
                }

                # Step A: query graph for explicit predicate relationships.
                # Only build the Cypher pattern for rel-types that actually exist
                # in the database (checked once per query run in _existing_rel_types).
                # Querying a non-existent rel-type generates a Neo4j GQL notification
                # warning on every call even though the query succeeds — this silences
                # that spam without hiding real errors.
                predicate_keys_from_graph: List[str] = []
                _predicate_rel_candidates = [
                    "PREDICATE_OF", "CONDITIONED_ON", "REQUIRES_SECTION"
                ]
                _available_pred_rels = [
                    r for r in _predicate_rel_candidates if r in _existing_rel_types
                ]
                if _available_pred_rels:
                    try:
                        _pred_pattern = "|".join(f"`{r}`" for r in _available_pred_rels)
                        pred_rows = self.verification_service.neo4j_service.run_query(
                            f"""
                            MATCH (n:LawSection {{act: $act, section: $section}})
                                  -[:{_pred_pattern}]->(p:LawSection)
                            RETURN p.act AS act, p.section AS section
                            LIMIT 20
                            """,
                            {"act": cand["act"], "section": cand["section_num"]}
                        )
                        predicate_keys_from_graph = [
                            f"{r['act']} {r['section']}" for r in pred_rows
                            if r.get("act") and r.get("section")
                        ]
                    except Exception:
                        predicate_keys_from_graph = []
                # If no predicate rel-types exist in the graph at all, skip the
                # query entirely — the act-level fallback map handles it below.

                # Step B: act-family fallback — keyed on the ACT of the offence
                # that must be validated, not specific section numbers.
                # Covers cases where graph edges are not yet populated.
                # Format: {(evidence_act, evidence_section): {offence_act, ...}}
                # The presence of ANY validated section from the listed offence
                # acts is sufficient — this stays correct as new sections are added.
                _ACT_LEVEL_PREDICATE_MAP: Dict[tuple, set] = {
                    # Dowry-death presumption sections require a dowry-death offence
                    ("BSA", "118"): {"BNS", "IPC"},   # BNS 80 / IPC 304B
                    ("IEA", "113B"): {"BNS", "IPC"},
                    # Abetment-of-suicide presumption (BSA/IEA) requires suicide offence
                    ("BSA", "119"): {"BNS", "IPC"},
                    ("IEA", "113A"): {"BNS", "IPC"},
                }

                cand_pair = (cand["act"], cand["section_num"])
                required_offence_acts = _ACT_LEVEL_PREDICATE_MAP.get(cand_pair)

                predicate_satisfied: bool
                predicate_rejection_reason: str = ""

                if predicate_keys_from_graph:
                    # Graph has explicit edges — require at least one to be validated
                    predicate_satisfied = any(pk in validated_keys for pk in predicate_keys_from_graph)
                    if not predicate_satisfied:
                        predicate_rejection_reason = (
                            f"{sec_label} is conditioned on at least one of "
                            f"{predicate_keys_from_graph} being established — "
                            f"none passed validation against the case facts."
                        )
                elif required_offence_acts:
                    # No graph edges but act-level fallback applies.
                    # Check whether any validated section belongs to a required offence act.
                    predicate_satisfied = any(
                        u["act"] in required_offence_acts
                        # additionally check that the validated section is an OFFENCE,
                        # not a procedural or evidence section from the same act family
                        and u.get("sub_query_type") in ("OFFENCE", "PUNISHMENT_QUANTUM")
                        for u in unranked
                    )
                    if not predicate_satisfied:
                        predicate_rejection_reason = (
                            f"{sec_label} is a presumption section whose predicate offence "
                            f"(act family: {sorted(required_offence_acts)}) was not validated "
                            f"against the case facts — section rejected to prevent inapplicable inference."
                        )
                else:
                    # No graph edges and no fallback rule → unconditionally accept
                    # (standard non-offence behaviour)
                    predicate_satisfied = True

                if not predicate_satisfied:
                    cand["is_valid"] = False
                    cand["validation_reason"] = predicate_rejection_reason
                    rejected.append({"section": cand["section"], "reason": predicate_rejection_reason})
                    self.pipeline_debug_service.log_section_decision(
                        section=cand["section_num"], act=cand["act"], title=cand.get("title", ""),
                        decision="rejected", stage=f"Step 4: {cand_type} (predicate not satisfied)",
                        reason=predicate_rejection_reason,
                        scores={"vector_similarity": cand.get("vector_similarity", 0.0), "ingredient_confidence": 0.0}
                    )
                    print(f"[LexiGraphAgent] REJECT (predicate not met): {sec_label}")
                    continue

                cand["is_valid"] = True
                cand["validation_reason"] = f"{cand_type} section — accepted on vector similarity; ingredient validation not applicable."
                cand["ingredient_confidence"] = cand.get("vector_similarity", 0.60)
                unranked.append(cand)
                self.pipeline_debug_service.log_section_decision(
                    section=cand["section_num"], act=cand["act"], title=cand.get("title", ""),
                    decision="included", stage=f"Step 4: {cand_type} (similarity-only)",
                    reason=cand["validation_reason"],
                    scores={"vector_similarity": cand.get("vector_similarity", 0.0), "ingredient_confidence": cand["ingredient_confidence"]}
                )
                continue

            # --- OFFENCE: full ingredient validation ---
            # Critical change: if ingredient_validator has no data for this section
            # (fallback path), we REJECT rather than grant a free pass. A section
            # with no ingredients in the graph has not been verified as applicable.
            is_valid, val_reason, val_confidence = self._validate_legal_applicability(cand, extracted_facts, "anticipatory_bail")
            cand["is_valid"] = is_valid
            cand["validation_reason"] = val_reason
            if val_confidence is not None:
                cand["ingredient_confidence"] = float(val_confidence)

            # Detect the no-ingredient fallback case and override to rejection
            if is_valid and "no ingredient data" in (val_reason or "").lower():
                cand["is_valid"] = False
                cand["validation_reason"] = (
                    f"OFFENCE section {sec_label} has no statutory ingredient data in the graph "
                    f"and cannot be validated against case facts — rejected to prevent false positives."
                )
                is_valid = False
                print(f"[LexiGraphAgent] REJECT (no ingredients): {sec_label}")

            if is_valid:
                cand["ingredient_summary"] = self.ingredient_validator_service.get_ingredient_summary(cand, extracted_facts)
                unranked.append(cand)
                self.pipeline_debug_service.log_section_decision(
                    section=cand["section_num"], act=cand["act"], title=cand.get("title", ""),
                    decision="included", stage="Step 4: Ingredient Validation",
                    reason=cand["validation_reason"],
                    scores={"vector_similarity": cand.get("vector_similarity", 0.0), "ingredient_confidence": val_confidence or 0.0}
                )
            else:
                rejected.append({"section": cand["section"], "reason": cand["validation_reason"]})
                self.pipeline_debug_service.log_section_decision(
                    section=cand["section_num"], act=cand["act"], title=cand.get("title", ""),
                    decision="rejected", stage="Step 4: Ingredient Validation",
                    reason=cand["validation_reason"],
                    scores={"vector_similarity": cand.get("vector_similarity", 0.0), "ingredient_confidence": val_confidence or 0.0}
                )

        # --- GRAPH ENRICHMENT FOR ALL UNRANKED CANDIDATES ---
        print("[LexiGraphAgent] Step 4b: Enriching candidates with graph relationships...")
        for cand in unranked:
            relationships = self.verification_service.get_graph_relationships(cand["act"], cand["section_num"])
            cand["relationships"] = relationships  # store for later use
            cand["precedent_count"] = len(relationships.get("supreme_court_cases", [])) + len(relationships.get("high_court_cases", []))
            cand["principle_count"] = len(relationships.get("legal_principles", []))
            cand["evidence_count"] = len(relationships.get("evidence_types", []))

        # Now rerank using the enriched candidates
        rerank_output = self.reranking_service.rerank_candidates({
            "verified_candidates": unranked,
            "primary_intent_community": "anticipatory_bail",
            "top_case_similarity": top_similar_cases[0]["similarity"] if top_similar_cases else 0.8
        })
        ranked_candidates = rerank_output.get("ranked_candidates") or unranked

        # Apply prosecutorial boost and re-sort
        for cand in ranked_candidates:
            prior = float(cand.get("confidence") or 0.8)
            cand["confidence"] = min(1.0, prior + role_cfg["score_boost"])
        ranked_candidates.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)

        top_candidates = ranked_candidates[:6]

        # --- ACT-FAMILY NORMALIZATION ---
        # top_candidates may contain a mix of old-law (IPC/CrPC/IEA) and
        # new-law (BNS/BNSS/BSA) sections. The output must be consistent:
        # pick the act family that has the most substantive offence sections
        # in the top candidates, then replace every section with its
        # preferred-family equivalent where one exists.
        #
        # Preference order matches _ACT_PREFERENCE: BNS > BNSS > BSA > IPC > CrPC > IEA
        # PROCEDURAL/EVIDENCE sections are always kept in the new-law family (BNSS/BSA).
        _OLD_ACTS = {"IPC", "CRPC", "IEA"}
        _NEW_ACTS = {"BNS", "BNSS", "BSA"}

        old_count = sum(1 for c in top_candidates if c["act"] in _OLD_ACTS and c.get("sub_query_type") == "OFFENCE")
        new_count = sum(1 for c in top_candidates if c["act"] in _NEW_ACTS and c.get("sub_query_type") == "OFFENCE")
        prefer_new = new_count >= old_count  # tie goes to new law

        normalized: list = []
        for cand in top_candidates:
            cand_act = cand["act"]
            is_old = cand_act in _OLD_ACTS
            is_new = cand_act in _NEW_ACTS

            # If already in the preferred family, keep as-is
            if (prefer_new and is_new) or (not prefer_new and is_old):
                normalized.append(cand)
                continue

            # Look up the equivalent in the preferred family
            eq = cand.get("equivalent_mapping") or {}
            if not eq:
                eq = self.verification_service.get_equivalent_ipc_section(cand_act, cand["section_num"]) or {}

            eq_act = eq.get("act", "") if isinstance(eq, dict) else ""
            eq_sec = eq.get("section", "") if isinstance(eq, dict) else ""
            target_in_preferred = (prefer_new and eq_act in _NEW_ACTS) or (not prefer_new and eq_act in _OLD_ACTS)

            if eq_act and eq_sec and target_in_preferred:
                # Fetch the equivalent node and substitute
                eq_node = self.verification_service.get_node_info(eq_act, eq_sec)
                if eq_node:
                    # Check whether the equivalent is already in normalized to avoid dupes
                    eq_key = f"{eq_act} {eq_sec}"
                    if any(c["section"] == eq_key for c in normalized):
                        continue  # already represented by the preferred-family version
                    cand = {
                        **cand,
                        "section": eq_key,
                        "act": eq_act,
                        "section_num": eq_sec,
                        "title": eq_node.get("title") or cand["title"],
                        "description": eq_node.get("description") or cand.get("description", ""),
                        "punishment": eq_node.get("punishment") or cand.get("punishment", ""),
                        "equivalent_mapping": {"act": cand_act, "section": cand["section_num"], "title": cand["title"]},
                        "metadata": eq_node,
                    }
            normalized.append(cand)

        top_candidates = normalized

        print(f"[LexiGraphAgent] Step 4 rejected: {rejected}")
        print(f"[LexiGraphAgent] Step 4 top_candidates: {[c['section'] for c in top_candidates]}")

        auto_injected_keys = {"BNSS 482", "CRPC 438"}
        substantive_sections = [c["section"] for c in top_candidates if c["section"] not in auto_injected_keys]
        if not substantive_sections:
            print(f"[LexiGraphAgent] WARNING: no substantive offence section survived.")

        # STEP 5: Build supporting graph from already stored relationships
        print("[LexiGraphAgent] Step 5: Building supporting graph from stored relationships...")
        supporting_graph = self._build_supporting_graph(top_candidates)

        # Re-rank similar cases with actual offence sections
        top_similar_cases = self.precedent_ranking_service.rank_cases(
            cases=top_similar_cases,
            query=query,
            offence_sections=[c["section"] for c in top_candidates],
            debug=debug
        )

        # STEP 6: Legal Reasoning
        print("[LexiGraphAgent] Step 6: Merging Unified Context & Executing Legal Reasoning...")
        case_analysis = self.legal_reasoning_service.analyze_case(
            user_query=query,
            ranked_candidates=top_candidates,
            similar_cases=top_similar_cases,
            supporting_graph=supporting_graph
        )

        top_recommended = []
        for cand in top_candidates:
            eq_sec = cand.get("equivalent_mapping") or self.verification_service.get_equivalent_ipc_section(cand["act"], cand["section_num"])
            top_recommended.append({
                "act": cand["act"],
                "section": cand["section_num"],
                "title": cand["title"],
                "equivalent_section": eq_sec,
                "confidence": cand.get("confidence", 0.85),
                "applicability": cand.get("validation_reason", "Statutory ingredients prima facie present."),
                "ingredient_summary": cand.get("ingredient_summary") or [],
                "reason": "Statutory provision used to oppose pre-arrest bail."
            })

        supporting_cases = []
        for c in top_candidates:
            rel = c.get("relationships") or {}
            for sc in rel.get("supreme_court_cases") or []:
                cname = sc.get("case_name") or sc.get("citation")
                if cname and not any(e["case_name"] == cname for e in supporting_cases):
                    ratio = (sc.get("summary") or sc.get("ratio") or sc.get("ratio_decidendi")
                             or sc.get("holding") or sc.get("held") or "")
                    facts_summary = sc.get("facts") or sc.get("facts_summary") or sc.get("brief_facts") or ""
                    supporting_cases.append({
                        "case_name": cname,
                        "citation": sc.get("citation") or "",
                        "interprets": sc.get("interprets") or [c.get("section")],
                        "binding_under": "Article 141",
                        "facts_summary": facts_summary,
                        "ratio_decidendi": ratio or "No specific ratio recorded in the graph for this precedent — cite it by name/citation only and do not attribute a holding to it.",
                        "has_recorded_ratio": bool(ratio),
                        "reason": f"Interprets/relates to {c.get('section')}, retrieved for this case's facts."
                    })

        production_output = {
            "role": role,
            "query": query,
            "extracted_facts": extracted_facts,
            "pipeline_confidence": top_recommended[0]["confidence"] if top_recommended else 0.8,
            "recommended_sections": top_recommended,
            "supporting_cases": supporting_cases,
            "similar_cases": top_similar_cases[:10],
            "supporting_articles": supporting_graph.get("articles", []),
            "supporting_evidence": self.evidence_ranking_service.rank_evidence(
                evidence_list=supporting_graph.get("evidence", []),
                query=query,
                facts=extracted_facts,
                max_items=6
            ),
            "supporting_principles": supporting_graph.get("principles", []),
            "supporting_graph": supporting_graph,
            "rejected_sections": rejected
        }

        if debug:
            self.pipeline_debug_service.print_summary()
            production_output["debug_trace"] = self.pipeline_debug_service.export_json()

        return production_output

    def render_context_for_agent(self, production_output: Dict[str, Any]) -> str:
        lines = ["=" * 90, "PROSECUTION VERIFIED CONTEXT (ANTICIPATORY BAIL / IPC / BNS / POCSO / DOWRY)", "=" * 90]
        lines.append("\nEXTRACTED CASE FACTS:")
        facts = production_output.get("extracted_facts") or production_output.get("query")
        lines.append(f"  {facts}\n")
        lines.append("=" * 90)
        lines.append("SECTION 1: STATUTORY PROVISIONS (BNS / IPC / BNSS / CrPC / POCSO / DPA / BSA / IEA)")
        lines.append("=" * 90)

        all_sections = production_output.get("recommended_sections", [])

        # Separate definition/offence sections from punishment-quantum companions.
        # Punishment-quantum sections (e.g. IPC 506 / BNS 351(2)) prescribe the
        # sentence for an offence defined elsewhere. They are rendered as a
        # "Punishment provision" annotation on the section they most likely pair
        # with, determined by act-family and equivalent-section cross-reference,
        # rather than as standalone entries (which would mislead the LLM into
        # treating them as independently charged offences).
        punishment_sections = [
            s for s in all_sections
            if s.get("sub_query_type") == "PUNISHMENT_QUANTUM"
            or s.get("validation_reason", "").startswith("Punishment-quantum")
        ]
        definition_sections = [
            s for s in all_sections
            if s not in punishment_sections
        ]

        # Index punishment sections by act for pairing heuristic:
        # pair IPC punishment with IPC definition, BNS punishment with BNS definition.
        punishment_by_act: Dict[str, list] = {}
        for ps in punishment_sections:
            punishment_by_act.setdefault(ps.get("act", ""), []).append(ps)

        def _find_paired_punishment(def_section: Dict[str, Any]) -> list:
            """Return punishment sections that pair with this definition section."""
            paired = []
            def_act = def_section.get("act", "")
            eq = def_section.get("equivalent_section") or {}
            eq_act = eq.get("act", "") if isinstance(eq, dict) else ""
            for ps in punishment_sections:
                ps_act = ps.get("act", "")
                ps_eq = ps.get("equivalent_section") or {}
                ps_eq_act = ps_eq.get("act", "") if isinstance(ps_eq, dict) else ""
                # Pair if same act-family (both IPC, or both BNS) or cross-reference matches
                if ps_act == def_act or ps_act == eq_act or ps_eq_act == def_act:
                    paired.append(ps)
            return paired

        paired_already_shown: set = set()

        for s in definition_sections:
            eq = s.get("equivalent_section")
            header = f"\n[SECTION:{s.get('act')} {s.get('section')}]"
            if eq and isinstance(eq, dict) and eq.get('act') and eq.get('section'):
                eq_title = eq.get('title')
                eq_desc = f" – {eq_title}" if eq_title else ""
                header += f" (corresponding to {eq.get('act')} {eq.get('section')}{eq_desc})"
            lines.append(header)
            lines.append(f"Title: {s.get('title')}")
            lines.append(f"Applicability: {s.get('applicability')}")
            ing_summary = s.get("ingredient_summary") or []
            if ing_summary:
                ing_lines = []
                for ing in ing_summary:
                    tag = "mandatory" if ing.get("mandatory") else "supporting"
                    ing_lines.append(f"{ing.get('name')} [{ing.get('element_type')}, {tag}, {ing.get('state')}]")
                lines.append(f"Statutory Ingredients: {'; '.join(ing_lines)}")

            # Attach any paired punishment-quantum sections as annotations
            paired = _find_paired_punishment(s)
            for ps in paired:
                ps_key = f"{ps.get('act')} {ps.get('section')}"
                if ps_key not in paired_already_shown:
                    ps_eq = ps.get("equivalent_section") or {}
                    ps_eq_str = ""
                    if isinstance(ps_eq, dict) and ps_eq.get("act") and ps_eq.get("section"):
                        ps_eq_str = f" / {ps_eq.get('act')} {ps_eq.get('section')}"
                    punishment_text = ps.get("punishment") or ps.get("description") or ""
                    lines.append(
                        f"Punishment provision: {ps_key}{ps_eq_str} — {ps.get('title', '')}"
                        + (f": {punishment_text}" if punishment_text else "")
                    )
                    paired_already_shown.add(ps_key)

        # Any punishment sections not paired with a definition section
        # (e.g. if the definition section wasn't retrieved) are listed separately
        # with a clear label so the LLM understands they are punishment provisions.
        unpaired = [ps for ps in punishment_sections if f"{ps.get('act')} {ps.get('section')}" not in paired_already_shown]
        if unpaired:
            lines.append("\n[PUNISHMENT PROVISIONS — definition section not separately retrieved]")
            for ps in unpaired:
                ps_eq = ps.get("equivalent_section") or {}
                ps_eq_str = ""
                if isinstance(ps_eq, dict) and ps_eq.get("act") and ps_eq.get("section"):
                    ps_eq_str = f" (corresponding to {ps_eq.get('act')} {ps_eq.get('section')})"
                lines.append(f"  {ps.get('act')} {ps.get('section')}{ps_eq_str}: {ps.get('title', '')} — {ps.get('punishment', '')}")

        lines.append("\n" + "=" * 90)
        lines.append("SECTION 2: LANDMARK PRECEDENTS & SIMILAR CASES (Top 5-10)")
        lines.append("=" * 90)
        all_cases = production_output.get("supporting_cases", []) + production_output.get("similar_cases", [])
        def _case_sort_key(c):
            has_ratio = bool(c.get("ratio_decidendi") or c.get("reasoning") or c.get("judgment_summary")
                              or c.get("holding") or c.get("held"))
            sim = float(c.get("similarity") or c.get("case_similarity") or 0.0)
            return (has_ratio, sim)
        all_cases = sorted(all_cases, key=_case_sort_key, reverse=True)
        for c in all_cases[:10]:
            name = c.get("case_name") or c.get("title") or "Supreme Court Precedent"
            lines.append(f"\n[CASE:{name}]")
            lines.append(f"Court: {c.get('court', 'Supreme Court of India')}")
            lines.append(f"Citation: {c.get('citation', 'N/A')}")
            facts_summary = c.get("facts_summary") or c.get("facts") or c.get("brief_facts")
            if facts_summary:
                lines.append(f"Facts of precedent: {facts_summary}")
            interprets = c.get("interprets")
            if interprets:
                lines.append(f"Interprets/Relates to: {', '.join(interprets) if isinstance(interprets, list) else interprets}")
            ratio = (c.get('ratio_decidendi') or c.get('reasoning') or c.get('judgment_summary')
                     or c.get('holding') or c.get('held'))
            if ratio and ratio != "No specific ratio recorded in the graph for this precedent — cite it by name/citation only and do not attribute a holding to it.":
                lines.append(f"Ratio/Holding: {ratio}")
            else:
                lines.append("Ratio/Holding: NOT RECORDED - cite this case by name/citation only; do not attribute a holding to it.")
        lines.append("\n" + "=" * 90)
        lines.append("SECTION 3: LEGAL PRINCIPLES & EVIDENTIARY PRESUMPTIONS")
        lines.append("=" * 90)
        for p in production_output.get("supporting_principles", []):
            lines.append(f"[PRINCIPLE:{p}]")
        for e in production_output.get("supporting_evidence", []):
            lines.append(f"[EVIDENCE:{e}]")
        return "\n".join(lines)

    def verify_claims(self, generated_text: str, production_output: Dict[str, Any]) -> Dict[str, Any]:
        # (unchanged; keep as provided)
        retrieved_section_keys = {
            (s.get("act"), s.get("section")) for s in production_output.get("recommended_sections", [])
        }
        retrieved_case_names = {
            str(c.get("case_name", "")).lower().strip()
            for c in (production_output.get("supporting_cases", []) + production_output.get("similar_cases", []))
        }

        result = {
            "is_clean": True,
            "verified_sections": [],
            "real_but_ungrounded_sections": [],
            "hallucinated_sections": [],
            "verified_cases": [],
            "unverified_cases": [],
        }

        section_matches = re.findall(r'\b(BNS|IPC|BNSS|CRPC|BSA|IEA|POCSO|DPA)\s*(\d+[A-Za-z]?)\b', generated_text, flags=re.IGNORECASE)
        seen_sections = set()
        for act_raw, sec_raw in section_matches:
            act_norm, sec_norm = _normalize_section_params(act_raw, sec_raw)
            key = (act_norm, sec_norm)
            if key in seen_sections:
                continue
            seen_sections.add(key)

            if key in retrieved_section_keys:
                result["verified_sections"].append(f"{act_norm} {sec_norm}")
                continue

            node_info = self.verification_service.get_node_info(act_norm, sec_norm)
            if node_info:
                result["real_but_ungrounded_sections"].append(f"{act_norm} {sec_norm}")
                result["is_clean"] = False
            else:
                result["hallucinated_sections"].append(f"{act_norm} {sec_norm}")
                result["is_clean"] = False

        joiner = r"(?:of|the|and)"
        title_token = r"[A-Z][A-Za-z.]*"
        name_run = rf"{title_token}(?:\s+(?:{title_token}|{joiner})){{0,6}}"
        case_name_pattern = re.compile(rf"\b({name_run}\s+v\.?s?\.?\s+{name_run})\b")

        seen_cases = set()
        for line in generated_text.splitlines():
            for m in case_name_pattern.findall(line):
                normalized = m.lower().strip()
                if normalized in seen_cases:
                    continue
                seen_cases.add(normalized)

                match = any(normalized in stored or stored in normalized
                            for stored in retrieved_case_names if stored)
                if match:
                    result["verified_cases"].append(m.strip())
                else:
                    result["unverified_cases"].append(m.strip())
                    result["is_clean"] = False

        return result

    def _build_supporting_graph(self, top_candidates: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
        """Aggregates articles, evidence, principles from already stored relationships."""
        articles, evidence, principles = set(), set(), set()
        cases: List[Dict[str, Any]] = []
        raw_relationship_keys: set = set()

        for cand in top_candidates:
            rel = cand.get("relationships") or {}
            raw_relationship_keys.update(rel.keys())

            for a in (rel.get("constitutional_articles") or rel.get("articles") or []):
                name = a.get("article") if isinstance(a, dict) else a
                if name:
                    articles.add(name)

            for e in (rel.get("evidence_types") or rel.get("evidence") or []):
                name = e.get("name") if isinstance(e, dict) else e
                if name:
                    evidence.add(name)

            for p in (rel.get("legal_principles") or rel.get("principles") or []):
                name = p.get("name") if isinstance(p, dict) else p
                if name:
                    principles.add(name)

            for sc in (rel.get("supreme_court_cases") or []):
                cases.append(sc)

        if top_candidates and not (articles or evidence or principles):
            print(f"[LexiGraphAgent] NOTE: no articles/evidence/principles extracted. Keys seen: {sorted(raw_relationship_keys) or '(empty)'}")

        return {
            "articles": sorted(articles),
            "cases": cases,
            "evidence": sorted(evidence),
            "principles": sorted(principles),
        }

    def _validate_legal_applicability(self, candidate: Dict[str, Any], extracted_facts: str, primary_intent: str) -> Tuple[bool, str, Any]:
        result = self.ingredient_validator_service.validate_candidate(candidate, extracted_facts)
        if isinstance(result, (tuple, list)):
            if len(result) >= 3:
                is_valid, confidence, reason = result[0], result[1], result[2]
            elif len(result) == 2:
                is_valid, confidence, reason = result[0], None, result[1]
            elif len(result) == 1:
                is_valid, confidence, reason = result[0], None, ""
            else:
                is_valid, confidence, reason = False, None, "validate_candidate returned no data"
        else:
            is_valid, confidence, reason = bool(result), None, ""
        return is_valid, reason, confidence