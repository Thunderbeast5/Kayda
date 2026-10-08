"""
Test script for Stage 5 Precedent Retrieval Pipeline.
Tests the complete pipeline on a real test case.
"""

import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from lexigraphbe.stage5_precedent_pipeline import Stage5PrecedentPipeline
from lexigraphbe.schemas import StatutoryVerificationObject, CaseContextObject


def test_stage5_with_real_case():
    """Test Stage 5 pipeline with a real test case."""
    
    print("="*100)
    print("TESTING STAGE 5 PRECEDENT RETRIEVAL PIPELINE WITH REAL CASE")
    print("="*100)
    
    # Load test case
    test_case_path = Path(__file__).parent / "bail_data" / "test_case.txt"
    with open(test_case_path, "r", encoding="utf-8") as f:
        test_case_text = f.read()
    
    print(f"\nTest case loaded ({len(test_case_text)} characters)")
    print(f"First 200 chars: {test_case_text[:200]}...")
    
    # Create mock Stage 4 output based on the test case
    # The test case mentions: Sections 406, 420, 465, 468, 471 IPC
    stage4_mock = {
        "verified_offences": [
            {
                "section_number": "406",
                "statute": "IPC",
                "title": "Criminal breach of trust",
                "overall_prima_facie_strength": "Moderate",
                "ingredient_evaluation": [
                    {
                        "ingredient": "Entrustment of property",
                        "status": "Satisfied",
                        "reason": "Complainant advanced ₹18 lakhs",
                        "confidence": 0.85
                    },
                    {
                        "ingredient": "Dishonest misappropriation or conversion",
                        "status": "Partially Satisfied",
                        "reason": "Alleged failure to complete transaction and return money",
                        "confidence": 0.70
                    }
                ],
                "overall_status": "Prima Facie Attracted",
                "confidence": 0.75
            },
            {
                "section_number": "420",
                "statute": "IPC",
                "title": "Cheating and dishonestly inducing delivery of property",
                "overall_prima_facie_strength": "Moderate",
                "ingredient_evaluation": [
                    {
                        "ingredient": "Deception",
                        "status": "Partially Satisfied",
                        "reason": "Alleged false promises regarding property transaction",
                        "confidence": 0.70
                    },
                    {
                        "ingredient": "Dishonest inducement to deliver property",
                        "status": "Satisfied",
                        "reason": "Complainant parted with ₹18 lakhs",
                        "confidence": 0.80
                    }
                ],
                "overall_status": "Prima Facie Attracted",
                "confidence": 0.72
            },
            {
                "section_number": "468",
                "statute": "IPC",
                "title": "Forgery for purpose of cheating",
                "overall_prima_facie_strength": "Weak",
                "ingredient_evaluation": [
                    {
                        "ingredient": "Making false document",
                        "status": "Insufficient Evidence",
                        "reason": "Documents yet to be forensically examined",
                        "confidence": 0.50
                    }
                ],
                "overall_status": "Requires Investigation",
                "confidence": 0.55
            }
        ],
        "verified_sections": [],
        "legal_regime": "IPC + CrPC",
        "verification_status": "VERIFIED"
    }
    
    # Create case context summary
    case_summary = """Commercial property transaction dispute involving allegations of cheating and breach of trust.
    Applicant is a 42-year-old businessman with no criminal record seeking anticipatory bail.
    Facts: Agreement for purchase of commercial property worth ₹80 lakhs; advance payment of ₹18 lakhs received;
    transaction failed to complete; allegations of forged documents. 
    Applicant denies allegations, claims commercial dispute, offers to return advance with interest.
    Defense argues: no criminal antecedents, no violence/threats, documentary dispute, cooperation with investigation,
    permanent resident, willing to surrender passport, no witness intimidation.
    Prosecution opposes: serious charges (cheating, breach of trust, forgery), custodial interrogation needed for
    document verification and money trail investigation."""
    
    # Initialize pipeline with reasonable limits for testing
    print("\n" + "-"*100)
    print("Initializing Stage 5 Pipeline...")
    print("-"*100)
    
    pipeline = Stage5PrecedentPipeline(
        max_candidates=10,  # Get top 10 from statutory matching
        max_prosecution_precedents=5,  # Return top 5 for prosecution
        max_defense_precedents=5  # Return top 5 for defense
    )
    
    # Run pipeline
    print("\n" + "-"*100)
    print("Running Pipeline...")
    print("-"*100)
    
    result = pipeline.run(
        case_context=case_summary,
        statutory_object=stage4_mock
    )
    
    # Display results
    print("\n" + "="*100)
    print("PIPELINE RESULTS")
    print("="*100)
    
    print(f"\nStatus: {result.status}")
    print(f"Feedback: {result.feedback}")
    
    if result.issues:
        print(f"\nIssues ({len(result.issues)}):")
        for issue in result.issues:
            print(f"  - [{issue.target}] {issue.issue}")
    
    if result.verified_precedent_object:
        obj = result.verified_precedent_object
        
        print(f"\n" + "="*100)
        print(f"PRECEDENT RETRIEVAL SUMMARY")
        print("="*100)
        print(f"Total judgments scanned: {obj.total_judgments_scanned}")
        print(f"Candidates after statutory match: {obj.candidates_after_statutory_match}")
        print(f"Input statutes: {len(obj.input_statutes)}")
        for stat in obj.input_statutes:
            print(f"  - {stat['act']} Section {stat['section']}")
        
        # Prosecution precedents
        print(f"\n" + "-"*100)
        print(f"PROSECUTION PRECEDENTS: {len(obj.prosecution_precedents)}")
        print("-"*100)
        
        for i, prec in enumerate(obj.prosecution_precedents, 1):
            print(f"\n{i}. {prec.case_name}")
            print(f"   Case ID: {prec.case_id}")
            print(f"   Court: {prec.court}")
            print(f"   Decided: {prec.decided_on}")
            print(f"   Procedural Stage: {prec.procedural_stage}")
            print(f"   Final Relevance Score: {prec.final_relevance_score:.3f}")
            print(f"   Statutory Match Score: {prec.match_score:.3f}")
            
            rel_eval = prec.relevance_evaluation
            print(f"\n   LLM EVALUATION:")
            print(f"   - Relevant: {rel_eval.is_relevant}")
            print(f"   - Relevance Type: {rel_eval.relevance_type}")
            print(f"   - Confidence: {rel_eval.confidence:.2f}")
            print(f"   - Factual Similarity: {rel_eval.factual_similarity[:150]}...")
            print(f"   - Legal Principle Alignment: {rel_eval.legal_principle_alignment[:150]}...")
            print(f"   - Usage Recommendation: {rel_eval.usage_recommendation[:200]}...")
            
            if rel_eval.supporting_propositions:
                print(f"   - Supporting Propositions: {rel_eval.supporting_propositions}")
            if rel_eval.key_quotes:
                print(f"   - Key Quotes ({len(rel_eval.key_quotes)}):")
                for quote in rel_eval.key_quotes[:2]:
                    print(f"     • {quote[:150]}...")
            
            print(f"\n   MATCHED STATUTES:")
            for match in prec.matched_statutes:
                print(f"   - {match.judgment_act} Section {match.judgment_section} [{match.match_type}]")
        
        # Defense precedents
        print(f"\n" + "-"*100)
        print(f"DEFENSE PRECEDENTS: {len(obj.defense_precedents)}")
        print("-"*100)
        
        for i, prec in enumerate(obj.defense_precedents, 1):
            print(f"\n{i}. {prec.case_name}")
            print(f"   Case ID: {prec.case_id}")
            print(f"   Court: {prec.court}")
            print(f"   Decided: {prec.decided_on}")
            print(f"   Procedural Stage: {prec.procedural_stage}")
            print(f"   Final Relevance Score: {prec.final_relevance_score:.3f}")
            print(f"   Statutory Match Score: {prec.match_score:.3f}")
            
            rel_eval = prec.relevance_evaluation
            print(f"\n   LLM EVALUATION:")
            print(f"   - Relevant: {rel_eval.is_relevant}")
            print(f"   - Relevance Type: {rel_eval.relevance_type}")
            print(f"   - Confidence: {rel_eval.confidence:.2f}")
            print(f"   - Factual Similarity: {rel_eval.factual_similarity[:150]}...")
            print(f"   - Legal Principle Alignment: {rel_eval.legal_principle_alignment[:150]}...")
            print(f"   - Usage Recommendation: {rel_eval.usage_recommendation[:200]}...")
            
            if rel_eval.supporting_propositions:
                print(f"   - Supporting Propositions: {rel_eval.supporting_propositions}")
            if rel_eval.key_quotes:
                print(f"   - Key Quotes ({len(rel_eval.key_quotes)}):")
                for quote in rel_eval.key_quotes[:2]:
                    print(f"     • {quote[:150]}...")
            
            print(f"\n   MATCHED STATUTES:")
            for match in prec.matched_statutes:
                print(f"   - {match.judgment_act} Section {match.judgment_section} [{match.match_type}]")
        
        # Shared precedents
        if obj.shared_precedents:
            print(f"\n" + "-"*100)
            print(f"SHARED PRECEDENTS (Relevant to both sides): {len(obj.shared_precedents)}")
            print("-"*100)
            for case_id in obj.shared_precedents:
                print(f"  - {case_id}")
        
        print("\n" + "="*100)
        print("TEST COMPLETED SUCCESSFULLY")
        print("="*100)
    
    else:
        print("\nNo precedent object returned")
    
    return result


if __name__ == "__main__":
    try:
        result = test_stage5_with_real_case()
        print("\n[+] Test completed successfully")
    except Exception as e:
        print(f"\n[-] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
