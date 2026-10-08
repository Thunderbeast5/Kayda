"""
Stage 5 Precedent Retrieval Pipeline.

Orchestrates the complete precedent retrieval workflow:
1. Deterministic statutory candidate retrieval
2. Role-specific LLM evaluation (prosecution + defense)
3. Reasoner + verifier validation
4. Ranking and output construction

Replaces the old Stage 5 (Bail Reasoning) and Stage 6 (Precedent Retrieval).
"""

from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from .precedent_retrieval import PrecedentRetriever, PrecedentCandidate
from .precedent_relevance_agent import PrecedentRelevanceBatchEvaluator
from .schemas.stage5_precedent import (
    RoleSpecificPrecedentRetrievalObject,
    PrecedentRetrievalResult,
    PrecedentRetrievalIssue,
)
from .schemas import CaseContextObject, StatutoryVerificationObject


class Stage5PrecedentPipeline:
    """
    Complete Stage 5 pipeline for Role-Specific Precedent Retrieval.
    
    Workflow:
    1. Extract statutes from Stage 4 output
    2. Retrieve candidate precedents via deterministic statutory matching
    3. Evaluate each candidate for prosecution relevance (LLM reasoner + verifier)
    4. Evaluate each candidate for defense relevance (LLM reasoner + verifier)
    5. Rank and construct final role-specific precedent lists
    6. Return RoleSpecificPrecedentRetrievalObject
    """
    
    def __init__(
        self,
        retriever: Optional[PrecedentRetriever] = None,
        evaluator: Optional[PrecedentRelevanceBatchEvaluator] = None,
        max_candidates: int = 20,
        max_prosecution_precedents: int = 10,
        max_defense_precedents: int = 10,
        tagged_dir: Optional[Path] = None
    ):
        """
        Initialize Stage 5 Precedent Pipeline.
        
        Args:
            retriever: PrecedentRetriever instance (or None to create default)
            evaluator: PrecedentRelevanceBatchEvaluator instance (or None to create default)
            max_candidates: Maximum candidates to retrieve from statutory matching
            max_prosecution_precedents: Maximum precedents to return for prosecution
            max_defense_precedents: Maximum precedents to return for defense
            tagged_dir: Directory containing tagged judgment files
        """
        self.retriever = retriever or PrecedentRetriever(
            tagged_dir=tagged_dir,
            max_candidates=max_candidates
        )
        self.evaluator = evaluator or PrecedentRelevanceBatchEvaluator()
        self.max_prosecution_precedents = max_prosecution_precedents
        self.max_defense_precedents = max_defense_precedents
    
    def _extract_case_summary(
        self,
        case_context: Union[CaseContextObject, Dict[str, Any], str]
    ) -> str:
        """Extract case summary from CaseContextObject."""
        if isinstance(case_context, str):
            return case_context
        
        if isinstance(case_context, dict):
            # Extract from dict
            case_profile = case_context.get("case_profile", {})
            facts = case_context.get("case_facts", {})
            
            summary_parts = []
            
            # Add case type and nature
            case_type = case_profile.get("case_type", "")
            dispute_nature = case_profile.get("dispute_nature", "")
            if case_type:
                summary_parts.append(f"Case Type: {case_type}")
            if dispute_nature:
                summary_parts.append(f"Dispute Nature: {dispute_nature}")
            
            # Add factual summary
            factual_summary = facts.get("factual_summary", "")
            if factual_summary:
                summary_parts.append(f"Facts: {factual_summary}")
            
            # Add allegations
            allegations = facts.get("allegations", [])
            if allegations:
                summary_parts.append(f"Allegations: {'; '.join(allegations[:3])}")
            
            return "\n".join(summary_parts) if summary_parts else "Case details not available"
        
        # CaseContextObject instance
        if hasattr(case_context, 'case_facts') and hasattr(case_context.case_facts, 'factual_summary'):
            return case_context.case_facts.factual_summary
        
        return "Case summary not available"
    
    def _extract_input_statutes(
        self,
        statutory_object: Union[StatutoryVerificationObject, Dict[str, Any], str]
    ) -> List[Dict[str, str]]:
        """
        Extract ALL input statutes from Stage 4 output.
        
        Includes:
        - IPC/BNS sections from verified_offences
        - BNSS/CrPC sections from bnss_output
        - BSA/IEA sections from bsa_output
        - Special Act sections from act_router_output
        """
        if isinstance(statutory_object, str):
            return []
        
        if isinstance(statutory_object, dict):
            statutes = []
            
            # 1. Extract IPC/BNS sections from verified_offences
            for offence in statutory_object.get("verified_offences", []):
                act = offence.get("statute", "IPC")
                section = offence.get("section_number", "")
                if section:
                    statutes.append({"act": act, "section": section})
            
            # 2. Extract BNSS/CrPC sections from bnss_output
            bnss_output = statutory_object.get("bnss_output", {})
            if bnss_output and isinstance(bnss_output, dict):
                for section_item in bnss_output.get("verified_sections", []):
                    act = section_item.get("statute", "BNSS")
                    section = section_item.get("section_number", "")
                    if section:
                        statutes.append({"act": act, "section": section})
            
            # 3. Extract BSA/IEA sections from bsa_output
            bsa_output = statutory_object.get("bsa_output", {})
            if bsa_output and isinstance(bsa_output, dict):
                for section_item in bsa_output.get("verified_sections", []):
                    act = section_item.get("statute", "BSA")
                    section = section_item.get("section_number", "")
                    if section:
                        statutes.append({"act": act, "section": section})
            
            # 4. Extract Special Act sections from act_router_output
            act_router_output = statutory_object.get("act_router_output", {})
            if act_router_output and isinstance(act_router_output, dict):
                for routing_decision in act_router_output.get("routing_decisions", []):
                    if routing_decision.get("routed", False):
                        act_name = routing_decision.get("target_act", "")
                        retrieved_sections = routing_decision.get("retrieved_sections", [])
                        for section_item in retrieved_sections:
                            section = section_item.get("section_number", "")
                            if section and act_name:
                                statutes.append({"act": act_name, "section": section})
            
            return statutes
        
        # StatutoryVerificationObject instance
        statutes = []
        
        # Extract from verified_offences
        if hasattr(statutory_object, 'verified_offences'):
            for offence in statutory_object.verified_offences:
                statutes.append({
                    "act": getattr(offence, 'statute', 'IPC'),
                    "section": offence.section_number
                })
        
        # Note: For Pydantic objects, bnss_output and bsa_output would need to be 
        # accessed if they're part of the schema. The dict path above handles the 
        # common case from the pipeline.
        
        return statutes
    
    def _convert_to_dict(
        self,
        obj: Union[Dict, Any]
    ) -> Dict[str, Any]:
        """Convert Pydantic model or dict to dict."""
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, 'model_dump'):
            return obj.model_dump()
        if hasattr(obj, 'dict'):
            return obj.dict()
        return {}
    
    def run(
        self,
        case_context: Union[CaseContextObject, Dict[str, Any], str],
        statutory_object: Union[StatutoryVerificationObject, Dict[str, Any], str],
        correction_feedback: Optional[str] = None
    ) -> PrecedentRetrievalResult:
        """
        Run complete Stage 5 precedent retrieval pipeline.
        
        Args:
            case_context: CaseContextObject from Stage 0
            statutory_object: StatutoryVerificationObject from Stage 4
            correction_feedback: Optional feedback from previous verification attempt
            
        Returns:
            PrecedentRetrievalResult with verified RoleSpecificPrecedentRetrievalObject
        """
        print("\n" + "="*80)
        print("STAGE 5: ROLE-SPECIFIC PRECEDENT RETRIEVAL PIPELINE")
        print("="*80)
        
        # Convert inputs to dicts
        statutory_dict = self._convert_to_dict(statutory_object)
        
        # Extract case summary and input statutes
        input_case_summary = self._extract_case_summary(case_context)
        input_statutes = self._extract_input_statutes(statutory_object)
        
        if not input_statutes:
            print("[Stage5] WARNING: No statutes found in Stage 4 output")
            return PrecedentRetrievalResult(
                status="VERIFIED",
                issues=[],
                feedback="No statutes found in Stage 4 output - no precedent retrieval performed",
                verified_precedent_object=RoleSpecificPrecedentRetrievalObject(
                    input_case_summary=input_case_summary,
                    input_statutes=[],
                    total_judgments_scanned=0,
                    candidates_after_statutory_match=0,
                    prosecution_precedents=[],
                    defense_precedents=[],
                    shared_precedents=[],
                    verification_status="VERIFIED"
                )
            )
        
        print(f"\n[Stage5] Input case summary: {input_case_summary[:200]}...")
        print(f"[Stage5] Input statutes: {input_statutes}")
        
        # Step 1: Deterministic statutory candidate retrieval
        print("\n" + "-"*80)
        print("STEP 1: DETERMINISTIC STATUTORY MATCHING")
        print("-"*80)
        
        candidates = self.retriever.retrieve_candidates(
            stage4_result=statutory_dict,
            case_context=self._convert_to_dict(case_context) if case_context else None
        )
        
        if not candidates:
            print("[Stage5] No precedent candidates found")
            return PrecedentRetrievalResult(
                status="VERIFIED",
                issues=[],
                feedback="No precedent candidates matched statutory criteria",
                verified_precedent_object=RoleSpecificPrecedentRetrievalObject(
                    input_case_summary=input_case_summary,
                    input_statutes=input_statutes,
                    total_judgments_scanned=len(list(self.retriever.tagged_dir.glob("tagged_*.json"))),
                    candidates_after_statutory_match=0,
                    prosecution_precedents=[],
                    defense_precedents=[],
                    shared_precedents=[],
                    verification_status="VERIFIED"
                )
            )
        
        print(f"[Stage5] Found {len(candidates)} candidates after statutory matching")
        
        # Step 2: Role-specific LLM evaluation (prosecution + defense)
        print("\n" + "-"*80)
        print("STEP 2: ROLE-SPECIFIC LLM EVALUATION")
        print("-"*80)
        
        role_evaluations = self.evaluator.evaluate_candidates_for_both_roles(
            candidates=candidates,
            input_case_summary=input_case_summary,
            input_statutes=input_statutes,
            stage4_result=statutory_dict
        )
        
        # Step 3: Build RoleSpecificPrecedentItem objects
        print("\n" + "-"*80)
        print("STEP 3: BUILDING ROLE-SPECIFIC PRECEDENT LISTS")
        print("-"*80)
        
        prosecution_items = self.evaluator.build_role_specific_precedent_items(
            role_evaluations["prosecution"]
        )[:self.max_prosecution_precedents]
        
        defense_items = self.evaluator.build_role_specific_precedent_items(
            role_evaluations["defense"]
        )[:self.max_defense_precedents]
        
        print(f"[Stage5] Prosecution precedents: {len(prosecution_items)}")
        print(f"[Stage5] Defense precedents: {len(defense_items)}")
        
        # Identify shared precedents (appearing in both lists)
        prosecution_case_ids = {item.case_id for item in prosecution_items}
        defense_case_ids = {item.case_id for item in defense_items}
        shared_precedents = list(prosecution_case_ids & defense_case_ids)
        
        if shared_precedents:
            print(f"[Stage5] Shared precedents (relevant to both sides): {len(shared_precedents)}")
        
        # Step 4: Construct final output object
        print("\n" + "-"*80)
        print("STEP 4: CONSTRUCTING OUTPUT")
        print("-"*80)
        
        precedent_object = RoleSpecificPrecedentRetrievalObject(
            input_case_summary=input_case_summary,
            input_statutes=input_statutes,
            total_judgments_scanned=len(list(self.retriever.tagged_dir.glob("tagged_*.json"))),
            candidates_after_statutory_match=len(candidates),
            prosecution_precedents=prosecution_items,
            defense_precedents=defense_items,
            shared_precedents=shared_precedents,
            verification_status="VERIFIED",
            retrieval_metadata={
                "max_candidates": self.retriever.max_candidates,
                "max_prosecution_precedents": self.max_prosecution_precedents,
                "max_defense_precedents": self.max_defense_precedents,
                "correction_feedback": correction_feedback
            }
        )
        
        # Step 5: Validation check
        issues = []
        
        if len(prosecution_items) == 0 and len(defense_items) == 0:
            issues.append(PrecedentRetrievalIssue(
                target="overall",
                issue="No relevant precedents found for either prosecution or defense",
                feedback="Consider expanding search criteria or reviewing statutory matching"
            ))
        
        # Check for verification issues from evaluations
        for role_name, role_data in [("prosecution", role_evaluations["prosecution"]),
                                      ("defense", role_evaluations["defense"])]:
            for prec_data in role_data:
                verification = prec_data.get("verification", {})
                if not verification.get("verified", True):
                    for issue_text in verification.get("issues", []):
                        issues.append(PrecedentRetrievalIssue(
                            target=f"{role_name}:{prec_data['candidate'].case_id}",
                            issue=issue_text,
                            feedback="Review and correct evaluation"
                        ))
        
        status = "VERIFIED" if len(issues) == 0 else "RETRY"
        feedback = "Precedent retrieval completed successfully" if status == "VERIFIED" else f"Found {len(issues)} issues requiring review"
        
        print(f"\n[Stage5] Pipeline status: {status}")
        print(f"[Stage5] Feedback: {feedback}")
        print("="*80 + "\n")
        
        return PrecedentRetrievalResult(
            status=status,
            issues=issues,
            feedback=feedback,
            verified_precedent_object=precedent_object
        )


def test_stage5_pipeline():
    """Test Stage 5 pipeline with sample data."""
    from .schemas import StatutoryVerificationObject
    
    print("\n" + "="*80)
    print("TESTING STAGE 5 PRECEDENT RETRIEVAL PIPELINE")
    print("="*80)
    
    # Sample Stage 4 output
    stage4_sample = StatutoryVerificationObject(
        verified_offences=[
            {
                "section_number": "498A",
                "statute": "IPC",
                "title": "Cruelty by husband or relatives of husband",
                "overall_prima_facie_strength": "Strong",
                "ingredient_evaluation": [],
                "overall_status": "Prima Facie Attracted",
                "confidence": 0.85
            },
            {
                "section_number": "406",
                "statute": "IPC",
                "title": "Criminal breach of trust",
                "overall_prima_facie_strength": "Moderate",
                "ingredient_evaluation": [],
                "overall_status": "Prima Facie Attracted",
                "confidence": 0.70
            }
        ]
    )
    
    # Sample case context
    case_summary = """Matrimonial dispute involving allegations of cruelty, dowry harassment, 
    and misappropriation of stridhan. Complainant alleges physical and mental harassment by 
    husband and in-laws. Accused seeks anticipatory bail citing false implication."""
    
    # Initialize pipeline with small limits for testing
    pipeline = Stage5PrecedentPipeline(
        max_candidates=5,
        max_prosecution_precedents=3,
        max_defense_precedents=3
    )
    
    # Run pipeline
    result = pipeline.run(
        case_context=case_summary,
        statutory_object=stage4_sample
    )
    
    print("\n" + "="*80)
    print("PIPELINE RESULT")
    print("="*80)
    print(f"Status: {result.status}")
    print(f"Feedback: {result.feedback}")
    print(f"Issues: {len(result.issues)}")
    
    if result.verified_precedent_object:
        obj = result.verified_precedent_object
        print(f"\nProsecution Precedents: {len(obj.prosecution_precedents)}")
        for i, prec in enumerate(obj.prosecution_precedents, 1):
            print(f"  {i}. {prec.case_name}")
            print(f"     Score: {prec.final_relevance_score:.2f}")
            print(f"     Relevance: {prec.relevance_evaluation.relevance_type}")
        
        print(f"\nDefense Precedents: {len(obj.defense_precedents)}")
        for i, prec in enumerate(obj.defense_precedents, 1):
            print(f"  {i}. {prec.case_name}")
            print(f"     Score: {prec.final_relevance_score:.2f}")
            print(f"     Relevance: {prec.relevance_evaluation.relevance_type}")
        
        if obj.shared_precedents:
            print(f"\nShared Precedents: {obj.shared_precedents}")


if __name__ == "__main__":
    test_stage5_pipeline()
