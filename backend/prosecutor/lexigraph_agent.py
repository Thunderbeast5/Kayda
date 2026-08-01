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

        # Always include anticipatory bail provisions
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
                    "vector_similarity": 0.70,   # reduced from 0.95 to prevent domination
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