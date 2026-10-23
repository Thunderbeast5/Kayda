"""
Stage 2 Pipeline orchestrating Stage2SubQueryMappingAgent and Stage2MappingVerifierAgent.
Transforms Stage 1 LegalQueryObject into verified Stage2BatchedMappingResponse.
Caps retries at 1 max for genuine mapping failures.
"""

from typing import Any, Dict, Optional, Union
from .stage2_mapping_agent import Stage2SubQueryMappingAgent
from .stage2_verifier_agent import Stage2MappingVerifierAgent
from .batch_utils import Stage2BatchedMappingResponse
from .schemas import LegalQueryObject, Stage2VerificationResult


def build_subquery_mapping(
    query_obj: LegalQueryObject,
    retriever: Optional[Any] = None,
    nominator: Optional[Any] = None,
    top_k: int = 20,
) -> Stage2BatchedMappingResponse:
    """
    Builds Stage2BatchedMappingResponse by retrieving top candidate sections per sub-query
    using the keyword-enhanced hybrid BM25 retriever (retriever.py + ipc_keywords.json + curated.py).
    """
    from .retriever import get_retriever
    from .batch_utils import SectionMappingCandidate, SubQueryChapterMapping, Stage2BatchedMappingResponse
    
    r = retriever or get_retriever()
    sub_queries = list(getattr(query_obj, "sub_queries", []) or [])
    
    if not sub_queries:
        from .schemas import SubQueryItem
        text = " ".join(
            str(getattr(f, "verbatim_quote", "") or getattr(f, "description", "") or "")
            for f in getattr(query_obj, "factual_allegations", [])
        ).strip() or str(getattr(query_obj, "case_facts", "") or "")
        sub_queries = [SubQueryItem(id="SQ1", concept="Case Allegations", query=text)]
    
    nominations = None
    if nominator:
        try:
            nominations = nominator.run(query_obj)
        except Exception as e:
            print(f"  [Stage 2] Nomination pass skipped: {e}", flush=True)
            nominations = None

    mappings: List[SubQueryChapterMapping] = []

    for sq in sub_queries:
        sq_id = getattr(sq, "id", "SQ1")
        sq_query = getattr(sq, "query", "") or ""
        sq_concept = getattr(sq, "concept", "") or ""
        search_text = f"{sq_concept} {sq_query}".strip() or sq_query
        
        hits = r.retrieve_top_k(search_text, k=top_k, mode='hybrid')
        if not hits and sq_query:
            hits = r.retrieve_top_k(sq_query, k=top_k, mode='hybrid')
            
        cands: List[SectionMappingCandidate] = []
        chapters: List[str] = []
        sec_numbers: List[str] = []
        
        top_score = hits[0]["raw_score"] if hits and hits[0].get("raw_score", 0) > 0 else 1.0
        
        for h in hits:
            sec_num = str(h["section_number"]).strip()
            title = str(h.get("section_title") or f"Section {sec_num}")
            score_val = float(h.get("score", 0.0))
            raw_score = float(h.get("raw_score", 0.0))
            chap = str(h.get("chapter") or "")
            if chap and chap not in chapters:
                chapters.append(chap)
            sec_numbers.append(sec_num)
            
            rel = raw_score / top_score if top_score > 0 else score_val
            if rel >= 0.5:
                tier = "PRIMARY"
            elif rel >= 0.25:
                tier = "SECONDARY"
            else:
                tier = "CONDITIONAL"
                
            if nominations and isinstance(nominations, dict):
                for fam_code, nom_list in nominations.items():
                    for n in nom_list:
                        if str(n.get("section", "")).strip().upper() == sec_num.upper():
                            tier = n.get("tier", tier)
            
            cand = SectionMappingCandidate(
                section_number=sec_num,
                section_title=title,
                statute="IPC",
                candidate_type=tier,
                score=round(score_val, 4),
                score_breakdown={"bm25_hybrid": round(score_val, 4)},
                ingredients_matched=[],
                missing_facts=[],
                relevance_reasoning=f"Retrieved via hybrid keyword BM25 index (score: {round(raw_score, 3)})",
                retrieval_sources=["bm25_hybrid"],
            )
            cands.append(cand)
            
        mapping_item = SubQueryChapterMapping(
            sub_query_id=sq_id,
            sub_query_text=sq_query,
            target_parties=list(getattr(sq, "target_parties", []) or []),
            facts_extracted=list(getattr(sq, "fact_ids", []) or []),
            ingredients_matched=[],
            candidate_chapters=chapters,
            primary_candidate_sections=[c for c in cands if c.candidate_type == "PRIMARY"],
            secondary_candidate_sections=[c for c in cands if c.candidate_type == "SECONDARY"],
            conditional_candidate_sections=[c for c in cands if c.candidate_type == "CONDITIONAL"],
            not_triggered_sections=[],
            candidate_sections=sec_numbers,
            relevance_reasoning=f"Retrieved top {len(cands)} candidates via hybrid BM25 index for {sq_id}.",
        )
        mappings.append(mapping_item)
        
    return Stage2BatchedMappingResponse(mappings=mappings)


class Stage2Pipeline:
    """
    Complete Stage 2 pipeline for Sub-Query to Chapter Candidate Batched Mapping.
    Executes LegalQueryObject -> Sub-Query Hybrid BM25 Retrieval -> Verified Stage2BatchedMappingResponse.
    """

    def __init__(
        self,
        mapping_agent: Optional[Stage2SubQueryMappingAgent] = None,
        verifier_agent: Optional[Stage2MappingVerifierAgent] = None,
        max_retries: int = 1,
        nominator: Optional[Any] = None,
        use_nomination: bool = True,
    ):
        self.mapping_agent = mapping_agent or Stage2SubQueryMappingAgent()
        self.verifier_agent = verifier_agent or Stage2MappingVerifierAgent()
        self.max_retries = max_retries
        if nominator is None and use_nomination:
            from .section_nominator import SectionNominator
            nominator = SectionNominator()
        self.nominator = nominator

    def run(
        self,
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
    ) -> Stage2VerificationResult:
        """
        Runs full Stage 2 pipeline on LegalQueryObject.

        Returns:
            Stage2VerificationResult containing final verified Stage2BatchedMappingResponse and audit details.
        """
        correction_feedback = None
        current_attempt = 0

        last_mapping_resp: Optional[Stage2BatchedMappingResponse] = None
        verification_result: Optional[Stage2VerificationResult] = None

        while current_attempt <= self.max_retries:
            current_attempt += 1

            # Step 1: Batched Mapping Evaluation
            last_mapping_resp = self.mapping_agent.run(
                legal_query=legal_query,
                correction_feedback=correction_feedback,
            )

            # Step 2: Verification Audit Check
            verification_result = self.verifier_agent.verify(
                legal_query=legal_query,
                mapping_response=last_mapping_resp,
            )

            if verification_result.status == "VERIFIED":
                verification_result.batched_mapping_response = last_mapping_resp
                return verification_result

            # Step 3: Prepare feedback for single reflection retry
            if current_attempt <= self.max_retries:
                feedback_parts = [f"Attempt {current_attempt} verification failed with audit issues:"]
                for issue in verification_result.issues:
                    feedback_parts.append(f"- Target '{issue.target}': {issue.issue} | Action: {issue.feedback}")
                if verification_result.feedback:
                    feedback_parts.append(f"Summary: {verification_result.feedback}")
                correction_feedback = "\n".join(feedback_parts)

        # Fallback Policy
        if verification_result:
            verification_result.batched_mapping_response = last_mapping_resp
            return verification_result

        return Stage2VerificationResult(
            status="RETRY",
            issues=[],
            feedback="Stage 2 pipeline execution completed without verification.",
            batched_mapping_response=last_mapping_resp,
        )
