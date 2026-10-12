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
    from .services.query_expansion_service import QueryExpansionService
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
    from services.query_expansion_service import QueryExpansionService
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


_PROCEDURAL_SECTIONS = {
    "438", "482", "437", "439", "480", "483",  # Anticipatory & regular bail (CrPC / BNSS)
    "167", "187",                                # Remand & custody (CrPC / BNSS)
    "27", "23",                                  # Recovery of evidence (IEA / BSA)
    "161", "164", "180", "183",                  # Police & judicial statements (CrPC / BNSS)
    "313", "351",                                # Statement of accused (CrPC / BNSS)
    "70", "71", "72", "73",                      # Warrants (CrPC / BNSS)
    "82", "83", "84", "85",                      # Proclamation & attachment (CrPC / BNSS)
    "156", "173", "190", "200", "202", "204",    # Investigation, charge-sheet, cognizance (CrPC / BNSS)
    # Substantive offences inseparable from proclamation/absconder cases
    "172", "174", "174a", "175",                 # IPC: non-compliance proclamation / disobedience of summons / absconding to avoid service
    "206", "209", "210",                         # BNS equivalents of IPC 172/174/174A/175
}

_STATUTE_CROSSWALK = {
    # CrPC <-> BNSS
    ("CRPC", "82"): ("BNSS", "84"),
    ("CRPC", "83"): ("BNSS", "85"),
    ("CRPC", "70"): ("BNSS", "72"),
    ("CRPC", "70(2)"): ("BNSS", "72(2)"),
    ("CRPC", "70(1)"): ("BNSS", "72(1)"),
    ("CRPC", "156"): ("BNSS", "175"),
    ("CRPC", "156(3)"): ("BNSS", "175(3)"),
    ("CRPC", "167"): ("BNSS", "187"),
    ("CRPC", "173"): ("BNSS", "193"),
    ("CRPC", "173(2)"): ("BNSS", "193(2)"),
    ("CRPC", "438"): ("BNSS", "482"),
    ("CRPC", "437"): ("BNSS", "480"),
    ("CRPC", "439"): ("BNSS", "483"),
    ("CRPC", "482"): ("BNSS", "528"),
    ("CRPC", "161"): ("BNSS", "180"),
    ("CRPC", "164"): ("BNSS", "183"),
    ("CRPC", "313"): ("BNSS", "351"),
    # IPC <-> BNS (substantive)
    ("IPC", "172"): ("BNS", "206"),   # Absconding to avoid service of summons
    ("IPC", "174"): ("BNS", "209"),
    ("IPC", "174A"): ("BNS", "209"),
    ("IPC", "174a"): ("BNS", "209"),   # lowercase variant
    ("IPC", "175"): ("BNS", "210"),
    ("IPC", "341"): ("BNS", "126"),
    ("IPC", "323"): ("BNS", "115"),
    ("IPC", "324"): ("BNS", "117"),
    ("IPC", "325"): ("BNS", "118"),
    ("IPC", "354"): ("BNS", "74"),
    ("IPC", "354B"): ("BNS", "76"),
    ("IPC", "379"): ("BNS", "303"),
    ("IPC", "504"): ("BNS", "352"),
    ("IPC", "506"): ("BNS", "351"),
    ("IPC", "149"): ("BNS", "190"),
    ("IPC", "420"): ("BNS", "318"),
    ("IPC", "302"): ("BNS", "103"),
    ("IPC", "307"): ("BNS", "109"),
    ("IPC", "376"): ("BNS", "64"),
    ("IPC", "498A"): ("BNS", "85"),
    # IEA <-> BSA
    ("IEA", "27"): ("BSA", "23"),
}
for (a1, s1), (a2, s2) in list(_STATUTE_CROSSWALK.items()):
    _STATUTE_CROSSWALK[(a2, s2)] = (a1, s1)


# ── Legal regime detection ───────────────────────────────────────────────────
# Cases filed before 1 July 2024 → IPC + CrPC
# Cases filed on/after 1 July 2024 → BNS + BNSS
_BNSS_CUTOFF_DATE = (2024, 7, 1)  # (year, month, day)

_YEAR_RE = re.compile(r'\b(20\d{2}|19\d{2})\b')


def _detect_legal_regime(query: str) -> str:
    """
    Infer whether the case falls under the old code (IPC + CrPC) or the new
    code (BNS + BNSS) from dates found in the query / facts text.

    Returns "IPC+CrPC" or "BNS+BNSS".
    """
    # Fast path: explicit BNS/BNSS/BSA references → new code
    if re.search(r'\b(BNS|BNSS|BSA)\b', query, re.IGNORECASE):
        # But only treat as new code if no strong old-code signal too
        if not re.search(r'\b(IPC|CrPC|IEA)\b', query, re.IGNORECASE):
            return "BNS+BNSS"

    # Look for the earliest year mentioned in the text (FIR year, case year, …)
    years = [int(m) for m in _YEAR_RE.findall(query)]
    if years:
        earliest = min(years)
        cutoff_year = _BNSS_CUTOFF_DATE[0]
        if earliest < cutoff_year:
            return "IPC+CrPC"
        # Year == cutoff year: check for a month/day hint
        # (If the filing/FIR date is before 1 July 2024 use old code.)
        # Without an explicit month we conservatively use old code for 2024.
        if earliest == cutoff_year:
            # Look for "July" or later in the text
            if re.search(r'\b(July|August|September|October|November|December)\s+2024\b', query, re.IGNORECASE):
                return "BNS+BNSS"
            return "IPC+CrPC"

    # Default: fall back to old code (most archived cases are pre-2024)
    return "IPC+CrPC"

_ACT_ALIASES = {
    "indian penal code": "IPC",
    "ipc": "IPC",
    "code of criminal procedure": "CRPC",
    "crpc": "CRPC",
    "cr.p.c.": "CRPC",
    "cr.p.c": "CRPC",
    "bharatiya nyaya sanhita": "BNS",
    "bns": "BNS",
    "bharatiya nagarik suraksha sanhita": "BNSS",
    "bnss": "BNSS",
    "indian evidence act": "IEA",
    "iea": "IEA",
    "bharatiya sakshya adhiniyam": "BSA",
    "bsa": "BSA",
    "pocso": "POCSO",
    "dpa": "DPA",
    "dowry prohibition act": "DPA",
    "prevention of witch (daain) practices act": "DAAIN",
    "daain act": "DAAIN",
    "daain": "DAAIN",
}


class LexiGraphAgent:
    """
    LexiGraphAgent - Comprehensive Retrieval Engine for Anticipatory Bail
    Handles IPC/BNS, CrPC/BNSS, IEA/BSA, POCSO, and Dowry Prohibition Act provisions.
    """

    def __init__(self):
        self.query_understanding_service = QueryUnderstandingService()
        self.query_expansion_service = QueryExpansionService()
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

        # STEP 1: Fact Extraction & Query Understanding
        print(f"\n[LexiGraphAgent] Step 1: Fact Extraction & Query Understanding...")
        extracted_facts = self.fact_extractor_service.extract_facts(query)
        qu_result = self.query_understanding_service.analyze_query(query)
        qe_result = self.query_expansion_service.expand_query(qu_result)

        # Start with the original query as the primary search
        search_queries = [query]
        # Add expansion queries from QueryExpansionService
        search_queries.extend(qe_result.get("search_queries", []))
        # Add role‑specific angles as separate queries (not concatenated)
        if role_cfg["expansion_angles"]:
            search_queries.extend(role_cfg["expansion_angles"])

        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for q in search_queries:
            q_clean = q.strip()
            if q_clean and q_clean.lower() not in seen:
                seen.add(q_clean.lower())
                deduped.append(q_clean)
        qe_result["search_queries"] = deduped

        # Citation Grounding Filter
        raw_queries = qe_result.get("search_queries") or []
        grounded_queries = []
        for sq in raw_queries:
            matches = re.findall(r'\b(BNS|IPC|BNSS|CRPC|BSA|IEA|POCSO|DPA)\s*(\d+[A-Z]?)\b', sq, flags=re.IGNORECASE)
            clean_sq = sq
            for act_raw, sec_raw in matches:
                act_norm, sec_norm = _normalize_section_params(act_raw, sec_raw)
                if not self.verification_service.get_node_info(act_norm, sec_norm):
                    clean_sq = re.sub(rf'\b{act_raw}\s*{sec_raw}\b', '', clean_sq, flags=re.IGNORECASE)
            clean_sq = re.sub(r'\s+', ' ', clean_sq).strip()
            if clean_sq:
                grounded_queries.append(clean_sq)

        qe_result["search_queries"] = grounded_queries

        self.pipeline_debug_service.log_query(
            original_query=query,
            expanded_queries=qe_result["search_queries"],
            intent=qu_result.get("primary_intent_community", ""),
            keywords=qu_result.get("keywords", [])
        )

        # STEP 2: Vector Search
        print("[LexiGraphAgent] Step 2: Vector Search (Pinecone Legal Sections + Precedents)...")
        emb_result = self.embedding_service.generate_embeddings(qe_result)

        retrieval_res = self.pinecone_service.query_index(emb_result, top_k=20, namespace="legal_sections")
        top_similar_cases = self.case_retrieval_service.retrieve_cases(emb_result, top_k=10)

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
            input_count=len(qe_result["search_queries"]),
            output_count=len(merged_candidates),
            metadata={"similar_cases_retrieved": len(top_similar_cases)}
        )

        raw_candidates = []
        for mc in merged_candidates:
            norm_act, norm_sec_num = _normalize_section_params(mc["act"], mc["section_num"])
            raw_candidates.append({
                "section": f"{norm_act} {norm_sec_num}",
                "act": norm_act,
                "section_num": norm_sec_num,
                "title": mc["metadata"].get("title") or "",
                "punishment": mc["metadata"].get("punishment") or "",
                "vector_similarity": mc["best_similarity"],
                "metadata": mc["metadata"],
                "sources": mc["sources"]
            })

        # STEP 3: Verification & Cross-Mapping
        print("[LexiGraphAgent] Step 3: Graph Verification & Code Cross-Mapping...")
        consolidated_candidates: Dict[str, Dict[str, Any]] = {}

        # Detect legal regime from query text (date-based)
        legal_regime = _detect_legal_regime(query)
        print(f"[LexiGraphAgent] Legal regime detected: {legal_regime}")

        # Always include the correct anticipatory bail provision for the regime.
        # Pre-July 1 2024 → CrPC 438 only; on/after → BNSS 482 only.
        if legal_regime == "BNS+BNSS":
            bail_provisions = [("BNSS", "482")]
        else:
            bail_provisions = [("CRPC", "438")]

        for p_act, p_sec in bail_provisions:
            node_info = self.verification_service.get_node_info(p_act, p_sec)
            if not node_info:
                # Try looking up the equivalent code as a fallback
                alt_pair = _STATUTE_CROSSWALK.get((p_act, p_sec))
                if alt_pair:
                    node_info = self.verification_service.get_node_info(alt_pair[0], alt_pair[1]) or {}
            if node_info is not None:
                key = f"{p_act} {p_sec}"
                consolidated_candidates[key] = {
                    "section": key,
                    "title": node_info.get("title", f"{p_act} Section {p_sec}"),
                    "description": node_info.get("description", ""),
                    "punishment": "",
                    "act": p_act,
                    "section_num": p_sec,
                    "vector_similarity": 0.70,
                    "graph_verified": True,
                    "metadata": node_info,
                    "sources": ["Anticipatory bail provision - the specific relief sought"],
                    "is_procedural": True,
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

        for c in filtered_candidates:
            act, sec_num = c["act"], c["section_num"]
            node_info = self.verification_service.get_node_info(act, sec_num)
            if not node_info:
                continue

            eq_result = self.verification_service.get_equivalent_ipc_section(act, sec_num)
            cand_key = f"{act} {sec_num}"
            consolidated_candidates[cand_key] = {
                "section": cand_key,
                "title": node_info.get("title", c["title"]),
                "description": node_info.get("description", ""),
                "punishment": node_info.get("punishment", ""),
                "act": act,
                "section_num": sec_num,
                "vector_similarity": c["vector_similarity"],
                "graph_verified": True,
                "equivalent_mapping": eq_result,
                "metadata": node_info,
                "sources": c["sources"]
            }

        verified_candidates_list = list(consolidated_candidates.values())
        print(f"[LexiGraphAgent] Step 3 candidates entering validation: {[c['section'] for c in verified_candidates_list]}")

        # STEP 4: Ingredient Validation + Graph Enrichment (BEFORE reranking)
        print("[LexiGraphAgent] Step 4: Ingredient Validation & Graph Enrichment...")
        unranked = []
        rejected = []
        for cand in verified_candidates_list:
            is_valid, val_reason, val_confidence = self._validate_legal_applicability(cand, extracted_facts, "anticipatory_bail")
            cand["is_valid"] = is_valid
            cand["validation_reason"] = val_reason
            if val_confidence is not None:
                cand["ingredient_confidence"] = float(val_confidence)

            if is_valid and "no ingredients ingested" in (val_reason or "").lower():
                cand["ingredient_fallback_used"] = True
                print(f"[LexiGraphAgent] NOTE: {cand.get('section')} passed via fallback (confidence={val_confidence}).")
            elif is_valid:
                cand["ingredient_summary"] = self.ingredient_validator_service.get_ingredient_summary(cand, extracted_facts)

            if is_valid:
                unranked.append(cand)
                self.pipeline_debug_service.log_section_decision(
                    section=cand["section_num"], act=cand["act"], title=cand.get("title", ""),
                    decision="included", stage="Step 4: Ingredient Validation", reason=val_reason,
                    scores={"vector_similarity": cand.get("vector_similarity", 0.0), "ingredient_confidence": val_confidence or 0.0}
                )
            else:
                rejected.append({"section": cand["section"], "reason": val_reason})
                self.pipeline_debug_service.log_section_decision(
                    section=cand["section_num"], act=cand["act"], title=cand.get("title", ""),
                    decision="rejected", stage="Step 4: Ingredient Validation", reason=val_reason,
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

        # Collect holding IDs from top candidates for panel display
        holding_ids = []
        for cand in top_candidates:
            rel = cand.get("relationships") or {}
            for sc in rel.get("supreme_court_cases") or []:
                hid = sc.get("id") or sc.get("holding_id")
                if hid and hid not in holding_ids:
                    holding_ids.append(hid)

        production_output = {
            "role": role,
            "query": query,
            "legal_regime": legal_regime,
            "extracted_facts": extracted_facts,
            "pipeline_confidence": top_recommended[0]["confidence"] if top_recommended else 0.8,
            "recommended_sections": top_recommended,
            "holding_ids": holding_ids,
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
        # (unchanged; keep as provided)
        lines = ["=" * 90, "PROSECUTION VERIFIED CONTEXT (ANTICIPATORY BAIL / IPC / BNS / POCSO / DOWRY)", "=" * 90]
        lines.append("\nEXTRACTED CASE FACTS:")
        facts = production_output.get("extracted_facts") or production_output.get("query")
        lines.append(f"  {facts}\n")
        lines.append("=" * 90)
        lines.append("SECTION 1: STATUTORY PROVISIONS (BNS / IPC / BNSS / CrPC / POCSO / DPA / BSA / IEA)")
        lines.append("=" * 90)
        for s in production_output.get("recommended_sections", []):
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
        # Allowed citations = sections referenced by recommended sections, retrieved holdings, and case facts
        allowed_section_keys = set()
        allowed_section_numbers = set(_PROCEDURAL_SECTIONS)

        # 1. Recommended sections and equivalents
        for s in production_output.get("recommended_sections", []):
            act_n, sec_n = _normalize_section_params(s.get("act", ""), s.get("section", ""))
            if sec_n:
                allowed_section_keys.add((act_n, sec_n))
                allowed_section_numbers.add(sec_n)
                allowed_section_numbers.add(sec_n.lower())
                base_m = re.match(r"^(\d+[a-zA-Z]?)", sec_n)
                if base_m:
                    allowed_section_numbers.add(base_m.group(1))
                    allowed_section_numbers.add(base_m.group(1).lower())
            eq = s.get("equivalent_section")
            if isinstance(eq, dict):
                eq_act, eq_sec = _normalize_section_params(eq.get("act", ""), eq.get("section", ""))
                if eq_sec:
                    allowed_section_keys.add((eq_act, eq_sec))
                    allowed_section_numbers.add(eq_sec)
                    allowed_section_numbers.add(eq_sec.lower())
            elif isinstance(eq, str) and eq:
                m_eq = re.search(r"\b(BNS|IPC|BNSS|CRPC|BSA|IEA)\s*(\d+[A-Za-z]?)\b", eq, flags=re.IGNORECASE)
                if m_eq:
                    eq_act, eq_sec = _normalize_section_params(m_eq.group(1), m_eq.group(2))
                    allowed_section_keys.add((eq_act, eq_sec))
                    allowed_section_numbers.add(eq_sec)

        # 2. Extract sections from case facts, query text, holdings, and case lists
        text_sources = [str(production_output.get("query", ""))]
        for f in production_output.get("extracted_facts", []):
            text_sources.append(str(f))
        for h in production_output.get("holdings", []):
            if isinstance(h, dict):
                text_sources.extend([str(h.get("principle", "")), str(h.get("conditions", "")), str(h.get("case", "")), str(h.get("applicable_sections", ""))])
            else:
                text_sources.append(str(h))
        for sc in (production_output.get("supporting_cases", []) + production_output.get("similar_cases", [])):
            if isinstance(sc, dict):
                text_sources.extend([str(sc.get("case_name", "")), str(sc.get("ratio_decidendi", "")), str(sc.get("facts_summary", ""))])
                for inter in sc.get("interprets", []):
                    text_sources.append(str(inter))

        combined_text = "\n".join(text_sources)

        # Extract structured section lists: "Sections 341, 323, 354 ... of the Indian Penal Code"
        list_pat = re.compile(
            r'Sections?\s+([0-9A-Za-z,\s\(\)/]+?)\s+(?:of\s+(?:the\s+)?)?'
            r'(Indian Penal Code|Code of Criminal Procedure|Bharatiya Nyaya Sanhita|Bharatiya Nagarik Suraksha Sanhita|Indian Evidence Act|Bharatiya Sakshya Adhiniyam|Prevention of Witch \(Daain\) Practices Act|CrPC|IPC|BNS|BNSS|IEA|BSA|POCSO|DPA|Daain Act|Daain)\b',
            re.IGNORECASE,
        )
        for m in list_pat.finditer(combined_text):
            sec_part = m.group(1)
            act_part = m.group(2).lower()
            act = _ACT_ALIASES.get(act_part, act_part.upper())
            for s in re.findall(r'\b\d+[A-Za-z]?(?:\(\d+\))?\b', sec_part):
                allowed_section_keys.add((act, s.upper()))
                allowed_section_numbers.add(s)
                allowed_section_numbers.add(s.lower())
                base_m = re.match(r"^(\d+[a-zA-Z]?)", s)
                if base_m:
                    allowed_section_numbers.add(base_m.group(1))
                    allowed_section_numbers.add(base_m.group(1).lower())

        # Extract single mentions: "CrPC 82" or "Section 82 CrPC"
        single_pat = re.compile(r'\b(BNS|IPC|BNSS|CRPC|BSA|IEA|POCSO|DPA|DAAIN)\s*(?:Sec(?:tion|\.)?|S\.)?\s*(\d+[A-Za-z]?(?:\(\d+\))?)\b', re.IGNORECASE)
        for m in single_pat.finditer(combined_text):
            a_norm, s_norm = _normalize_section_params(m.group(1), m.group(2))
            allowed_section_keys.add((a_norm, s_norm))
            allowed_section_numbers.add(s_norm)
            allowed_section_numbers.add(s_norm.lower())
            base_m = re.match(r"^(\d+[a-zA-Z]?)", s_norm)
            if base_m:
                allowed_section_numbers.add(base_m.group(1))
                allowed_section_numbers.add(base_m.group(1).lower())

        sec_act_pat = re.compile(r'\b(?:Sec(?:tion|\.)?|S\.|u/s)\s*(\d+[A-Za-z]?(?:\(\d+\))?)\s*(?:of\s+(?:the\s+)?)?(BNS|IPC|BNSS|CRPC|BSA|IEA|POCSO|DPA|DAAIN)\b', re.IGNORECASE)
        for m in sec_act_pat.finditer(combined_text):
            a_norm, s_norm = _normalize_section_params(m.group(2), m.group(1))
            allowed_section_keys.add((a_norm, s_norm))
            allowed_section_numbers.add(s_norm)
            allowed_section_numbers.add(s_norm.lower())
            base_m = re.match(r"^(\d+[a-zA-Z]?)", s_norm)
            if base_m:
                allowed_section_numbers.add(base_m.group(1))
                allowed_section_numbers.add(base_m.group(1).lower())

        # Generic Section mentions in facts/holdings: "Section 82", "Section 83"
        gen_sec_pat = re.compile(r'\b(?:Section|Sec\.|S\.)\s*(\d+[A-Za-z]?(?:\(\d+\))?)\b', re.IGNORECASE)
        for m in gen_sec_pat.finditer(combined_text):
            s_val = m.group(1)
            allowed_section_numbers.add(s_val)
            allowed_section_numbers.add(s_val.lower())
            base_m = re.match(r"^(\d+[a-zA-Z]?)", s_val)
            if base_m:
                allowed_section_numbers.add(base_m.group(1))
                allowed_section_numbers.add(base_m.group(1).lower())

        # Crosswalk mapping expansion
        for (a_in, s_in) in list(allowed_section_keys):
            eq_pair = _STATUTE_CROSSWALK.get((a_in, s_in))
            if eq_pair:
                allowed_section_keys.add(eq_pair)
                allowed_section_numbers.add(eq_pair[1])
                allowed_section_numbers.add(eq_pair[1].lower())
                base_m = re.match(r"^(\d+[a-zA-Z]?)", eq_pair[1])
                if base_m:
                    allowed_section_numbers.add(base_m.group(1))
                    allowed_section_numbers.add(base_m.group(1).lower())

        # Procedural sections crosswalk
        for p_sec in _PROCEDURAL_SECTIONS:
            allowed_section_numbers.add(p_sec)
            for act_name in ("CRPC", "BNSS", "IPC", "BNS", "IEA", "BSA"):
                allowed_section_keys.add((act_name, p_sec))

        retrieved_case_names = set()
        for c in (production_output.get("supporting_cases", []) + production_output.get("similar_cases", [])):
            cn = str(c.get("case_name", "")).lower().strip()
            if cn:
                retrieved_case_names.add(cn)
                # Also add short party names (first part before " v. ")
                parts = re.split(r'\bv\.?s?\.?\b', cn, flags=re.IGNORECASE)
                for part in parts:
                    short = part.strip().rstrip(",").strip()
                    if len(short) > 4:
                        retrieved_case_names.add(short)

        # Also include case names mentioned in holdings
        for h in production_output.get("holdings", []):
            if isinstance(h, dict):
                hcase = str(h.get("case", "")).lower().strip()
                if hcase:
                    retrieved_case_names.add(hcase)
                    parts = re.split(r'\bv\.?s?\.?\b', hcase, flags=re.IGNORECASE)
                    for part in parts:
                        short = part.strip().rstrip(",").strip()
                        if len(short) > 4:
                            retrieved_case_names.add(short)

        # Include case text within facts and query
        combined_for_cases = str(production_output.get("query", ""))
        for entry in (production_output.get("extracted_facts") or []):
            combined_for_cases += " " + str(entry)
        for m in re.finditer(r'([A-Z][A-Za-z.]*(?:\s+(?:[A-Z][A-Za-z.]*|of|the|and)){0,6}\s+v\.?s?\.?\s+[A-Z][A-Za-z.]*(?:\s+[A-Z][A-Za-z.]*){0,5})', combined_for_cases):
            retrieved_case_names.add(m.group(0).lower().strip())

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

            if key in allowed_section_keys or sec_norm in allowed_section_numbers or sec_norm.lower() in allowed_section_numbers:
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