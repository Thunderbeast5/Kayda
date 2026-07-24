import json
import re
from typing import Dict, Any, List

from .services.query_understanding_service import QueryUnderstandingService
from .services.query_expansion_service import QueryExpansionService
from .services.embedding_service import EmbeddingService
from .services.pinecone_service import PineconeService
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


class LexiGraphAgent:
    """
    LexiGraphAgent
    
    The final retrieval orchestration component of Kayda AI.
    Consolidates, validates, ranks, and returns the most relevant legal provisions.
    """

    def __init__(self):
        self.query_understanding_service = QueryUnderstandingService()
        self.query_expansion_service = QueryExpansionService()
        self.embedding_service = EmbeddingService()
        self.pinecone_service = PineconeService()
        self.merge_service = MergeService()
        self.verification_service = VerificationService()
        self.community_retrieval_service = CommunityRetrievalService()
        self.reranking_service = RerankingService()
        self.legal_reasoning_service = LegalReasoningService()

    def process_query(self, query: str) -> Dict[str, Any]:
        """
        Processes a user query and returns consolidated, validated, and ranked legal provisions.
        """
        user_asked_ipc = any(word in query.lower() for word in ["ipc", "indian penal code", "historical", "before bns"])

        # ── STEP 1: Query Understanding & Expansion ──────────────────────────
        print(f"\n[LexiGraphAgent] Step 1: Query Understanding & Expansion for: '{query}'")
        qu_result = self.query_understanding_service.analyze_query(query)
        qe_result = self.query_expansion_service.expand_query(qu_result)
        primary_intent = qu_result.get("primary_intent_community") or "general_offences"

        print(f"Original query: {query}")
        print(f"Expanded queries: {json.dumps(qe_result.get('search_queries'), indent=2)}")
        print(f"Primary intent community: {primary_intent}")

        # ── STEP 2: Embedding & Retrieval ──────────────────────────────────
        print("[LexiGraphAgent] Step 2: Embedding & Retrieval...")
        keywords = qu_result.get("keywords") or []
        queries_to_run = qe_result.get("search_queries") or []

        emb_result = self.embedding_service.generate_embeddings(qe_result)
        retrieval_res = self.pinecone_service.query_index(emb_result, top_k=10)
        retrieval_results = retrieval_res.get("retrieval_results") or []

        # Diagnostic output for Step 1
        print(f"Index name: {self.pinecone_service.PINECONE_INDEX_NAME if hasattr(self.pinecone_service, 'PINECONE_INDEX_NAME') else 'legal-embeddings'}")
        print("Namespace: default")
        print("\nTop Pinecone Results (Scanned across expansion queries):")
        scan_idx = 1
        for q_res in retrieval_results:
            q_text = q_res.get("query", "")
            for m in q_res.get("matches", []):
                if scan_idx <= 20:
                    meta = m.get("metadata", {})
                    t = meta.get("title") or meta.get("offense") or meta.get("name") or ""
                    sec = meta.get("section") or ""
                    print(f"  {scan_idx:02d}. Score: {m.get('score', 0.0):.4f} | ID: {m.get('id')} | Query: '{q_text}' | Title: {t} | Sec: {sec}")
                    scan_idx += 1

        merge_res = self.merge_service.merge_results(retrieval_res)
        merged_candidates = merge_res.get("merged_candidates") or []

        candidates = []
        for mc in merged_candidates:
            mid = mc["metadata"].get("id") or f"{mc['act']}_{mc['section_num']}"
            if not _is_legal_section_hit(mid, mc["metadata"]):
                continue
            
            norm_act, norm_sec_num = _normalize_section_params(mc["act"], mc["section_num"])
            
            candidates.append({
                "section": f"{norm_act} {norm_sec_num}",
                "act": norm_act,
                "section_num": norm_sec_num,
                "title": mc["metadata"].get("title") or mc["metadata"].get("offense") or "",
                "punishment": mc["metadata"].get("punishment") or "",
                "vector_similarity": mc["best_similarity"],
                "metadata": mc["metadata"],
                "sources": mc["sources"]
            })

        # ── STEP 3: Candidate Filtering ────────────────────────────────────
        print("[LexiGraphAgent] Step 3: Candidate Filtering & LexiGraph Verification...")
        filtered_candidates = self._filter_candidates_by_intent(candidates, primary_intent, query)

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

        # ── STEP 4: Category-aware Retrieval & Enrichment ──────────────────
        print("[LexiGraphAgent] Step 4: Category-aware Retrieval & Enrichment...")
        verified_candidates_list = list(consolidated_candidates.values())
        enriched_list = self.community_retrieval_service.retrieve_community_context(
            verified_candidates_list, query, primary_intent_community=primary_intent
        )

        # ── STEP 5: Community-aware Scoring & Reranking ────────────────────
        print("[LexiGraphAgent] Step 5: Community-aware Scoring & Reranking...")
        unranked_candidates = []

        for item in enriched_list:
            scoring = self.reranking_service.compute_retrieval_score(
                candidate={"title": item["title"], "punishment": item["punishment"]},
                query_keywords=keywords,
                user_query=query
            )
            keyword_match = scoring["keyword_overlap"]

            relationships = self.verification_service.get_graph_relationships(
                item["act"], item["section_num"]
            )

            unranked_candidates.append({
                "section": item["section"],
                "act": item["act"],
                "section_num": item["section_num"],
                "title": item["title"],
                "description": item.get("description") or "",
                "punishment": item.get("punishment") or "",
                "similarity": round(item["vector_similarity"], 4),
                "keyword_match": keyword_match,
                "metadata_verified": True,
                "graph_verified": item["graph_verified"],
                "sources": item["sources"],
                "relationships": relationships,
                "community": item.get("community"),
                "community_id": item.get("community_id") or item.get("community", {}).get("candidate_community_id")
            })

        rerank_output = self.reranking_service.rerank_candidates({
            "verified_candidates": unranked_candidates,
            "primary_intent_community": primary_intent
        })
        ranked_candidates = rerank_output.get("ranked_candidates") or []

        # ── STEP 6: Legal Validation ───────────────────────────────────────
        print("[LexiGraphAgent] Step 6: Legal Validation...")
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

        # ── STEP 7: Fallback Policy ─────────────────────────────────────────
        print("[LexiGraphAgent] Step 7: Fallback Policy Evaluation...")
        CONFIDENCE_THRESHOLD = 0.45

        if not validated_candidates or float(validated_candidates[0].get("confidence") or 0.0) < CONFIDENCE_THRESHOLD:
            print("[FallbackPolicy] Confidence below threshold or no valid legal sections passed validation.")
            return {
                "decision": {
                    "invoke_reasoning": False,
                    "reason": "No sufficiently relevant legal section found."
                },
                "ranked_candidates": [],
                "case_analysis": {
                    "user_query": query,
                    "message": "No sufficiently relevant legal section found.",
                    "recommended_sections": [],
                    "rejected_sections": rejected_by_validation
                }
            }

        top_candidate = validated_candidates[0]
        top_confidence = float(top_candidate.get("confidence") or 0.0)

        invoke_reasoning = True
        reason = "Confidence below threshold or verification incomplete."

        if top_confidence >= 0.92 and top_candidate.get("graph_verified"):
            invoke_reasoning = False
            reason = "High-confidence verified retrieval."

        case_analysis = None
        if invoke_reasoning:
            case_analysis = self.legal_reasoning_service.analyze_case(
                query,
                validated_candidates[:10]
            )

        return {
            "decision": {
                "invoke_reasoning": invoke_reasoning,
                "reason": reason
            },
            "ranked_candidates": validated_candidates,
            "case_analysis": case_analysis
        }

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

        # Reject non-sexual/non-bodily sections when query specifically asks about rape/sexual assault
        if "rape" in q_lower or "sexual assault" in q_lower:
            relevant_kw = ["rape", "sexual", "intercourse", "modesty", "homicide", "murder", "death", "assault", "cruelty", "abduction", "woman"]
            if not any(kw in title or kw in desc for kw in relevant_kw):
                return False, "No factual overlap with sexual/bodily assault facts."

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
