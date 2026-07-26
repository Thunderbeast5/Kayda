import json
import re
from typing import Dict, Any, List

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

_IPC_ID_RE = re.compile(r"^IPC_\d+[A-Za-z]*$")
_BNS_ID_RE = re.compile(r"^BNS_\d+[A-Za-z]*$")
_SECTION_RE = re.compile(r"^\d+[A-Za-z]*$")


def _is_legal_section_hit(match_id: str, meta: Dict[str, Any]) -> bool:
    """Return True if the match corresponds to an IPC or BNS legal section, false for CASE/Evidence."""
    if _IPC_ID_RE.match(match_id) or _BNS_ID_RE.match(match_id):
        return True
    sec = str(meta.get("section", ""))
    return bool(sec and _SECTION_RE.match(sec))


def _normalize_section_params(act: str, section_num: str) -> tuple[str, str]:
    act = str(act or "").strip().upper()
    section_num = str(section_num or "").strip()
    
    # Replace underscores with spaces for splitting
    clean_sec = section_num.replace("_", " ")
    
    # Split by whitespace
    parts = clean_sec.split()
    if len(parts) >= 2:
        prefix = parts[0].upper()
        suffix = parts[1]
        if prefix in ("BNS", "IPC"):
            act = prefix
            section_num = suffix
        elif prefix.lower() == "section":
            section_num = suffix
    else:
        # Check if the section_num contains BNS or IPC without space (e.g. BNS80, BNS_80)
        upper_sec = section_num.upper()
        if upper_sec.startswith("BNS"):
            act = "BNS"
            section_num = upper_sec.replace("BNS", "").replace("_", "").strip()
        elif upper_sec.startswith("IPC"):
            act = "IPC"
            section_num = upper_sec.replace("IPC", "").replace("_", "").strip()
            
    # Clean any "section" keyword in section_num
    if section_num.lower().startswith("section"):
        section_num = section_num[7:].strip()
        
    # Clean any BNS or IPC prefix in section_num
    if section_num.upper().startswith("BNS"):
        section_num = section_num[3:].replace("_", "").strip()
    elif section_num.upper().startswith("IPC"):
        section_num = section_num[3:].replace("_", "").strip()
        
    # Clean any remaining underscores/whitespace
    section_num = section_num.replace("_", "").strip()
    
    # Act sanity check
    if "BNS" in act:
        act = "BNS"
    elif "IPC" in act:
        act = "IPC"
        
    return act, section_num


try:
    from config.retrieval_config import (
        PINECONE_TOP_K, FILTER_TOP_K, GRAPH_TOP_K,
        COMMUNITY_TOP_K, RERANK_TOP_K, FINAL_OUTPUT_TOP_K
    )
except ModuleNotFoundError:
    from agents.config.retrieval_config import (
        PINECONE_TOP_K, FILTER_TOP_K, GRAPH_TOP_K,
        COMMUNITY_TOP_K, RERANK_TOP_K, FINAL_OUTPUT_TOP_K
    )


class LexiGraphAgent:
    """
    LexiGraphAgent
    
    The final retrieval orchestration component of Kayda AI.
    Consolidates, validates, ranks, and returns the most relevant legal provisions using a
    hierarchical GraphRAG retrieval pipeline (Pinecone -> Candidate Filtering -> Metadata Verification
    -> Graph Enrichment -> Community Retrieval -> Scoring -> LLM Reasoning -> Top Final Output).
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

    def process_query(self, query: str, debug: bool = False) -> Dict[str, Any]:
        """
        Processes a user query and returns consolidated, validated, and ranked legal provisions
        using a hierarchical retrieval pipeline.
        Returns a lean Production JSON by default, or includes diagnostic details if debug=True.
        """
        user_asked_ipc = any(word in query.lower() for word in ["ipc", "indian penal code", "historical", "before bns"])

        # ── STEP 1: Query Understanding, Expansion & Citation Grounding Gate ──
        print(f"\n[LexiGraphAgent] Step 1: Query Understanding & Expansion for: '{query}'")
        qu_result = self.query_understanding_service.analyze_query(query)
        qe_result = self.query_expansion_service.expand_query(qu_result)
        primary_intent = qu_result.get("primary_intent_community") or "general_offences"

        # Citation Grounding Gate (Verifies & strips ungrounded section guesses before vector embedding)
        raw_queries = qe_result.get("search_queries") or []
        grounded_queries = []
        gate_checked = 0
        gate_valid = 0
        gate_stripped = 0

        for sq in raw_queries:
            matches = re.findall(r'\b(BNS|IPC)\s*(\d+[A-Z]?)\b', sq, flags=re.IGNORECASE)
            clean_sq = sq
            for act_raw, sec_raw in matches:
                gate_checked += 1
                act_norm, sec_norm = _normalize_section_params(act_raw, sec_raw)
                node_info = self.verification_service.get_node_info(act_norm, sec_norm)
                if node_info:
                    gate_valid += 1
                else:
                    gate_stripped += 1
                    clean_sq = re.sub(rf'\b{act_raw}\s*{sec_raw}\b', '', clean_sq, flags=re.IGNORECASE)
            
            clean_sq = re.sub(r'\s+', ' ', clean_sq).strip()
            if clean_sq:
                grounded_queries.append(clean_sq)

        hallucination_rate = (gate_stripped / gate_checked * 100.0) if gate_checked > 0 else 0.0
        qe_result["search_queries"] = grounded_queries

        print(f"Original query: {query}")
        print(f"Expanded queries (Grounded): {json.dumps(qe_result.get('search_queries'), indent=2)}")
        print(f"[CitationGroundingGate] Checked: {gate_checked}, Validated: {gate_valid}, Stripped Ungrounded: {gate_stripped} (Hallucination Rate: {hallucination_rate:.1f}%)")
        print(f"Primary intent community: {primary_intent}")

        # ── STEP 2: Embedding & Parallel Retrieval (Top PINECONE_TOP_K) ─────
        print(f"[LexiGraphAgent] Step 2: Embedding & Parallel Retrieval (Top {PINECONE_TOP_K})...")
        keywords = qu_result.get("keywords") or []

        emb_result = self.embedding_service.generate_embeddings(qe_result)
        
        # Statutory Laws Retrieval (Namespace: legal_sections)
        retrieval_res = self.pinecone_service.query_index(
            emb_result, top_k=PINECONE_TOP_K, namespace="legal_sections"
        )
        
        # Precedent Cases Retrieval (Namespace: legal_cases)
        top_similar_cases = self.case_retrieval_service.retrieve_cases(emb_result, top_k=5)
        top_case_sim = top_similar_cases[0]["similarity"] if top_similar_cases else 0.70

        merge_res = self.merge_service.merge_results(retrieval_res)
        merged_candidates = merge_res.get("merged_candidates") or []

        raw_candidates = []
        for mc in merged_candidates:
            mid = mc["metadata"].get("id") or f"{mc['act']}_{mc['section_num']}"
            if not _is_legal_section_hit(mid, mc["metadata"]):
                continue
            
            norm_act, norm_sec_num = _normalize_section_params(mc["act"], mc["section_num"])
            
            raw_candidates.append({
                "section": f"{norm_act} {norm_sec_num}",
                "act": norm_act,
                "section_num": norm_sec_num,
                "title": mc["metadata"].get("title") or mc["metadata"].get("offense") or "",
                "punishment": mc["metadata"].get("punishment") or "",
                "vector_similarity": mc["best_similarity"],
                "metadata": mc["metadata"],
                "sources": mc["sources"]
            })

        count_pinecone_retrieved = len(raw_candidates)

        # ── STEP 3: Candidate Filtering (Keep Top FILTER_TOP_K) ─────────────
        print(f"[LexiGraphAgent] Step 3: Candidate Filtering (Truncate to Top {FILTER_TOP_K})...")
        filtered_candidates = self._filter_candidates_by_intent(raw_candidates, primary_intent, query)
        filtered_candidates.sort(key=lambda x: float(x.get("vector_similarity") or 0.0), reverse=True)
        filtered_candidates = filtered_candidates[:FILTER_TOP_K]
        count_after_candidate_filtering = len(filtered_candidates)

        # ── STEP 4: Metadata Verification (Top FILTER_TOP_K only) ──────────
        print(f"[LexiGraphAgent] Step 4: Metadata Verification & Successor Mapping (Top {count_after_candidate_filtering})...")
        consolidated_candidates: Dict[str, Dict[str, Any]] = {}
        for c in filtered_candidates:
            act = c["act"]
            sec_num = c["section_num"]
            vector_sim = c["vector_similarity"]
            sources = c.get("sources") or []

            node_info = self.verification_service.get_node_info(act, sec_num)
            graph_verified = bool(node_info)

            node_section = node_info.get("section") or sec_num
            node_title = node_info.get("title") or c.get("title")
            node_act = node_info.get("act") or act

            if not node_section or not node_title or not node_act:
                continue

            meta_dict = {
                "section": node_section,
                "title": node_title,
                "act": node_act,
                "chapter": node_info.get("chapter") or c["metadata"].get("chapter") or "",
                "status": node_info.get("status") or c["metadata"].get("status") or "active"
            }

            mappings = self.verification_service.get_mappings(act, sec_num)
            has_mappings = len(mappings) > 0

            target_section = f"{node_act} {node_section}"
            target_act = node_act
            target_sec_num = node_section
            target_title = node_title
            target_description = node_info.get("description") or ""
            target_punishment = node_info.get("punishment") or c.get("punishment") or ""
            target_meta = meta_dict

            if node_act == "IPC" and not user_asked_ipc:
                bns_successor = None
                for m in mappings:
                    if m["equivalent_section"].startswith("BNS "):
                        bns_successor = m["equivalent_section"].replace("BNS ", "").strip()
                        break
                
                if bns_successor:
                    bns_node = self.verification_service.get_node_info("BNS", bns_successor)
                    if bns_node:
                        target_section = f"BNS {bns_successor}"
                        target_act = "BNS"
                        target_sec_num = bns_successor
                        target_title = bns_node.get("title") or ""
                        target_description = bns_node.get("description") or ""
                        target_punishment = bns_node.get("punishment") or ""
                        target_meta = {
                            "section": bns_successor,
                            "title": target_title,
                            "act": "BNS",
                            "chapter": bns_node.get("chapter") or "",
                            "status": bns_node.get("status") or "active"
                        }
                        mappings = self.verification_service.get_mappings("BNS", bns_successor)
                        has_mappings = True

            if target_section in consolidated_candidates:
                existing = consolidated_candidates[target_section]
                if vector_sim > existing["vector_similarity"]:
                    existing["vector_similarity"] = vector_sim
                existing["sources"] = sorted(list(set(existing["sources"] + sources)))
            else:
                consolidated_candidates[target_section] = {
                    "section": target_section,
                    "title": target_title,
                    "description": target_description,
                    "punishment": target_punishment,
                    "act": target_act,
                    "section_num": target_sec_num,
                    "vector_similarity": vector_sim,
                    "graph_verified": graph_verified,
                    "has_mappings": has_mappings,
                    "metadata": target_meta,
                    "mappings": mappings,
                    "sources": sources
                }

        verified_candidates_list = list(consolidated_candidates.values())
        count_after_metadata_verification = len(verified_candidates_list)

        # ── STEP 5: Graph Enrichment (Top GRAPH_TOP_K only) ────────────────
        print(f"[LexiGraphAgent] Step 5: Graph Enrichment (Top {GRAPH_TOP_K})...")
        candidates_for_graph = verified_candidates_list[:GRAPH_TOP_K]
        
        for cand in candidates_for_graph:
            relationships = self.verification_service.get_graph_relationships(
                cand["act"], cand["section_num"]
            )
            cand["relationships"] = relationships

        count_after_graph_enrichment = len(candidates_for_graph)

        # ── STEP 6: Community Retrieval (Top COMMUNITY_TOP_K only) ─────────
        print(f"[LexiGraphAgent] Step 6: Community Retrieval (Top {COMMUNITY_TOP_K})...")
        candidates_for_community = candidates_for_graph[:COMMUNITY_TOP_K]
        enriched_list = self.community_retrieval_service.retrieve_community_context(
            candidates_for_community, query, primary_intent_community=primary_intent
        )
        count_after_community_retrieval = len(enriched_list)

        # Extract single top-level community summary
        community_info = None
        if enriched_list and enriched_list[0].get("community"):
            comm_data = enriched_list[0]["community"]
            community_info = {
                "community_id": comm_data.get("community_id") or comm_data.get("candidate_community_id") or "",
                "community_name": comm_data.get("community_name") or "",
                "community_summary": comm_data.get("community_summary") or "",
                "community_score": comm_data.get("community_score", 0.0)
            }

        # ── STEP 7: Community-aware Scoring & Reranking ────────────────────
        print("[LexiGraphAgent] Step 7: Multi-Signal Scoring & Reranking (40% Sim, 20% KW, 15% Graph, 10% Comm, 10% Case, 5% Meta)...")
        unranked_candidates = []

        for item in enriched_list:
            scoring = self.reranking_service.compute_retrieval_score(
                candidate={"title": item["title"], "punishment": item["punishment"]},
                query_keywords=keywords,
                user_query=query
            )
            keyword_match = scoring["keyword_overlap"]

            unranked_candidates.append({
                "section": item["section"],
                "act": item["act"],
                "section_num": item["section_num"],
                "title": item["title"],
                "description": item.get("description") or "",
                "punishment": item.get("punishment") or "",
                "similarity": round(item["vector_similarity"], 4),
                "keyword_match": keyword_match,
                "case_similarity": top_case_sim,
                "metadata_verified": True,
                "graph_verified": item["graph_verified"],
                "sources": item["sources"],
                "relationships": item.get("relationships") or {},
                "community_id": item.get("community_id") or item.get("community", {}).get("candidate_community_id")
            })

        rerank_output = self.reranking_service.rerank_candidates({
            "verified_candidates": unranked_candidates,
            "primary_intent_community": primary_intent,
            "top_case_similarity": top_case_sim
        })
        ranked_candidates = rerank_output.get("ranked_candidates") or []

        # Legal Validation
        validated_candidates = []
        rejected_by_validation = []

        for cand in ranked_candidates:
            is_valid, val_reason = self._validate_legal_applicability(cand, query, primary_intent)
            if is_valid:
                validated_candidates.append(cand)
            else:
                cand_copy = dict(cand)
                cand_copy["rejection_reason"] = val_reason
                rejected_by_validation.append(cand_copy)
                print(f"[LegalValidation] Rejected {cand.get('section')}: {cand.get('title')} | Reason: {val_reason}")

        # Truncate to RERANK_TOP_K (Top 5)
        top_5_candidates = validated_candidates[:RERANK_TOP_K]
        count_after_community_scoring = len(top_5_candidates)

        # Aggregate Supporting Graph (Articles, Evidence, Principles)
        supporting_graph = self._build_supporting_graph(top_5_candidates, enriched_list)

        # ── STEP 8: Fallback Policy & LLM Legal Reasoning ───────────────────
        print(f"[LexiGraphAgent] Step 8: Legal Reasoning Service (Top {count_after_community_scoring} + Precedents sent to LLM)...")
        CONFIDENCE_THRESHOLD = 0.45

        if not top_5_candidates or float(top_5_candidates[0].get("confidence") or 0.0) < CONFIDENCE_THRESHOLD:
            print("[FallbackPolicy] Confidence below threshold or no valid legal sections passed validation.")
            rejected_output = [
                {"section": r.get("section", ""), "reason": r.get("rejection_reason", "Validation failed.")}
                for r in rejected_by_validation
            ]
            self._print_retrieval_stats(
                count_pinecone_retrieved,
                count_after_candidate_filtering,
                count_after_metadata_verification,
                count_after_graph_enrichment,
                count_after_community_retrieval,
                count_after_community_scoring,
                0,
                0
            )
            fallback_res = {
                "pipeline_confidence": 0.0,
                "community": community_info,
                "recommended_sections": [],
                "similar_cases": [],
                "supporting_articles": supporting_graph.get("articles", []),
                "supporting_evidence": supporting_graph.get("evidence", []),
                "supporting_principles": supporting_graph.get("principles", []),
                "supporting_graph": supporting_graph,
                "rejected_sections": rejected_output
            }
            if debug:
                fallback_res["debug"] = {
                    "decision": {
                        "invoke_reasoning": False,
                        "reason": "No sufficiently relevant legal section found."
                    },
                    "ranked_candidates": []
                }
            return fallback_res

        top_candidate = top_5_candidates[0]
        top_confidence = float(top_candidate.get("confidence") or 0.0)

        invoke_reasoning = True
        reason = "Confidence below threshold or verification incomplete."

        if top_confidence >= 0.92 and top_candidate.get("graph_verified"):
            invoke_reasoning = False
            reason = "High-confidence verified retrieval."

        case_analysis = None
        count_sent_to_llm = 0
        if invoke_reasoning:
            count_sent_to_llm = len(top_5_candidates)
            case_analysis = self.legal_reasoning_service.analyze_case(
                user_query=query,
                ranked_candidates=top_5_candidates,
                similar_cases=top_similar_cases,
                supporting_graph=supporting_graph
            )

        # ── STEP 9: Final Production Output Formatting ─────────────────────
        recommended_raw = (case_analysis.get("recommended_sections") if case_analysis else None) or [
            {
                "section": c.get("section", ""),
                "confidence": c.get("confidence", 0.0),
                "reason": f"High confidence match for {c.get('title', '')}."
            }
            for c in top_5_candidates
        ]

        top_recommended = []
        for item in recommended_raw:
            conf = float(item.get("confidence") or 0.0)
            if conf >= 0.45 or len(top_recommended) < 2:
                sec_raw = item.get("section", "")
                
                # Match candidate from top_5_candidates if possible
                matching_cand = None
                for c in top_5_candidates:
                    if (
                        c.get("section") == sec_raw
                        or f"{c.get('act')} {c.get('section_num')}" == sec_raw
                        or c.get("section_num") == sec_raw
                    ):
                        matching_cand = c
                        break

                if matching_cand:
                    act_val = matching_cand["act"]
                    sec_val = matching_cand["section_num"]
                    title_val = matching_cand["title"]
                else:
                    act_val, sec_val = _normalize_section_params("", sec_raw)
                    node_info = self.verification_service.get_node_info(act_val, sec_val)
                    title_val = node_info.get("title") or item.get("title") or ""

                eq_sec = self.verification_service.get_equivalent_ipc_section(act_val, sec_val)

                top_recommended.append({
                    "act": act_val,
                    "section": sec_val,
                    "title": title_val,
                    "equivalent_section": eq_sec,
                    "confidence": conf,
                    "applicability": item.get("applicability") or item.get("reason") or item.get("decision_reason") or "Statutory elements applicable.",
                    "reason": item.get("reason") or item.get("decision_reason") or "Statutory elements satisfied."
                })
            if len(top_recommended) >= FINAL_OUTPUT_TOP_K:
                break

        top_recommended.sort(key=lambda x: float(x.get("confidence") or 0.0), reverse=True)
        count_returned_to_user = len(top_recommended)
        pipeline_confidence = top_recommended[0]["confidence"] if top_recommended else 0.0

        # Structured Supporting Cases from Neo4j Precedent Graph Traversal
        supporting_cases = []
        for c in top_5_candidates:
            rel = c.get("relationships") or {}
            for sc in rel.get("supreme_court_cases") or []:
                cname = sc.get("case_name") or sc.get("citation")
                if cname and not any(existing["case_name"] == cname for existing in supporting_cases):
                    supporting_cases.append({
                        "case_name": cname,
                        "citation": sc.get("citation") or "",
                        "interprets": sc.get("interprets") or [c.get("section")],
                        "binding_under": sc.get("binding_under") or "Article 141",
                        "legal_principles": sc.get("legal_principles") or [],
                        "required_evidence": sc.get("required_evidence") or [],
                        "reason": sc.get("summary") or sc.get("ratio_decidendi") or f"Landmark Supreme Court precedent interpreting {c.get('section')}."
                    })

        # Similar cases fallback formatting
        formatted_similar_cases = (case_analysis.get("similar_cases") if case_analysis else None) or [
            {
                "case_name": cs.get("case_name") or cs.get("title") or "Supreme Court Judgment",
                "court": cs.get("court", "Supreme Court of India"),
                "similarity": cs.get("similarity", 0.85),
                "reasoning": cs.get("reasoning") or cs.get("facts") or "Semantically relevant Supreme Court precedent.",
                "judgment_summary": cs.get("judgment_summary") or cs.get("reasoning") or ""
            }
            for cs in top_similar_cases[:3]
        ]

        # Supporting articles, evidence, principles (Ground truth graph merged with LLM output)
        graph_arts = supporting_graph.get("articles") or []
        llm_arts = (case_analysis.get("supporting_articles") if case_analysis else None) or []
        supporting_articles = sorted(list(set(graph_arts + llm_arts)))

        graph_ev = supporting_graph.get("evidence") or []
        llm_ev = (case_analysis.get("supporting_evidence") if case_analysis else None) or []
        supporting_evidence = sorted(list(set(graph_ev + llm_ev)))

        graph_prin = supporting_graph.get("principles") or []
        llm_prin = (case_analysis.get("supporting_principles") if case_analysis else None) or []
        supporting_principles = sorted(list(set(graph_prin + llm_prin)))

        # Format Rejected Sections concisely
        rejected_sections_formatted = []
        for r in rejected_by_validation:
            rejected_sections_formatted.append({
                "section": r.get("section", ""),
                "reason": r.get("rejection_reason", "Failed legal applicability validation.")
            })
        if case_analysis and case_analysis.get("rejected_sections"):
            for r in case_analysis.get("rejected_sections"):
                if isinstance(r, dict):
                    sec_name = r.get("section", "")
                    reason = r.get("decision_reason") or r.get("reason") or "Elements unsatisfied."
                else:
                    sec_name = str(r)
                    reason = "Elements unsatisfied or lower applicability."
                if sec_name and not any(item["section"] == sec_name for item in rejected_sections_formatted):
                    rejected_sections_formatted.append({
                        "section": sec_name,
                        "reason": reason
                    })

        self._print_retrieval_stats(
            count_pinecone_retrieved,
            count_after_candidate_filtering,
            count_after_metadata_verification,
            count_after_graph_enrichment,
            count_after_community_retrieval,
            count_after_community_scoring,
            count_sent_to_llm,
            count_returned_to_user
        )

        production_output = {
            "pipeline_confidence": pipeline_confidence,
            "recommended_sections": top_recommended,
            "supporting_cases": supporting_cases,
            "similar_cases": formatted_similar_cases,
            "supporting_articles": supporting_articles,
            "supporting_evidence": supporting_evidence,
            "supporting_principles": supporting_principles,
            "supporting_graph": supporting_graph,
            "community": community_info,
            "rejected_sections": rejected_sections_formatted
        }

        if debug:
            production_output["debug"] = {
                "decision": {
                    "invoke_reasoning": invoke_reasoning,
                    "reason": reason
                },
                "ranked_candidates": top_5_candidates,
                "case_analysis": case_analysis
            }

        return production_output

    def _build_supporting_graph(self, top_candidates: List[Dict[str, Any]], enriched_list: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
        """Aggregates supporting graph context across top candidates and community context."""
        raw_articles = set()
        cases = set()
        evidence = set()
        principles = set()

        for c in top_candidates:
            rel = c.get("relationships") or {}
            for a in rel.get("constitutional_articles") or []:
                art_str = f"{a.get('article')} - {a.get('title')}" if a.get("title") else a.get("article")
                if art_str:
                    raw_articles.add(art_str)
            for cs in rel.get("supreme_court_cases") or []:
                name = cs.get("case_name") or cs.get("citation")
                if name:
                    cases.add(name)
            for cs in rel.get("high_court_cases") or []:
                name = cs.get("case_name") or cs.get("citation")
                if name:
                    cases.add(name)
            for e in rel.get("evidence_types") or []:
                name = e.get("name")
                if name:
                    evidence.add(name)
            for p in rel.get("legal_principles") or []:
                name = p.get("name")
                if name:
                    principles.add(name)

        # Deduplicate articles so detailed titles override bare numbers (e.g. "Article 21 - Protection..." overrides "Article 21")
        dedup_articles = {}
        for art in raw_articles:
            art_clean = art.strip()
            if not art_clean:
                continue
            key = art_clean.split(" - ")[0].strip()
            if key not in dedup_articles or len(art_clean) > len(dedup_articles[key]):
                dedup_articles[key] = art_clean

        return {
            "articles": sorted(list(dedup_articles.values())),
            "cases": sorted(list(cases)),
            "evidence": sorted(list(evidence)),
            "principles": sorted(list(principles))
        }

    def _print_retrieval_stats(
        self,
        pinecone: int,
        filter_cnt: int,
        verify_cnt: int,
        graph_cnt: int,
        comm_cnt: int,
        scoring_cnt: int,
        llm_cnt: int,
        user_cnt: int
    ) -> None:
        """Prints pipeline retrieval statistics log."""
        print("\n" + "=" * 80)
        print("LEXIGRAPH HIERARCHICAL RETRIEVAL STATISTICS")
        print("=" * 80)
        print(f"  Pinecone Retrieved          : {pinecone}")
        print(f"  After Candidate Filtering   : {filter_cnt}")
        print(f"  After Metadata Verification : {verify_cnt}")
        print(f"  After Graph Enrichment      : {graph_cnt}")
        print(f"  After Community Retrieval   : {comm_cnt}")
        print(f"  After Community Scoring     : {scoring_cnt}")
        print(f"  Sent to LLM                 : {llm_cnt}")
        print(f"  Returned to User            : {user_cnt}")
        print("=" * 80 + "\n")


    def _filter_candidates_by_intent(
        self, candidates: List[Dict[str, Any]], primary_intent: str, query: str
    ) -> List[Dict[str, Any]]:
        """
        Step 3: Candidate Filtering.
        Before reranking, remove candidates that belong to legally unrelated categories
        unless similarity exceeds high threshold (0.75).
        """
        unrelated_titles = [
            "illegal bid", "furnishing false information", "unlawful purchase",
            "fraudulent claim", "counterfeiting", "forgery", "public auction",
            "false statement", "cheating and dishonestly"
        ]
        
        q_lower = query.lower()
        is_women_or_body_crime = any(w in q_lower for w in ["rape", "sexual", "dowry", "married woman", "cruelty", "murder", "death", "acid", "kidnap"])

        filtered = []
        for c in candidates:
            title_lower = (c.get("title") or "").lower()
            sim = float(c.get("vector_similarity") or 0.0)

            if is_women_or_body_crime:
                if any(ut in title_lower for ut in unrelated_titles) and sim < 0.75:
                    print(f"[CandidateFiltering] Purging unrelated candidate: {c.get('section')} - {c.get('title')} (sim: {sim:.4f})")
                    continue

            filtered.append(c)
        return filtered

    def _validate_legal_applicability(
        self, candidate: Dict[str, Any], query: str, primary_intent: str
    ) -> tuple[bool, str]:
        """
        Step 6: Legal Validation.
        Question: 'Does this offence logically apply to the facts?'
        If NO -> Reject.
        """
        title = (candidate.get("title") or "").lower()
        desc = (candidate.get("description") or "").lower()
        q_lower = query.lower()

        # Reject auction/bidding/financial reporting for sexual/body crimes
        if any(w in q_lower for w in ["rape", "sexual", "dowry", "married woman", "murder", "death", "acid"]):
            if any(unrel in title for unrel in ["bid", "furnishing false", "unlawful purchase", "fraudulent claim", "coin", "currency", "forgery"]):
                return False, "No factual overlap (Financial/Property/Procedure offence applied to violent/sexual crime)."

        # Statutory Ingredient Check for Rape (BNS 63 / BNS 64):
        # Rape requires non-consensual penetration/intercourse. If query uses general 'sexually assaulted'
        # without alleging penetration, rape (BNS 63/64) elements are unverified -> Prefer BNS 355 / BNS 74 (Outraging Modesty).
        sec_str = str(candidate.get("section") or "")
        has_penetration_alleged = any(p_kw in q_lower for p_kw in ["penetrat", "intercourse", "raped", "rape"])
        if ("bns 63" in sec_str.lower() or "bns 64" in sec_str.lower() or "rape" in title) and not has_penetration_alleged:
            return False, "Statutory ingredient of Rape (penetration/intercourse) is unalleged in query. Outraging modesty (BNS 355/74) applies."

        # Dowry death validation
        if "dowry" in q_lower:
            relevant_dowry_kw = ["dowry", "cruelty", "husband", "marriage", "woman", "death", "homicide", "murder", "harm"]
            if not any(kw in title or kw in desc for kw in relevant_dowry_kw):
                return False, "No factual overlap with dowry facts."

        # Kidnapping validation
        if "kidnap" in q_lower or "abduct" in q_lower:
            relevant_kidnap_kw = ["kidnap", "abduct", "minor", "child", "guardianship", "confinement", "custody"]
            if not any(kw in title or kw in desc for kw in relevant_kidnap_kw):
                return False, "No factual overlap with kidnapping facts."

        # Acid attack validation
        if "acid" in q_lower:
            relevant_acid_kw = ["acid", "grievous hurt", "hurt", "assault", "poison", "corrosive"]
            if not any(kw in title or kw in desc for kw in relevant_acid_kw):
                return False, "No factual overlap with acid attack facts."

        return True, "Factual overlap verified."



if __name__ == "__main__":
    import sys
    agent = LexiGraphAgent()
    
    test_query = (
        "My neighbor Ramesh came into my house yesterday evening while I was away, "
        "broke open my steel almirah with a crowbar, and stole gold ornaments worth "
        "5 lakhs and 50,000 cash."
    )
    if len(sys.argv) > 1:
        test_query = sys.argv[1]
    
    print("\n" + "=" * 80)
    print("LEXIGRAPH AGENT PIPELINE RUN (CONSOLIDATED SCORING & OUTPUTS)")
    print("=" * 80)
    
    output = agent.process_query(test_query)
    print(json.dumps(output, indent=2))
