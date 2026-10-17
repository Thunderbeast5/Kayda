"""
End-to-End Pipeline Test: LexiGraphBE + Precedent Retrieval
Tests the complete flow from case text to precedent recommendations.
"""
import json
import sys
from pathlib import Path

# Test case
MEDICAL_NEGLIGENCE_CASE = """
The applicant, a senior medical officer at a private hospital, seeks anticipatory bail after an FIR was registered following the death of a patient who underwent emergency surgery at the hospital. The complainant, a relative of the deceased, alleges that the applicant deliberately ignored repeated warnings regarding the patient's deteriorating condition, failed to arrange timely specialist intervention, and falsified certain entries in the medical records to conceal negligence. The FIR further alleges that the applicant, along with the hospital administrator, destroyed internal monitoring records and instructed junior staff members not to disclose the actual sequence of events. The applicant denies these allegations and submits that the patient was admitted in a critical condition, all necessary medical procedures were followed, and the death resulted from complications that could not have been reasonably anticipated.
"""

def test_lexigraphbe_only():
    """Test only LexiGraphBE stages 0-4."""
    print("="*80)
    print("TEST 1: LEXIGRAPHBE PIPELINE (STAGES 0-4)")
    print("="*80)
    
    try:
        from lexigraphbe.runner import run_full_pipeline
        
        result = run_full_pipeline(text=MEDICAL_NEGLIGENCE_CASE)
        
        print("\n✅ LexiGraphBE Pipeline Completed Successfully")
        print(f"   - Status: {result.get('status', 'unknown')}")
        
        # Check Stage 4 output
        stage4 = result.get('stage4_result', {})
        if isinstance(stage4, dict):
            verified_offences = stage4.get('verified_offences', [])
            print(f"   - Verified Offences: {len(verified_offences)}")
            for offence in verified_offences[:5]:
                sec = offence.get('section_number', '?')
                title = offence.get('title', 'Unknown')
                print(f"     • Section {sec}: {title}")
        
        return result
        
    except Exception as e:
        print(f"\n❌ LexiGraphBE Pipeline Failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_precedent_only():
    """Test only Precedent Retrieval with mock Stage 4 output."""
    print("\n" + "="*80)
    print("TEST 2: PRECEDENT RETRIEVAL (STAGE 5 STANDALONE)")
    print("="*80)
    
    try:
        from precedent_retrieval.pipeline import PrecedentPipeline
        
        # Mock Stage 4 output
        mock_stage4 = {
            "verified_offences": [
                {
                    "section_number": "304A",
                    "statute": "IPC",
                    "title": "Causing death by negligence",
                    "overall_status": "Prima Facie Attracted",
                    "confidence": 0.75
                },
                {
                    "section_number": "204",
                    "statute": "IPC",
                    "title": "Destruction of document to prevent its production as evidence",
                    "overall_status": "Prima Facie Attracted",
                    "confidence": 0.70
                },
                {
                    "section_number": "477A",
                    "statute": "IPC",
                    "title": "Falsification of accounts",
                    "overall_status": "Requires Investigation",
                    "confidence": 0.60
                }
            ],
            "legal_regime": "IPC + CrPC"
        }
        
        # Mock Stage 0 output
        mock_case_context = {
            "case_facts": MEDICAL_NEGLIGENCE_CASE,
            "requested_relief": "Anticipatory Bail",
            "procedural_stage": "Anticipatory Bail"
        }
        
        # Mock Stage 1 legal issues
        mock_legal_issues = [
            "What evidence supports the allegation that the senior medical officer's failure to arrange timely specialist intervention caused the patient's death?",
            "What evidence supports the allegation of destruction of internal monitoring records?",
            "What are the grounds for opposing anticipatory bail based on risk of influencing witnesses?"
        ]
        
        pipeline = PrecedentPipeline(max_candidates=20)
        result = pipeline.run(
            case_context=mock_case_context,
            statutory_object=mock_stage4,
            legal_issues=mock_legal_issues
        )
        
        prec_obj = result.verified_precedent_object
        
        print(f"\n✅ Precedent Retrieval Completed Successfully")
        print(f"   - Status: {result.status}")
        print(f"   - Judgments Scanned: {prec_obj.total_judgments_scanned}")
        print(f"   - Candidates After Match: {prec_obj.candidates_after_statutory_match}")
        print(f"   - Prosecution Precedents: {len(prec_obj.prosecution_precedents)}")
        print(f"   - Defense Precedents: {len(prec_obj.defense_precedents)}")
        
        if prec_obj.prosecution_precedents:
            print("\n   Top Prosecution Precedents:")
            for i, prec in enumerate(prec_obj.prosecution_precedents[:3], 1):
                print(f"     {i}. {prec.case_name} ({prec.case_id})")
                print(f"        Score: {prec.calibrated_relevance_score:.3f}")
        
        if prec_obj.defense_precedents:
            print("\n   Top Defense Precedents:")
            for i, prec in enumerate(prec_obj.defense_precedents[:3], 1):
                print(f"     {i}. {prec.case_name} ({prec.case_id})")
                print(f"        Score: {prec.calibrated_relevance_score:.3f}")
        
        return result
        
    except Exception as e:
        print(f"\n❌ Precedent Retrieval Failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_full_integration():
    """Test full integration: LexiGraphBE → Precedent Retrieval."""
    print("\n" + "="*80)
    print("TEST 3: FULL INTEGRATION (STAGES 0-5)")
    print("="*80)
    
    try:
        from lexigraphbe.runner import run_full_pipeline
        from precedent_retrieval.pipeline import PrecedentPipeline
        
        # Step 1: Run LexiGraphBE
        print("\n[1/2] Running LexiGraphBE pipeline...")
        lexi_result = run_full_pipeline(text=MEDICAL_NEGLIGENCE_CASE)
        
        if not lexi_result or lexi_result.get('status') != 'VERIFIED':
            print("❌ LexiGraphBE failed, cannot proceed to precedent retrieval")
            return None
        
        print("✅ LexiGraphBE completed")
        
        # Step 2: Extract outputs
        stage0_result = lexi_result.get('stage0_result')
        stage1_result = lexi_result.get('stage1_result')
        stage4_result = lexi_result.get('stage4_result')
        
        # Extract legal issues from Stage 1
        legal_issues = []
        if stage1_result and isinstance(stage1_result, dict):
            sub_queries = stage1_result.get('sub_queries', [])
            legal_issues = [sq.get('query', '') for sq in sub_queries if sq.get('query')]
        
        print(f"   - Extracted {len(legal_issues)} legal issues from Stage 1")
        
        # Step 3: Run Precedent Retrieval
        print("\n[2/2] Running Precedent Retrieval pipeline...")
        prec_pipeline = PrecedentPipeline(max_candidates=20)
        prec_result = prec_pipeline.run(
            case_context=stage0_result,
            statutory_object=stage4_result,
            legal_issues=legal_issues
        )
        
        prec_obj = prec_result.verified_precedent_object
        
        print(f"\n✅ Full Integration Test PASSED")
        print(f"\n   LEXIGRAPHBE RESULTS:")
        stage4 = lexi_result.get('stage4_result', {})
        if isinstance(stage4, dict):
            verified_offences = stage4.get('verified_offences', [])
            print(f"   - Verified Offences: {len(verified_offences)}")
            for offence in verified_offences[:5]:
                sec = offence.get('section_number', '?')
                print(f"     • Section {sec}")
        
        print(f"\n   PRECEDENT RETRIEVAL RESULTS:")
        print(f"   - Judgments Scanned: {prec_obj.total_judgments_scanned}")
        print(f"   - Candidates Matched: {prec_obj.candidates_after_statutory_match}")
        print(f"   - Prosecution Precedents: {len(prec_obj.prosecution_precedents)}")
        print(f"   - Defense Precedents: {len(prec_obj.defense_precedents)}")
        
        # Save results
        output = {
            "lexigraphbe": lexi_result,
            "precedent_retrieval": prec_result.model_dump() if hasattr(prec_result, 'model_dump') else {}
        }
        
        output_file = Path("full_pipeline_test_output.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str)
        
        print(f"\n   Results saved to: {output_file}")
        
        return output
        
    except Exception as e:
        print(f"\n❌ Full Integration Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("MOOT COURT PIPELINE - END-TO-END TEST SUITE")
    print("="*80)
    print(f"\nTest Case: Medical Negligence Anticipatory Bail")
    print(f"Length: {len(MEDICAL_NEGLIGENCE_CASE)} characters")
    
    results = {}
    
    # Test 1: LexiGraphBE only
    results['lexigraphbe'] = test_lexigraphbe_only()
    
    # Test 2: Precedent Retrieval only (with mocks)
    results['precedent_standalone'] = test_precedent_only()
    
    # Test 3: Full integration
    if results['lexigraphbe'] is not None:
        results['full_integration'] = test_full_integration()
    else:
        print("\n⚠️  Skipping full integration test (LexiGraphBE failed)")
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v is not None)
    total = len(results)
    
    print(f"\nTests Passed: {passed}/{total}")
    print(f"Tests Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print("\n⚠️  SOME TESTS FAILED - Check logs above for details")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    main()
