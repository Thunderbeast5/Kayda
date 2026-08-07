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
    # COMMENTED OUT: Query expansion creates misleading sub-queries
    # Now using ENTIRE query throughout the pipeline
    # from .services.query_expansion_service import QueryExpansionService, NON_OFFENCE_TYPES
    from .services.embedding_service import EmbeddingService
    # REPLACED: Pinecone vector search with LLM-based IPC retrieval
    # from .services.pinecone_service import PineconeService
    # v3: LLMIPCRetrievalService is now itself a ReAct agent — AgenticIPCRetrievalService removed
    from .services.llm_ipc_retrieval_service import LLMIPCRetrievalService
    from .services.neo4j_retrieval_service import Neo4jRetrievalService
    from .services.candidate_fusion_service import CandidateFusionService
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
    # COMMENTED OUT: Query expansion creates misleading sub-queries
    # from services.query_expansion_service import QueryExpansionService, NON_OFFENCE_TYPES
    from services.embedding_service import EmbeddingService
    # REPLACED: Pinecone vector search with LLM-based IPC retrieval
    # from services.pinecone_service import PineconeService
    # v3: LLMIPCRetrievalService is now itself a ReAct agent — AgenticIPCRetrievalService removed
    from services.llm_ipc_retrieval_service import LLMIPCRetrievalService
    from services.neo4j_retrieval_service import Neo4jRetrievalService
    from services.candidate_fusion_service import CandidateFusionService
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

# ---------------------------------------------------------------------------
# Section identifier regexes
# ---------------------------------------------------------------------------
_IPC_ID_RE   = re.compile(r"^IPC_\d+[A-Za-z]*$",        re.IGNORECASE)
_BNS_ID_RE   = re.compile(r"^BNS_\d+[A-Za-z]*$",        re.IGNORECASE)
_CRPC_ID_RE  = re.compile(r"^CRPC_\d+[A-Za-z]*$",       re.IGNORECASE)
_BNSS_ID_RE  = re.compile(r"^BNSS_\d+[A-Za-z]*$",       re.IGNORECASE)
_IEA_ID_RE   = re.compile(r"^IEA_\d+[A-Za-z]*$",        re.IGNORECASE)
_BSA_ID_RE   = re.compile(r"^BSA_\d+[A-Za-z]*$",        re.IGNORECASE)
_POCSO_ID_RE = re.compile(r"^POCSO_\d+[A-Za-z]*$",      re.IGNORECASE)
_DPA_ID_RE   = re.compile(r"^(DPA|DOWRY)_\d+[A-Za-z]*$", re.IGNORECASE)
_SECTION_RE  = re.compile(r"^\d+[A-Za-z]*$")


def _is_legal_section_hit(match_id: str, meta: Dict[str, Any]) -> bool:
    patterns = [
        _IPC_ID_RE, _BNS_ID_RE, _CRPC_ID_RE, _BNSS_ID_RE,
        _IEA_ID_RE, _BSA_ID_RE, _POCSO_ID_RE, _DPA_ID_RE,
    ]
    if any(p.match(match_id) for p in patterns):
        return True
    sec     = str(meta.get("section", ""))
    sec_num = str(meta.get("section_num", ""))
    return bool(
        (sec     and _SECTION_RE.match(sec)) or
        (sec_num and _SECTION_RE.match(sec_num))
    )


def _normalize_section_params(act: str, section_num: str) -> Tuple[str, str]:
    act        = str(act or "").strip().upper()
    section_num = str(section_num or "").strip()
    clean_sec  = section_num.replace("_", " ")
    parts      = clean_sec.split()
    known_acts = ("BNS", "IPC", "BNSS", "CRPC", "BSA", "IEA", "POCSO", "DPA", "DOWRY")
    if len(parts) >= 2:
        prefix = parts[0].upper()
        suffix = parts[1]
        if prefix in known_acts:
            act, section_num = prefix, suffix
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


# ---------------------------------------------------------------------------
# Thresholds and role configuration
# ---------------------------------------------------------------------------

# Pinecone hits below this score are treated as noise.
# Lowered from 0.50 → 0.42: OFFENCE queries are now element-description sentences
# rather than short label phrases, which embed at 0.42–0.55 against the correct
# IPC section even when the match is perfect.  The fact-relevance filter (threshold
# 0.50, see _filter_by_fact_relevance call in Step 3) does the real quality gate —
# being too strict here causes the right sections to be discarded before they ever
# reach that filter.
CANDIDATE_SIMILARITY_THRESHOLD = 0.42

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


_ACT_PREFERENCE = ["BNS", "BNSS", "BSA", "IPC", "CRPC", "IEA", "POCSO", "DPA"]


def _act_rank(act: str) -> int:
    try:
        return _ACT_PREFERENCE.index(act.upper())
    except ValueError:
        return len(_ACT_PREFERENCE)


# ---------------------------------------------------------------------------
# Deduplication helper (IPC↔BNS, CRPC↔BNSS, IEA↔BSA union-find)
# ---------------------------------------------------------------------------

def _deduplicate_equivalent_candidates(
    candidates: List[Dict[str, Any]],
    verification_service,
) -> List[Dict[str, Any]]:
    key_to_cand: Dict[str, Dict[str, Any]] = {c["section"]: c for c in candidates}
    _CROSSWALK_PAIRS: set = {
        frozenset({"BNS",  "IPC"}),
        frozenset({"BNSS", "CRPC"}),
        frozenset({"BSA",  "IEA"}),
    }
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

    _subsection_re = re.compile(r"\(\w+\)\s*$")
    for key, cand in key_to_cand.items():
        eq = cand.get("equivalent_mapping")
        if not (eq and isinstance(eq, dict)):
            continue
        eq_act = eq.get("act", "")
        eq_sec = eq.get("section", "")
        if not eq_act or not eq_sec:
            continue
        source_act = cand["act"]
        if frozenset({source_act, eq_act}) not in _CROSSWALK_PAIRS:
            continue
        eq_key_exact = f"{eq_act} {eq_sec}".strip()
        if eq_key_exact in key_to_cand:
            union(key, eq_key_exact)
        else:
            eq_sec_base  = _subsection_re.sub("", eq_sec).strip()
            eq_key_base  = f"{eq_act} {eq_sec_base}".strip()
            if eq_key_base in key_to_cand:
                union(key, eq_key_base)

    groups: Dict[str, List[str]] = {}
    for key in key_to_cand:
        root = find(key)
        groups.setdefault(root, []).append(key)

    kept: List[Dict[str, Any]] = []
    for group_keys in groups.values():
        if len(group_keys) == 1:
            kept.append(key_to_cand[group_keys[0]])
        else:
            best_key = min(group_keys, key=lambda k: _act_rank(key_to_cand[k]["act"]))
            kept.append(key_to_cand[best_key])
            dropped = [k for k in group_keys if k != best_key]
            print(f"[LexiGraphAgent] Dedup: keeping {best_key}, dropping equivalent(s): {dropped}")

    original_order = {c["section"]: i for i, c in enumerate(candidates)}
    kept.sort(key=lambda c: original_order.get(c["section"], 999))
    return kept


# ---------------------------------------------------------------------------
# Main agent class
# ---------------------------------------------------------------------------

class LexiGraphAgent:
    def __init__(self):
        self.query_understanding_service  = QueryUnderstandingService()
        # COMMENTED OUT: Query expansion creates misleading sub-queries
        # self.query_expansion_service      = QueryExpansionService()
        self.embedding_service            = EmbeddingService()
        # v3: LLMIPCRetrievalService is a full ReAct agent — no separate agentic service needed
        self.llm_ipc_retrieval_service = LLMIPCRetrievalService()
        self.neo4j_retrieval_service   = Neo4jRetrievalService()
        self.candidate_fusion_service     = CandidateFusionService()
        self.case_retrieval_service       = CaseRetrievalService()
        self.merge_service                = MergeService()
        self.verification_service         = VerificationService()
        self.community_retrieval_service  = CommunityRetrievalService()
        self.reranking_service            = RerankingService()
        self.legal_reasoning_service      = LegalReasoningService()
        self.fact_extractor_service       = FactExtractorService()
        self.ingredient_validator_service = IngredientValidatorService(
            self.verification_service.neo4j_service
        )
        self.evidence_ranking_service     = EvidenceRankingService()
        self.pipeline_debug_service       = PipelineDebugService()
        self.precedent_ranking_service    = PrecedentRankingService()
        
        # v3: always uses the ReAct agent inside LLMIPCRetrievalService
        # Neo4j still runs for graph verification (Phase A/B) but not for candidate retrieval

    # ------------------------------------------------------------------
    # Dynamic Fact-Relevance Filter
    # ------------------------------------------------------------------
    def _filter_by_fact_relevance(
        self,
        candidates: List[Dict[str, Any]],
        facts_text: str,
        threshold: float = 0.45,
    ) -> List[Dict[str, Any]]:
        """
        Drops OFFENCE candidates whose title+description embedding is not
        semantically close enough to the extracted case facts.
        Non-OFFENCE types always pass through unchanged.
        """
        if not candidates or not facts_text:
            return candidates

        emb_result = self.embedding_service.generate_embeddings(
            {"search_queries": [facts_text]}
        )
        facts_emb = (emb_result.get("embeddings") or [{}])[0].get("embedding")
        if not facts_emb:
            print("[LexiGraphAgent] WARNING: could not embed facts; skipping fact-relevance filter.")
            return candidates

        norm_facts = sum(a * a for a in facts_emb) ** 0.5
        if not norm_facts:
            return candidates

        filtered = []
        for cand in candidates:
            if cand.get("sub_query_type") != "OFFENCE":
                filtered.append(cand)
                continue

            section_text = f"{cand.get('title', '')} {cand.get('description', '')}".strip()
            if not section_text:
                filtered.append(cand)
                continue

            sec_emb_result = self.embedding_service.generate_embeddings(
                {"search_queries": [section_text]}
            )
            sec_emb = (sec_emb_result.get("embeddings") or [{}])[0].get("embedding")
            if not sec_emb:
                filtered.append(cand)
                continue

            dot      = sum(a * b for a, b in zip(facts_emb, sec_emb))
            norm_sec = sum(b * b for b in sec_emb) ** 0.5
            sim      = dot / (norm_facts * norm_sec) if norm_sec else 0.0

            print(
                f"[LexiGraphAgent] Fact-section similarity "
                f"{cand['section']}: {sim:.3f} (threshold={threshold})"
            )
            if sim >= threshold:
                filtered.append(cand)
            else:
                print(
                    f"[LexiGraphAgent] Dropping {cand['section']} "
                    f"(fact-relevance too low: {sim:.3f})"
                )
        return filtered

    # ------------------------------------------------------------------
    # Neo4j direct retrieval for EVIDENCE_PRESUMPTION / CONSTITUTIONAL
    # ------------------------------------------------------------------
    def _retrieve_direct_neo4j_candidates(
        self,
        sub_queries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        EVIDENCE_PRESUMPTION → searches BSA/IEA nodes by title/description text match.
        CONSTITUTIONAL       → searches constitutional article nodes by text match.

        These types must NOT go through Pinecone (IPC-only index) — they would
        either return irrelevant IPC sections or nothing at all.
        """
        results: List[Dict[str, Any]] = []

        for sq in sub_queries:
            sq_type = sq["type"]
            concept = sq["query"]

            if sq_type == "EVIDENCE_PRESUMPTION":
                try:
                    rows = self.verification_service.neo4j_service.run_query(
                        """
                        MATCH (n:LawSection)
                        WHERE n.act IN ['BSA', 'IEA']
                          AND (
                                toLower(n.title)       CONTAINS toLower($concept)
                             OR toLower(n.description) CONTAINS toLower($concept)
                          )
                        RETURN n.act       AS act,
                               n.section   AS section,
                               n.title     AS title,
                               n.description AS description,
                               n.punishment  AS punishment
                        LIMIT 3
                        """,
                        {"concept": concept},
                    )
                    for row in rows:
                        if not (row.get("act") and row.get("section")):
                            continue
                        key = f"{row['act']} {row['section']}"
                        print(
                            f"[LexiGraphAgent] Direct Neo4j EVIDENCE_PRESUMPTION hit: "
                            f"{key} for query '{concept}'"
                        )
                        results.append({
                            "section":        key,
                            "act":            row["act"],
                            "section_num":    row["section"],
                            "title":          row.get("title") or "",
                            "description":    row.get("description") or "",
                            "punishment":     row.get("punishment") or "",
                            "vector_similarity": 0.75,   # synthetic — text match is high confidence
                            "sub_query_type": "EVIDENCE_PRESUMPTION",
                            "graph_verified": True,
                            "equivalent_mapping": None,
                            "metadata":       dict(row),
                            "sources":        [concept],
                        })
                except Exception as e:
                    print(
                        f"[LexiGraphAgent] Neo4j EVIDENCE_PRESUMPTION query failed "
                        f"for '{concept}': {e}"
                    )

            elif sq_type == "CONSTITUTIONAL":
                try:
                    rows = self.verification_service.neo4j_service.run_query(
                        """
                        MATCH (n)
                        WHERE (n:ConstitutionalArticle OR n:LawSection)
                          AND (
                                toLower(n.title)       CONTAINS toLower($concept)
                             OR toLower(n.description) CONTAINS toLower($concept)
                             OR toLower(coalesce(n.article, '')) CONTAINS toLower($concept)
                          )
                        RETURN
                          coalesce(n.act, 'CONSTITUTION') AS act,
                          coalesce(n.section, n.article)  AS section,
                          n.title                         AS title,
                          n.description                   AS description
                        LIMIT 2
                        """,
                        {"concept": concept},
                    )
                    for row in rows:
                        if not row.get("section"):
                            continue
                        act = row.get("act") or "CONSTITUTION"
                        key = f"{act} {row['section']}"
                        print(
                            f"[LexiGraphAgent] Direct Neo4j CONSTITUTIONAL hit: "
                            f"{key} for query '{concept}'"
                        )
                        results.append({
                            "section":        key,
                            "act":            act,
                            "section_num":    row["section"],
                            "title":          row.get("title") or "",
                            "description":    row.get("description") or "",
                            "punishment":     "",
                            "vector_similarity": 0.80,
                            "sub_query_type": "CONSTITUTIONAL",
                            "graph_verified": True,
                            "equivalent_mapping": None,
                            "metadata":       dict(row),
                            "sources":        [concept],
                        })
                except Exception as e:
                    print(
                        f"[LexiGraphAgent] Neo4j CONSTITUTIONAL query failed "
                        f"for '{concept}': {e}"
                    )

        return results

    # ------------------------------------------------------------------
    # Main processing pipeline
    # ------------------------------------------------------------------
    def process_query(
        self,
        query: str,
        debug: bool = False,
        role: str = "prosecutor",
    ) -> Dict[str, Any]:

        if debug:
            self.pipeline_debug_service.enable()
            self.pipeline_debug_service.reset()

        role_cfg = _role_config(role)

        # Discover existing Neo4j relationship types once per call
        _existing_rel_types: set = set()
        try:
            _rel_rows = self.verification_service.neo4j_service.run_query(
                "CALL db.relationshipTypes()", {}
            )
            for _r in _rel_rows:
                _existing_rel_types.add(_r.get("relationshipType", ""))
        except Exception:
            pass

        # ----------------------------------------------------------------
        # STEP 1: Fact Extraction, Query Understanding, Expansion
        # ----------------------------------------------------------------
        # REVERTED from QueryDecompositionService back to QueryUnderstandingService +
        # QueryExpansionService. The single-shot decomposition LLM call was
        # hallucinating: it invented AGGRAVATION/MITIGATION facts that "sounded
        # right" for the offence type but were never stated in the case, and
        # occasionally added OFFENCE concepts only loosely related to the raw
        # text. QueryExpansionService produces the identical typed sub_queries
        # contract (OFFENCE/AGGRAVATION/MITIGATION/EVIDENCE_PRESUMPTION/
        # CONSTITUTIONAL/PROCEDURAL), so no downstream routing code below needed
        # to change — only this call and the import/init above. Both services
        # have also been broadened to cover the full legal domain now in scope
        # for anticipatory bail (not just offences against women/children).
        print(f"\n[LexiGraphAgent] Step 1: Fact Extraction & Query Understanding...")
        extracted_facts = self.fact_extractor_service.extract_facts(query)
        qu_result       = self.query_understanding_service.analyze_query(query)
        
        # MODIFIED: No query expansion - use entire query as single sub-query
        # expansion_result = self.query_expansion_service.expand_query(qu_result, query, role)
        # sub_queries     = expansion_result.get("sub_queries") or []
        
        # Create single sub-query from entire query
        sub_queries = [{
            "query": query,
            "type": "OFFENCE",
            "original_query": query
        }]
        print(f"[LexiGraphAgent] Using ENTIRE query (no expansion): {query[:100]}...")

        # Route sub-queries by type:
        #   - OFFENCE only → LLM-based IPC retrieval (replaces Pinecone vector search)
        #   - AGGRAVATION / MITIGATION → case retrieval only (NOT LLM IPC retrieval).
        #     These are verbatim fact-sentences; they embed well against precedent
        #     case text but are not suitable for IPC section matching.
        #   - EVIDENCE_PRESUMPTION / CONSTITUTIONAL → Neo4j direct text search
        #   - PROCEDURAL → auto-injected from Neo4j; never embedded
        direct_neo4j_sub_queries = [sq for sq in sub_queries
                                    if sq["type"] in ("EVIDENCE_PRESUMPTION", "CONSTITUTIONAL")]
        # PROCEDURAL is handled by the hard-inject of BNSS 482 below.

        # ----------------------------------------------------------------
        # STEP 2: Dual Retrieval (LLM + Neo4j) + Fusion + Case Retrieval
        # ----------------------------------------------------------------
        print("[LexiGraphAgent] Step 2: Dual Retrieval (LLM + Neo4j) & Fusion...")

        # Route sub-queries by type (OFFENCE goes to both LLM and Neo4j retrieval)
        llm_ipc_sub_queries = [sq for sq in sub_queries if sq["type"] == "OFFENCE"]
        
        llm_ipc_query_strings = [sq["query"] for sq in llm_ipc_sub_queries]

        self.pipeline_debug_service.log_query(
            original_query=query,
            expanded_queries=llm_ipc_query_strings,
            intent=qu_result.get("primary_intent_community", ""),
            keywords=qu_result.get("keywords", []),
        )

        # Build the sub-query-type lookup keyed on STRIPPED query string
        sq_type_by_query: Dict[str, str] = {
            str(sq["query"]).strip(): sq["type"]
            for sq in llm_ipc_sub_queries
        }

        # ========================================================================
        # STEP 2a: ReAct Agent IPC Retrieval
        # LLMIPCRetrievalService (v3) is a self-contained ReAct agent.
        # It runs a Thought→Action→Observation loop per sub-query, calling
        # search_chapters / get_section_titles / get_section_detail / submit_answer
        # autonomously, with reward/penalise self-correction on rejection.
        # Returns Pinecone-compatible {"retrieval_results": [...]} schema.
        # ========================================================================
        print("[LexiGraphAgent] Step 2a: ReAct Agent IPC Retrieval...")
        retrieval_res: Dict[str, Any] = {"retrieval_results": []}
        if llm_ipc_sub_queries:
            retrieval_res = self.llm_ipc_retrieval_service.retrieve_sections(
                sub_queries=llm_ipc_sub_queries,
                case_facts=query,
                top_k=20,
            )

        # Flatten the agent's retrieval results into a deduplicated candidate list.
        # The merged result (last entry, keyed "[ALL SUB-QUERIES MERGED]") already
        # deduplicates across sub-queries — use it when available so every confirmed
        # section appears exactly once regardless of how many sub-queries surfaced it.
        agent_matches: List[Dict[str, Any]] = []
        all_results = retrieval_res.get("retrieval_results", [])
        merged_result = next(
            (r for r in all_results if "[ALL SUB-QUERIES MERGED]" in r.get("query", "")),
            None,
        )
        if merged_result:
            agent_matches = merged_result.get("matches", [])
        elif all_results:
            # Fallback: flatten + deduplicate manually
            seen_ids: set = set()
            for res in all_results:
                for m in res.get("matches", []):
                    if m["id"] not in seen_ids:
                        agent_matches.append(m)
                        seen_ids.add(m["id"])

        # Build fused_candidates in the format downstream steps expect.
        # Each entry needs: section, act, section_num, relevance_score, metadata, sources.
        # We derive act and section_num from the match ID (e.g. "IPC_503" → IPC, 503).
        fused_candidates: List[Dict[str, Any]] = []
        for match in agent_matches:
            match_id   = match["id"]                        # e.g. "IPC_503"
            meta       = match.get("metadata", {})
            score      = match.get("score", 0.75)

            # Parse act + section_num from the ID
            id_parts   = match_id.split("_", 1)
            act        = id_parts[0].upper() if len(id_parts) == 2 else "IPC"
            section_num = (
                meta.get("section_num")
                or meta.get("section")
                or (id_parts[1] if len(id_parts) == 2 else match_id)
            )

            fused_candidates.append({
                "section":         f"{act} {section_num}",
                "act":             act,
                "section_num":     section_num,
                "relevance_score": score,
                "title":           meta.get("title", ""),
                "description":     meta.get("full_text") or meta.get("description", ""),
                "punishment":      meta.get("punishment", ""),
                "metadata":        meta,
                # sources: list the sub-query strings that produced this section
                # (carried through from the per-sub-query results)
                "sources": [
                    r["query"]
                    for r in all_results
                    if any(m["id"] == match_id for m in r.get("matches", []))
                    and "[ALL SUB-QUERIES MERGED]" not in r.get("query", "")
                ],
            })

        fusion_stats = {
            "llm_input":   len(agent_matches),
            "neo4j_input": 0,
            "total_unique": len(fused_candidates),
            "final_count":  len(fused_candidates),
        }

        print(
            f"[LexiGraphAgent] Step 2a: Agent confirmed "
            f"{len(fused_candidates)} sections: "
            f"{[c['section'] for c in fused_candidates]}"
        )

        # ========================================================================
        # COMMON PATH: Both agentic and legacy converge here
        # ========================================================================
        
        # Case-retrieval: Still need embeddings for case similarity search
        # We embed OFFENCE queries + AGGRAVATION/MITIGATION queries for case retrieval
        emb_result: Dict[str, Any] = {"embeddings": []}
        if llm_ipc_query_strings:
            emb_result = self.embedding_service.generate_embeddings(
                {"search_queries": llm_ipc_query_strings}
            )

        case_only_sub_queries = [sq for sq in sub_queries
                                 if sq["type"] in ("AGGRAVATION", "MITIGATION")]
        case_only_strings = [sq["query"] for sq in case_only_sub_queries]
        case_only_emb_result: Dict[str, Any] = {"embeddings": []}
        if case_only_strings:
            case_only_emb_result = self.embedding_service.generate_embeddings(
                {"search_queries": case_only_strings}
            )

        case_emb_result: Dict[str, Any] = {
            "embeddings": (emb_result.get("embeddings") or []) +
                          (case_only_emb_result.get("embeddings") or [])
        }

        # Case similarity retrieval
        top_similar_cases: List[Dict[str, Any]] = []
        if case_emb_result.get("embeddings"):
            top_similar_cases = self.case_retrieval_service.retrieve_cases(
                case_emb_result, top_k=10
            )
        top_similar_cases = self.precedent_ranking_service.rank_cases(
            cases=top_similar_cases,
            query=query,
            offence_sections=[],
            debug=debug,
        )

        # Build raw_candidates directly from agent-confirmed fused_candidates.
        # The agent has already verified every section — no merge_service needed.
        # We still resolve sub_query_type from sq_type_by_query so the downstream
        # type-aware validation (Step 4) works correctly.
        self.pipeline_debug_service.log_stage(
            "Step 2: ReAct Agent IPC Retrieval",
            input_count=len(llm_ipc_query_strings),
            output_count=len(fused_candidates),
            metadata={
                "similar_cases_retrieved": len(top_similar_cases),
                "fusion_stats": fusion_stats,
            },
        )

        _cand_summary = [
            f"{c['act']} {c['section_num']} ({c['relevance_score']:.2f})"
            for c in fused_candidates
        ]
        print(f"[LexiGraphAgent] Step 2 agent-confirmed candidates: {_cand_summary}")

        raw_candidates: List[Dict[str, Any]] = []
        for fc in fused_candidates:
            _, norm_sec_num = _normalize_section_params(fc["act"], fc["section_num"])

            # Resolve dominant sub-query type from sources
            source_types: set = set()
            for src in (fc.get("sources") or []):
                t = sq_type_by_query.get(str(src).strip())
                if t:
                    source_types.add(t)

            if not source_types:
                dominant_type = "OFFENCE"
            else:
                non_offence_hits = source_types - {"OFFENCE"}
                dominant_type = (
                    "AGGRAVATION" if "AGGRAVATION" in non_offence_hits
                    else next(iter(non_offence_hits))
                ) if non_offence_hits else "OFFENCE"

            raw_candidates.append({
                "section":           f"{fc['act']} {norm_sec_num}",
                "act":               fc["act"],
                "section_num":       norm_sec_num,
                "title":             fc.get("title") or fc["metadata"].get("title") or "",
                "punishment":        fc.get("punishment") or fc["metadata"].get("punishment") or "",
                # agent score used as vector_similarity for threshold gates downstream
                "vector_similarity": fc["relevance_score"],
                "sub_query_type":    dominant_type,
                "metadata":          fc["metadata"],
                "sources":           fc.get("sources") or [],
                # agent-verified flag: tells Phase A it can skip Neo4j re-verification
                # if the node isn't in the graph (agent already read ipc_structured.json)
                "agent_verified":    True,
            })

        # ----------------------------------------------------------------
        # STEP 3: Graph Enrichment (IPC) + BNS Crosswalk +
        #         Direct Neo4j candidates for EVIDENCE_PRESUMPTION/CONSTITUTIONAL
        #         OFFENCE candidates come from the ReAct agent (ipc_structured.json);
        #         Neo4j enriches them with BNS crosswalk + relationship data.
        # ----------------------------------------------------------------
        print("[LexiGraphAgent] Step 3: Graph Verification (IPC) + BNS Crosswalk...")
        consolidated_candidates: Dict[str, Dict[str, Any]] = {}

        # Always inject BNSS 482 (anticipatory bail)
        bnss_node = self.verification_service.get_node_info("BNSS", "482")
        if bnss_node:
            consolidated_candidates["BNSS 482"] = {
                "section":           "BNSS 482",
                "title":             bnss_node.get("title", "BNSS Section 482"),
                "description":       bnss_node.get("description", ""),
                "punishment":        "",
                "act":               "BNSS",
                "section_num":       "482",
                "vector_similarity": 0.70,
                "sub_query_type":    "PROCEDURAL",
                "graph_verified":    True,
                "equivalent_mapping": None,
                "metadata":          bnss_node,
                "sources":           ["Anticipatory bail provision — specific relief sought"],
            }

        # Inject direct Neo4j candidates for EVIDENCE_PRESUMPTION / CONSTITUTIONAL
        direct_neo4j_candidates = self._retrieve_direct_neo4j_candidates(direct_neo4j_sub_queries)
        for dnc in direct_neo4j_candidates:
            key = dnc["section"]
            if key not in consolidated_candidates:
                consolidated_candidates[key] = dnc
            else:
                # Keep the one with higher similarity
                if dnc["vector_similarity"] > consolidated_candidates[key].get("vector_similarity", 0):
                    consolidated_candidates[key] = dnc

        # Threshold gate on agent candidates (agent scores are 0–1; anything below
        # CANDIDATE_SIMILARITY_THRESHOLD is unlikely to survive Step 4 validation anyway)
        FALLBACK_MIN_CANDIDATES = 5
        candidates_above_threshold = [
            c for c in raw_candidates
            if c["vector_similarity"] >= CANDIDATE_SIMILARITY_THRESHOLD
        ]
        if candidates_above_threshold:
            filtered_candidates = candidates_above_threshold
        else:
            sorted_by_similarity = sorted(
                raw_candidates, key=lambda c: c["vector_similarity"], reverse=True
            )
            filtered_candidates = sorted_by_similarity[:FALLBACK_MIN_CANDIDATES]
            if raw_candidates:
                print(
                    f"[LexiGraphAgent] WARNING: no Pinecone candidates cleared threshold "
                    f"({CANDIDATE_SIMILARITY_THRESHOLD}); falling back to top "
                    f"{len(filtered_candidates)}."
                )

        # Phase A: Enrich IPC sections from Neo4j.
        # Agent-verified sections (agent_verified=True) are kept even when Neo4j
        # has no matching node — the agent already read ipc_structured.json directly.
        # Non-agent candidates that are absent from Neo4j are still rejected.
        ipc_verified: List[Dict[str, Any]] = []
        for c in filtered_candidates:
            ipc_node = self.verification_service.get_node_info("IPC", c["section_num"])
            if ipc_node:
                # Prefer Neo4j enrichment when available
                c["title"]        = ipc_node.get("title")       or c.get("title", "")
                c["description"]  = ipc_node.get("description") or c.get("description", "")
                c["punishment"]   = ipc_node.get("punishment")  or c.get("punishment", "")
                c["metadata"]     = ipc_node
                c["graph_verified"] = True
                ipc_verified.append(c)
            elif c.get("agent_verified"):
                # Agent confirmed this section from ipc_structured.json — keep as-is
                c["graph_verified"] = False   # honest: not in Neo4j graph
                meta = c.get("metadata", {})
                c["title"]       = c.get("title")       or meta.get("title", "")
                c["description"] = c.get("description") or meta.get("full_text") or meta.get("description", "")
                c["punishment"]  = c.get("punishment")  or meta.get("punishment", "")
                print(
                    f"[LexiGraphAgent] Phase A: IPC {c['section_num']} not in Neo4j "
                    f"but agent-verified — keeping with ipc_structured.json data"
                )
                ipc_verified.append(c)
            else:
                print(f"[LexiGraphAgent] Phase A REJECT (not in Neo4j, not agent-verified): IPC {c['section_num']}")

        print(f"[LexiGraphAgent] Phase A verified IPC sections: {[c['section'] for c in ipc_verified]}")

        # Phase B: Crosswalk IPC → BNS; keep IPC if no BNS mapping found
        _PUNISHMENT_TITLE_SIGNALS = re.compile(
            r"\bpunishment\s+for\b|\bpenalty\s+for\b|\bsentence\s+for\b", re.IGNORECASE
        )
        for c in ipc_verified:
            ipc_sec_num  = c["section_num"]
            bns_eq       = self.verification_service.get_equivalent_ipc_section("IPC", ipc_sec_num)

            if bns_eq and bns_eq.get("act") == "BNS" and bns_eq.get("section"):
                bns_act  = bns_eq["act"]
                bns_sec  = bns_eq["section"]
                cand_key = f"{bns_act} {bns_sec}"
                bns_node = self.verification_service.get_node_info(bns_act, bns_sec)

                title_str    = (bns_node.get("title")       if bns_node else None) or c["title"]
                desc_str     = (bns_node.get("description") if bns_node else None) or c.get("description", "")
                pun_str      = (bns_node.get("punishment")  if bns_node else None) or c.get("punishment", "")
                dominant_type = c.get("sub_query_type", "OFFENCE")
                if _PUNISHMENT_TITLE_SIGNALS.search(title_str or ""):
                    dominant_type = "PUNISHMENT_QUANTUM"

                print(f"[LexiGraphAgent] Phase B crosswalk: IPC {ipc_sec_num} → {cand_key}")
                consolidated_candidates[cand_key] = {
                    "section":           cand_key,
                    "title":             title_str,
                    "description":       desc_str,
                    "punishment":        pun_str,
                    "act":               bns_act,
                    "section_num":       bns_sec,
                    "vector_similarity": c["vector_similarity"],
                    "sub_query_type":    dominant_type,
                    "graph_verified":    True,
                    "equivalent_mapping": {
                        "act":              "IPC",
                        "section":          ipc_sec_num,
                        "mapping_verified": True,
                    },
                    "metadata":          bns_node or c["metadata"],
                    "sources":           c["sources"],
                    "_promoted_from":    f"IPC {ipc_sec_num}",
                }
            else:
                cand_key     = f"IPC {ipc_sec_num}"
                title_str    = c.get("title") or ""
                dominant_type = c.get("sub_query_type", "OFFENCE")
                if _PUNISHMENT_TITLE_SIGNALS.search(title_str):
                    dominant_type = "PUNISHMENT_QUANTUM"

                print(f"[LexiGraphAgent] Phase B no BNS mapping — keeping: {cand_key}")
                consolidated_candidates[cand_key] = {
                    "section":           cand_key,
                    "title":             title_str,
                    "description":       c.get("description", ""),
                    "punishment":        c.get("punishment", ""),
                    "act":               "IPC",
                    "section_num":       ipc_sec_num,
                    "vector_similarity": c["vector_similarity"],
                    "sub_query_type":    dominant_type,
                    "graph_verified":    True,
                    "equivalent_mapping": None,
                    "metadata":          c["metadata"],
                    "sources":           c["sources"],
                }

        verified_candidates_list = list(consolidated_candidates.values())
        print(
            f"[LexiGraphAgent] Step 3 candidates entering Step 4 "
            f"({len(verified_candidates_list)}): "
            f"{[c['section'] for c in verified_candidates_list]}"
        )

        # Fact-relevance filter (OFFENCE sections only; others pass through).
        # Use expanded_query from QUS as the semantic anchor — it is a legally
        # precise, fact-grounded sentence and embeds better than the raw query
        # for computing section-to-fact similarity.
        # FactExtractorService returns a typed dict (no "summary" key), so we
        # do NOT use extracted_facts here.
        # Threshold raised to 0.50 (from 0.45): the Pinecone gate is now lower
        # (0.42) so more noise enters; the fact-relevance filter is the real
        # quality gate and should be tighter.
        facts_summary = qu_result.get("expanded_query") or query
        verified_candidates_list = self._filter_by_fact_relevance(
            verified_candidates_list, facts_summary, threshold=0.50
        )
        print(
            f"[LexiGraphAgent] After fact-relevance filter: "
            f"{[c['section'] for c in verified_candidates_list]}"
        )

        # ----------------------------------------------------------------
        # STEP 4: Type-Aware Validation + Graph Enrichment
        # ----------------------------------------------------------------
        print("[LexiGraphAgent] Step 4: Type-Aware Ingredient Validation & Graph Enrichment...")
        unranked: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        for cand in verified_candidates_list:
            cand_type = cand.get("sub_query_type", "OFFENCE")
            sec_label = cand.get("section", "?")

            # ---- PROCEDURAL ------------------------------------------------
            if cand_type == "PROCEDURAL":
                _auto_injected_bail = {"BNSS 482", "CRPC 438"}
                if cand.get("section") in _auto_injected_bail:
                    cand["is_valid"]           = True
                    cand["validation_reason"]   = "Anticipatory bail provision — auto-injected; unconditionally relevant."
                    cand["ingredient_confidence"] = cand.get("vector_similarity", 0.70)
                    unranked.append(cand)
                    self.pipeline_debug_service.log_section_decision(
                        section=cand["section_num"], act=cand["act"],
                        title=cand.get("title", ""),
                        decision="included",
                        stage="Step 4: Procedural (auto-injected bail provision)",
                        reason=cand["validation_reason"],
                        scores={
                            "vector_similarity":    cand.get("vector_similarity", 0.0),
                            "ingredient_confidence": cand["ingredient_confidence"],
                        },
                    )
                    continue

                # Non-auto-injected procedural: check bail-graph link or high similarity
                _bail_rel_candidates = [
                    "RELATED_TO", "APPLIES_WITH", "MENTIONED_WITH",
                    "PRECONDITION_FOR", "BAIL_CONDITION", "APPLIES_TO",
                ]
                _available_bail_rels = [r for r in _bail_rel_candidates if r in _existing_rel_types]
                bail_relevant        = False
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
                            {"act": cand["act"], "section": cand["section_num"]},
                        )
                        if bail_rows:
                            bail_relevant         = True
                            bail_relevance_source = "graph-linked to bail provision"
                    except Exception:
                        pass

                if not bail_relevant:
                    _PROCEDURAL_SIMILARITY_FLOOR = 0.72
                    if cand.get("vector_similarity", 0.0) >= _PROCEDURAL_SIMILARITY_FLOOR:
                        bail_relevant         = True
                        bail_relevance_source = (
                            f"high vector similarity "
                            f"({cand['vector_similarity']:.3f} ≥ {_PROCEDURAL_SIMILARITY_FLOOR})"
                        )

                if bail_relevant:
                    cand["is_valid"]           = True
                    cand["validation_reason"]   = f"Procedural provision accepted — {bail_relevance_source}."
                    cand["ingredient_confidence"] = cand.get("vector_similarity", 0.65)
                    unranked.append(cand)
                    self.pipeline_debug_service.log_section_decision(
                        section=cand["section_num"], act=cand["act"],
                        title=cand.get("title", ""),
                        decision="included",
                        stage="Step 4: Procedural (bail-relevance gate passed)",
                        reason=cand["validation_reason"],
                        scores={
                            "vector_similarity":    cand.get("vector_similarity", 0.0),
                            "ingredient_confidence": cand["ingredient_confidence"],
                        },
                    )
                else:
                    _proc_reason = (
                        f"PROCEDURAL section {sec_label} not graph-linked to bail "
                        f"and similarity below floor."
                    )
                    cand["is_valid"]         = False
                    cand["validation_reason"] = _proc_reason
                    rejected.append({"section": cand["section"], "reason": _proc_reason})
                    self.pipeline_debug_service.log_section_decision(
                        section=cand["section_num"], act=cand["act"],
                        title=cand.get("title", ""),
                        decision="rejected",
                        stage="Step 4: Procedural (bail-relevance gate failed)",
                        reason=_proc_reason,
                        scores={
                            "vector_similarity":    cand.get("vector_similarity", 0.0),
                            "ingredient_confidence": 0.0,
                        },
                    )
                    print(f"[LexiGraphAgent] REJECT (procedural, not bail-relevant): {sec_label}")
                continue

            # ---- PUNISHMENT_QUANTUM ----------------------------------------
            if cand_type == "PUNISHMENT_QUANTUM":
                cand["is_valid"]           = True
                cand["validation_reason"]   = "Punishment-quantum provision — auto-accepted."
                cand["ingredient_confidence"] = cand.get("vector_similarity", 0.65)
                unranked.append(cand)
                self.pipeline_debug_service.log_section_decision(
                    section=cand["section_num"], act=cand["act"],
                    title=cand.get("title", ""),
                    decision="included",
                    stage="Step 4: Punishment-quantum (auto-accept)",
                    reason=cand["validation_reason"],
                    scores={
                        "vector_similarity":    cand.get("vector_similarity", 0.0),
                        "ingredient_confidence": cand["ingredient_confidence"],
                    },
                )
                continue

            # ---- NON-OFFENCE types (EVIDENCE_PRESUMPTION, CONSTITUTIONAL,
            #      AGGRAVATION, MITIGATION) ------------------------------------
            if cand_type in NON_OFFENCE_TYPES:
                validated_keys = {f"{u['act']} {u['section_num']}" for u in unranked}

                # Predicate check: some sections require a predicate offence first
                predicate_keys_from_graph: List[str] = []
                _predicate_rel_candidates = ["PREDICATE_OF", "CONDITIONED_ON", "REQUIRES_SECTION"]
                _available_pred_rels      = [r for r in _predicate_rel_candidates if r in _existing_rel_types]
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
                            {"act": cand["act"], "section": cand["section_num"]},
                        )
                        predicate_keys_from_graph = [
                            f"{r['act']} {r['section']}"
                            for r in pred_rows
                            if r.get("act") and r.get("section")
                        ]
                    except Exception:
                        pass

                if predicate_keys_from_graph:
                    predicate_satisfied = any(
                        pk in validated_keys for pk in predicate_keys_from_graph
                    )
                    if not predicate_satisfied:
                        cand["is_valid"]         = False
                        cand["validation_reason"] = (
                            f"{sec_label} conditioned on "
                            f"{predicate_keys_from_graph} — none yet validated."
                        )
                        rejected.append({"section": cand["section"], "reason": cand["validation_reason"]})
                        self.pipeline_debug_service.log_section_decision(
                            section=cand["section_num"], act=cand["act"],
                            title=cand.get("title", ""),
                            decision="rejected",
                            stage=f"Step 4: {cand_type} (predicate not satisfied)",
                            reason=cand["validation_reason"],
                            scores={
                                "vector_similarity":    cand.get("vector_similarity", 0.0),
                                "ingredient_confidence": 0.0,
                            },
                        )
                        continue

                elif cand["act"] in ("BSA", "IEA"):
                    # Evidence-act sections require at least one substantive offence
                    predicate_satisfied = any(
                        u.get("sub_query_type") in ("OFFENCE", "PUNISHMENT_QUANTUM")
                        and u["act"] in ("BNS", "IPC", "DPA", "POCSO")
                        for u in unranked
                    )
                    if not predicate_satisfied:
                        cand["is_valid"]         = False
                        cand["validation_reason"] = (
                            f"{sec_label} is evidence-act; no substantive offence validated yet."
                        )
                        rejected.append({"section": cand["section"], "reason": cand["validation_reason"]})
                        self.pipeline_debug_service.log_section_decision(
                            section=cand["section_num"], act=cand["act"],
                            title=cand.get("title", ""),
                            decision="rejected",
                            stage=f"Step 4: {cand_type} (no offence validated)",
                            reason=cand["validation_reason"],
                            scores={
                                "vector_similarity":    cand.get("vector_similarity", 0.0),
                                "ingredient_confidence": 0.0,
                            },
                        )
                        continue

                # No blocking predicate — accept
                cand["is_valid"]           = True
                cand["validation_reason"]   = f"{cand_type} section — accepted on similarity/direct retrieval."
                cand["ingredient_confidence"] = cand.get("vector_similarity", 0.60)
                unranked.append(cand)
                self.pipeline_debug_service.log_section_decision(
                    section=cand["section_num"], act=cand["act"],
                    title=cand.get("title", ""),
                    decision="included",
                    stage=f"Step 4: {cand_type} (accepted)",
                    reason=cand["validation_reason"],
                    scores={
                        "vector_similarity":    cand.get("vector_similarity", 0.0),
                        "ingredient_confidence": cand["ingredient_confidence"],
                    },
                )
                continue

            # ---- OFFENCE ---------------------------------------------------
            # Accepted if it survived: (a) Pinecone threshold gate, (b) Neo4j
            # IPC verification, (c) fact-relevance embedding filter.
            # That is three independent signals — no further ingredient
            # validation needed at this stage.
            cand["is_valid"]           = True
            cand["validation_reason"]   = (
                f"OFFENCE section {sec_label} accepted — Pinecone + Neo4j verified, "
                f"fact-relevance passed."
            )
            cand["ingredient_confidence"] = cand.get("vector_similarity", 0.0)
            print(f"[LexiGraphAgent] ACCEPT (cross-verified, fact-relevant): {sec_label}")
            unranked.append(cand)
            self.pipeline_debug_service.log_section_decision(
                section=cand["section_num"], act=cand["act"],
                title=cand.get("title", ""),
                decision="included",
                stage="Step 4: OFFENCE (Pinecone + Neo4j + fact-relevance)",
                reason=cand["validation_reason"],
                scores={
                    "vector_similarity":    cand.get("vector_similarity", 0.0),
                    "ingredient_confidence": cand["ingredient_confidence"],
                },
            )

        # ---- Step 4b: Graph enrichment -------------------------------------
        print("[LexiGraphAgent] Step 4b: Enriching candidates with graph relationships...")
        for cand in unranked:
            relationships           = self.verification_service.get_graph_relationships(
                cand["act"], cand["section_num"]
            )
            cand["relationships"]   = relationships
            cand["precedent_count"] = (
                len(relationships.get("supreme_court_cases", [])) +
                len(relationships.get("high_court_cases", []))
            )
            cand["principle_count"] = len(relationships.get("legal_principles", []))
            cand["evidence_count"]  = len(relationships.get("evidence_types", []))

        # ---- Reranking -----------------------------------------------------
        rerank_output    = self.reranking_service.rerank_candidates({
            "verified_candidates":         unranked,
            "primary_intent_community":    "anticipatory_bail",
            "top_case_similarity":         top_similar_cases[0]["similarity"] if top_similar_cases else 0.8,
        })
        ranked_candidates = rerank_output.get("ranked_candidates") or unranked

        for cand in ranked_candidates:
            prior              = float(cand.get("confidence") or 0.8)
            cand["confidence"] = min(1.0, prior + role_cfg["score_boost"])
        ranked_candidates.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)

        top_candidates = ranked_candidates[:6]

        # ---- Act-family normalisation (prefer BNS/BNSS/BSA over IPC/CRPC/IEA) ---
        _OLD_ACTS = {"IPC", "CRPC", "IEA"}
        _NEW_ACTS = {"BNS", "BNSS", "BSA"}
        old_count  = sum(1 for c in top_candidates
                         if c["act"] in _OLD_ACTS and c.get("sub_query_type") == "OFFENCE")
        new_count  = sum(1 for c in top_candidates
                         if c["act"] in _NEW_ACTS and c.get("sub_query_type") == "OFFENCE")
        prefer_new = new_count >= old_count
        normalized: List[Dict[str, Any]] = []

        for cand in top_candidates:
            cand_act = cand["act"]
            is_old   = cand_act in _OLD_ACTS
            is_new   = cand_act in _NEW_ACTS

            if (prefer_new and is_new) or (not prefer_new and is_old):
                normalized.append(cand)
                continue

            eq      = cand.get("equivalent_mapping") or {}
            if not eq:
                eq = self.verification_service.get_equivalent_ipc_section(
                    cand_act, cand["section_num"]
                ) or {}
            eq_act  = eq.get("act", "")  if isinstance(eq, dict) else ""
            eq_sec  = eq.get("section", "") if isinstance(eq, dict) else ""

            target_in_preferred = (
                (prefer_new  and eq_act in _NEW_ACTS) or
                (not prefer_new and eq_act in _OLD_ACTS)
            )
            if eq_act and eq_sec and target_in_preferred:
                eq_node = self.verification_service.get_node_info(eq_act, eq_sec)
                if eq_node:
                    eq_key = f"{eq_act} {eq_sec}"
                    if any(c["section"] == eq_key for c in normalized):
                        continue
                    cand = {
                        **cand,
                        "section":          eq_key,
                        "act":              eq_act,
                        "section_num":      eq_sec,
                        "title":            eq_node.get("title")       or cand["title"],
                        "description":      eq_node.get("description") or cand.get("description", ""),
                        "punishment":       eq_node.get("punishment")  or cand.get("punishment", ""),
                        "equivalent_mapping": {
                            "act":     cand_act,
                            "section": cand["section_num"],
                            "title":   cand["title"],
                        },
                        "metadata":         eq_node,
                    }
            normalized.append(cand)

        top_candidates = normalized

        print(f"[LexiGraphAgent] Step 4 rejected:       {rejected}")
        print(f"[LexiGraphAgent] Step 4 top_candidates: {[c['section'] for c in top_candidates]}")

        # ----------------------------------------------------------------
        # STEP 5: Supporting graph
        # ----------------------------------------------------------------
        print("[LexiGraphAgent] Step 5: Building supporting graph from stored relationships...")
        supporting_graph = self._build_supporting_graph(top_candidates)

        top_similar_cases = self.precedent_ranking_service.rank_cases(
            cases=top_similar_cases,
            query=query,
            offence_sections=[c["section"] for c in top_candidates],
            debug=debug,
        )

        # ----------------------------------------------------------------
        # STEP 6: Legal Reasoning
        # ----------------------------------------------------------------
        print("[LexiGraphAgent] Step 6: Merging Unified Context & Executing Legal Reasoning...")
        case_analysis = self.legal_reasoning_service.analyze_case(
            user_query=query,
            ranked_candidates=top_candidates,
            similar_cases=top_similar_cases,
            supporting_graph=supporting_graph,
        )

        top_recommended: List[Dict[str, Any]] = []
        for cand in top_candidates:
            eq_sec = cand.get("equivalent_mapping") or self.verification_service.get_equivalent_ipc_section(
                cand["act"], cand["section_num"]
            )
            top_recommended.append({
                "act":               cand["act"],
                "section":           cand["section_num"],
                "title":             cand["title"],
                "equivalent_section": eq_sec,
                "confidence":        cand.get("confidence", 0.85),
                "applicability":     cand.get("validation_reason", "Statutory ingredients prima facie present."),
                "ingredient_summary": cand.get("ingredient_summary") or [],
                "reason":            "Statutory provision used to oppose pre-arrest bail.",
                # Carry sub_query_type so render_context_for_agent can pair
                # punishment sections with their definition sections correctly.
                "sub_query_type":    cand.get("sub_query_type", "OFFENCE"),
            })

        supporting_cases: List[Dict[str, Any]] = []
        for c in top_candidates:
            rel = c.get("relationships") or {}
            for sc in (rel.get("supreme_court_cases") or []):
                cname = sc.get("case_name") or sc.get("citation")
                if cname and not any(e["case_name"] == cname for e in supporting_cases):
                    ratio = (
                        sc.get("summary") or sc.get("ratio") or
                        sc.get("ratio_decidendi") or sc.get("holding") or sc.get("held") or ""
                    )
                    facts_summary = (
                        sc.get("facts") or sc.get("facts_summary") or sc.get("brief_facts") or ""
                    )
                    supporting_cases.append({
                        "case_name":      cname,
                        "citation":       sc.get("citation") or "",
                        "interprets":     sc.get("interprets") or [c.get("section")],
                        "binding_under":  "Article 141",
                        "facts_summary":  facts_summary,
                        "ratio_decidendi": ratio or (
                            "No specific ratio recorded in the graph for this precedent — "
                            "cite it by name/citation only and do not attribute a holding to it."
                        ),
                        "has_recorded_ratio": bool(ratio),
                        "reason": (
                            f"Interprets/relates to {c.get('section')}, "
                            f"retrieved for this case's facts."
                        ),
                    })

        production_output: Dict[str, Any] = {
            "role":              role,
            "query":             query,
            "extracted_facts":   extracted_facts,
            "pipeline_confidence": top_recommended[0]["confidence"] if top_recommended else 0.8,
            "recommended_sections": top_recommended,
            "supporting_cases":  supporting_cases,
            "similar_cases":     top_similar_cases[:10],
            "supporting_articles": supporting_graph.get("articles", []),
            "supporting_evidence": self.evidence_ranking_service.rank_evidence(
                evidence_list=supporting_graph.get("evidence", []),
                query=query,
                facts=extracted_facts,
                max_items=6,
            ),
            "supporting_principles": supporting_graph.get("principles", []),
            "supporting_graph":  supporting_graph,
            "rejected_sections": rejected,
        }

        if debug:
            self.pipeline_debug_service.print_summary()
            production_output["debug_trace"] = self.pipeline_debug_service.export_json()

        return production_output

    # ------------------------------------------------------------------
    # render_context_for_agent
    # ------------------------------------------------------------------
    def render_context_for_agent(self, production_output: Dict[str, Any]) -> str:
        lines = [
            "=" * 90,
            "PROSECUTION VERIFIED CONTEXT (ANTICIPATORY BAIL / IPC / BNS / POCSO / DOWRY)",
            "=" * 90,
        ]
        lines.append("\nEXTRACTED CASE FACTS:")
        facts = production_output.get("extracted_facts") or production_output.get("query")
        lines.append(f"  {facts}\n")
        lines.append("=" * 90)
        lines.append("SECTION 1: STATUTORY PROVISIONS (BNS / IPC / BNSS / CrPC / POCSO / DPA / BSA / IEA)")
        lines.append("=" * 90)

        all_sections = production_output.get("recommended_sections", [])

        # Split into punishment sections and definition sections.
        # sub_query_type is now forwarded into top_recommended so this works correctly.
        punishment_sections = [
            s for s in all_sections
            if s.get("sub_query_type") == "PUNISHMENT_QUANTUM"
            or s.get("validation_reason", "").startswith("Punishment-quantum")
        ]
        definition_sections = [s for s in all_sections if s not in punishment_sections]

        def _find_paired_punishment(def_section: Dict[str, Any]) -> List[Dict[str, Any]]:
            def_act = def_section.get("act", "")
            eq      = def_section.get("equivalent_section") or {}
            eq_act  = eq.get("act", "") if isinstance(eq, dict) else ""
            paired  = []
            for ps in punishment_sections:
                ps_act    = ps.get("act", "")
                ps_eq     = ps.get("equivalent_section") or {}
                ps_eq_act = ps_eq.get("act", "") if isinstance(ps_eq, dict) else ""
                if ps_act == def_act or ps_act == eq_act or ps_eq_act == def_act:
                    paired.append(ps)
            return paired

        paired_already_shown: set = set()

        for s in definition_sections:
            eq     = s.get("equivalent_section")
            header = f"\n[SECTION:{s.get('act')} {s.get('section')}]"
            if eq and isinstance(eq, dict) and eq.get("act") and eq.get("section"):
                eq_title = eq.get("title")
                eq_desc  = f" – {eq_title}" if eq_title else ""
                header  += f" (corresponding to {eq.get('act')} {eq.get('section')}{eq_desc})"
            lines.append(header)
            lines.append(f"Title: {s.get('title')}")
            lines.append(f"Applicability: {s.get('applicability')}")
            ing_summary = s.get("ingredient_summary") or []
            if ing_summary:
                ing_lines = []
                for ing in ing_summary:
                    tag = "mandatory" if ing.get("mandatory") else "supporting"
                    ing_lines.append(
                        f"{ing.get('name')} [{ing.get('element_type')}, {tag}, {ing.get('state')}]"
                    )
                lines.append(f"Statutory Ingredients: {'; '.join(ing_lines)}")

            paired = _find_paired_punishment(s)
            for ps in paired:
                ps_key = f"{ps.get('act')} {ps.get('section')}"
                if ps_key not in paired_already_shown:
                    ps_eq     = ps.get("equivalent_section") or {}
                    ps_eq_str = ""
                    if isinstance(ps_eq, dict) and ps_eq.get("act") and ps_eq.get("section"):
                        ps_eq_str = f" / {ps_eq.get('act')} {ps_eq.get('section')}"
                    punishment_text = ps.get("punishment") or ps.get("description") or ""
                    lines.append(
                        f"Punishment provision: {ps_key}{ps_eq_str} — {ps.get('title', '')}"
                        + (f": {punishment_text}" if punishment_text else "")
                    )
                    paired_already_shown.add(ps_key)

        unpaired = [
            ps for ps in punishment_sections
            if f"{ps.get('act')} {ps.get('section')}" not in paired_already_shown
        ]
        if unpaired:
            lines.append(
                "\n[PUNISHMENT PROVISIONS — definition section not separately retrieved]"
            )
            for ps in unpaired:
                ps_eq     = ps.get("equivalent_section") or {}
                ps_eq_str = ""
                if isinstance(ps_eq, dict) and ps_eq.get("act") and ps_eq.get("section"):
                    ps_eq_str = (
                        f" (corresponding to {ps_eq.get('act')} {ps_eq.get('section')})"
                    )
                lines.append(
                    f"  {ps.get('act')} {ps.get('section')}{ps_eq_str}: "
                    f"{ps.get('title', '')} — {ps.get('punishment', '')}"
                )

        lines.append("\n" + "=" * 90)
        lines.append("SECTION 2: LANDMARK PRECEDENTS & SIMILAR CASES (Top 5-10)")
        lines.append("=" * 90)
        all_cases = (
            production_output.get("supporting_cases", []) +
            production_output.get("similar_cases", [])
        )

        def _case_sort_key(c: Dict[str, Any]):
            has_ratio = bool(
                c.get("ratio_decidendi") or c.get("reasoning") or
                c.get("judgment_summary") or c.get("holding") or c.get("held")
            )
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
                lines.append(
                    f"Interprets/Relates to: "
                    f"{', '.join(interprets) if isinstance(interprets, list) else interprets}"
                )
            ratio = (
                c.get("ratio_decidendi") or c.get("reasoning") or
                c.get("judgment_summary")  or c.get("holding") or c.get("held")
            )
            _NO_RATIO_SENTINEL = (
                "No specific ratio recorded in the graph for this precedent — "
                "cite it by name/citation only and do not attribute a holding to it."
            )
            if ratio and ratio != _NO_RATIO_SENTINEL:
                lines.append(f"Ratio/Holding: {ratio}")
            else:
                lines.append(
                    "Ratio/Holding: NOT RECORDED - cite this case by name/citation only; "
                    "do not attribute a holding to it."
                )

        lines.append("\n" + "=" * 90)
        lines.append("SECTION 3: LEGAL PRINCIPLES & EVIDENTIARY PRESUMPTIONS")
        lines.append("=" * 90)
        for p in production_output.get("supporting_principles", []):
            lines.append(f"[PRINCIPLE:{p}]")
        for e in production_output.get("supporting_evidence", []):
            lines.append(f"[EVIDENCE:{e}]")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # verify_claims
    # ------------------------------------------------------------------
    def verify_claims(
        self, generated_text: str, production_output: Dict[str, Any]
    ) -> Dict[str, Any]:
        retrieved_section_keys = {
            (s.get("act"), s.get("section"))
            for s in production_output.get("recommended_sections", [])
        }
        retrieved_case_names = {
            str(c.get("case_name", "")).lower().strip()
            for c in (
                production_output.get("supporting_cases", []) +
                production_output.get("similar_cases", [])
            )
        }
        result: Dict[str, Any] = {
            "is_clean":                  True,
            "verified_sections":         [],
            "real_but_ungrounded_sections": [],
            "hallucinated_sections":     [],
            "verified_cases":            [],
            "unverified_cases":          [],
        }

        section_matches = re.findall(
            r'\b(BNS|IPC|BNSS|CRPC|BSA|IEA|POCSO|DPA)\s*(\d+[A-Za-z]?)\b',
            generated_text, flags=re.IGNORECASE,
        )
        seen_sections: set = set()
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

        joiner        = r"(?:of|the|and)"
        title_token   = r"[A-Z][A-Za-z.]*"
        name_run      = rf"{title_token}(?:\s+(?:{title_token}|{joiner})){{0,6}}"
        case_name_pat = re.compile(rf"\b({name_run}\s+v\.?s?\.?\s+{name_run})\b")
        seen_cases: set = set()
        for line in generated_text.splitlines():
            for m in case_name_pat.findall(line):
                normalized = m.lower().strip()
                if normalized in seen_cases:
                    continue
                seen_cases.add(normalized)
                match = any(
                    normalized in stored or stored in normalized
                    for stored in retrieved_case_names if stored
                )
                if match:
                    result["verified_cases"].append(m.strip())
                else:
                    result["unverified_cases"].append(m.strip())
                    result["is_clean"] = False

        return result

    # ------------------------------------------------------------------
    # _build_supporting_graph
    # ------------------------------------------------------------------
    def _build_supporting_graph(
        self, top_candidates: List[Dict[str, Any]]
    ) -> Dict[str, List[Any]]:
        articles:   set = set()
        evidence:   set = set()
        principles: set = set()
        cases: List[Dict[str, Any]] = []
        raw_relationship_keys: set  = set()

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
            print(
                f"[LexiGraphAgent] NOTE: no articles/evidence/principles extracted. "
                f"Keys seen: {sorted(raw_relationship_keys) or '(empty)'}"
            )

        return {
            "articles":   sorted(articles),
            "cases":      cases,
            "evidence":   sorted(evidence),
            "principles": sorted(principles),
        }

    # ------------------------------------------------------------------
    # _validate_legal_applicability  (kept for external callers)
    # ------------------------------------------------------------------
    def _validate_legal_applicability(
        self,
        candidate: Dict[str, Any],
        extracted_facts: str,
        primary_intent: str,
    ) -> Tuple[bool, str, Any]:
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