import os
from typing import Dict, Any, List
from .pinecone_service import PineconeService

class CaseRetrievalService:
    """
    CaseRetrievalService
    
    Modular precedent retrieval service for LexiGraphAgent.
    Searches Pinecone namespace `legal_cases` to retrieve top semantically similar
    Supreme Court precedent cases.
    """

    def __init__(self):
        self.pinecone_service = PineconeService()

    def retrieve_cases(
        self, emb_result: Dict[str, Any], top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Receives query embedding structure (from EmbeddingService) and queries namespace `legal_cases`.
        Returns Top 3-5 cases with metadata (case_id, title, court, year, similarity, facts, reasoning, sections, judgment_summary).
        """
        if not emb_result or not emb_result.get("embeddings"):
            return []

        try:
            raw_res = self.pinecone_service.query_index(
                input_json=emb_result,
                top_k=top_k,
                namespace="legal_cases"
            )
        except Exception as e:
            print(f"[CaseRetrievalService] Error querying Pinecone namespace 'legal_cases': {e}")
            return []

        retrieval_results = raw_res.get("retrieval_results") or []
        
        # Deduplicate matches across queries and retain highest similarity match per case
        cases_by_id: Dict[str, Dict[str, Any]] = {}

        for res in retrieval_results:
            matches = res.get("matches") or []
            for m in matches:
                cid = m.get("id") or m.get("metadata", {}).get("case_id") or ""
                score = float(m.get("score", 0.0))
                meta = m.get("metadata") or {}

                case_name = meta.get("case_name") or meta.get("title") or meta.get("case_title") or cid or "Supreme Court Judgment"
                court = meta.get("court") or "Supreme Court of India"
                year = meta.get("year") or ""
                facts = meta.get("facts") or ""
                reasoning = meta.get("reasoning") or meta.get("ratio_decidendi") or ""
                summary = meta.get("judgment_summary") or meta.get("summary") or reasoning
                
                # Pull sections for every act this agent handles, not just
                # IPC/BNS - the previous version silently dropped BNSS, CrPC,
                # IEA, BSA, POCSO, and Dowry section tags a precedent case
                # might carry (e.g. a POCSO case's `pocso_sections` metadata
                # was never read at all), which would make case<->section
                # cross-referencing incomplete for exactly the case types you
                # said you need (POCSO, Dowry).
                all_sections: List[str] = []
                for meta_key in (
                    "ipc_sections", "bns_sections", "bnss_sections", "crpc_sections",
                    "iea_sections", "bsa_sections", "pocso_sections",
                    "dpa_sections", "dowry_sections",
                ):
                    val = meta.get(meta_key) or []
                    if isinstance(val, str):
                        val = [s.strip() for s in val.split(",") if s.strip()]
                    all_sections.extend(val)

                sections = sorted(list(set(all_sections)))

                case_dict = {
                    "case_id": cid,
                    "case_name": case_name,
                    "title": case_name,
                    "court": court,
                    "year": year,
                    "similarity": round(score, 4),
                    "vector_similarity": score,
                    "facts": facts,
                    "reasoning": reasoning,
                    "judgment_summary": summary,
                    "sections": sections,
                    "metadata": meta
                }

                if cid not in cases_by_id or score > cases_by_id[cid]["vector_similarity"]:
                    cases_by_id[cid] = case_dict

        cases_list = list(cases_by_id.values())
        cases_list.sort(key=lambda x: x["vector_similarity"], reverse=True)
        return cases_list[:top_k]