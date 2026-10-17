"""
Test script for full LexiGraphBE pipeline with Groq LLM.
Tests all stages: Stage 0 -> Stage 1 -> Stage 2 -> Stage 3 -> Stage 3b (BSA) -> Stage 3c (BNSS) -> Stage 4 -> Stage 5 (Precedent Retrieval)
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from lexigraphbe.runner import run_full_pipeline
import json

# Sample test case
test_case = """
FIR No. 123/2025 registered at Nashik Road Police Station, Maharashtra.

Complainant: Mrs. Sunita Sharma
Accused: Mr. Rajesh Sharma (Husband)

Facts:
The complainant alleges that her husband Rajesh Sharma has been subjecting her to cruelty for the past 2 years demanding dowry of Rs. 10 lakhs. He has threatened to kill her if she does not bring the money. He has also misappropriated her gold jewelry worth Rs. 5 lakhs which was given to her by her parents at the time of marriage.

On 15th January 2025, the accused assaulted the complainant with a wooden stick causing grievous injuries on her back and arms. Medical examination confirms multiple contusions and bruises.

The complainant seeks anticipatory bail apprehending arrest under IPC 498A (Cruelty by husband), IPC 406 (Criminal breach of trust), and IPC 506 (Criminal intimidation).
"""

def main():
    print("=" * 80)
    print("TESTING LEXIGRAPHBE PIPELINE WITH GROQ LLM")
    print("=" * 80)
    print("\nTest Case:")
    print(test_case)
    print("\n" + "=" * 80)
    print("Running full pipeline (Stage 0 through Stage 5)...")
    print("=" * 80 + "\n")
    
    try:
        result = run_full_pipeline(
            text=test_case,
            user_query="Analyze the case for anticipatory bail application",
            court_type="Sessions Court",
            legal_regime_override="IPC + CrPC"
        )
        
        print("\n" + "=" * 80)
        print("PIPELINE EXECUTION SUCCESSFUL!")
        print("=" * 80)
        
        # Save full result to file
        output_file = backend_path / "lexigraphbe_test_result.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\nFull result saved to: {output_file}")
        
        # Print summary
        print("\n" + "=" * 80)
        print("PIPELINE SUMMARY:")
        print("=" * 80)
        
        # Stage 0 Summary
        stage0 = result.get("stage0_case_context", {})
        print(f"\n[Stage 0] Case Context:")
        print(f"  - Legal Regime: {stage0.get('legal_regime_decision', {}).get('regime')}")
        print(f"  - Court Type: {stage0.get('court_type')}")
        
        # Stage 1 Summary
        stage1 = result.get("stage1_legal_query", {})
        concepts = stage1.get("legal_concepts", [])
        print(f"\n[Stage 1] Legal Query:")
        print(f"  - Legal Concepts: {len(concepts)}")
        for c in concepts[:3]:
            print(f"    • {c.get('concept', 'N/A')}")
        
        # Stage 2 Summary
        stage2 = result.get("stage2_subquery_mapping", {})
        mappings = stage2.get("mappings", [])
        print(f"\n[Stage 2] Subquery Mapping:")
        print(f"  - Mappings: {len(mappings)}")
        
        # Stage 3 Summary
        stage3 = result.get("stage3_chapter_identification", {})
        verified_offences = stage3.get("verified_offences", [])
        print(f"\n[Stage 3] Chapter Identification:")
        print(f"  - Verified Offences: {len(verified_offences)}")
        for off in verified_offences:
            sec = off.get('section_number', 'N/A')
            title = off.get('offence_title', 'N/A')
            print(f"    • IPC {sec}: {title}")
        
        # Stage 3b Summary (BSA)
        stage3b = result.get("stage3b_bsa_retrieval", {})
        bsa_sections = stage3b.get("relevant_sections", [])
        print(f"\n[Stage 3b] BSA Evidence Law Retrieval:")
        print(f"  - BSA Sections: {len(bsa_sections)}")
        for sec in bsa_sections[:3]:
            print(f"    • BSA {sec.get('section_number')}: {sec.get('heading', 'N/A')[:50]}")
        
        # Stage 3c Summary (BNSS)
        stage3c = result.get("stage3c_bnss_retrieval", {})
        bnss_sections = stage3c.get("relevant_sections", [])
        print(f"\n[Stage 3c] BNSS Procedural Law Retrieval:")
        print(f"  - BNSS Sections: {len(bnss_sections)}")
        for sec in bnss_sections[:3]:
            print(f"    • BNSS {sec.get('section_number')}: {sec.get('heading', 'N/A')[:50]}")
        
        # Stage 4 Summary
        stage4 = result.get("stage4_statutory_verification", {})
        ipc_bns = stage4.get("ipc_to_bns_equivalents", [])
        print(f"\n[Stage 4] Statutory Verification:")
        print(f"  - IPC → BNS Equivalents: {len(ipc_bns)}")
        for eq in ipc_bns:
            print(f"    • IPC {eq.get('ipc_section')} → BNS {eq.get('bns_equivalent')}")
        
        # Stage 4b Summary (Act Router)
        act_router = result.get("stage4b_act_router", {})
        special_acts = act_router.get("act_routing", [])
        print(f"\n[Stage 4b] Special Act Router:")
        print(f"  - Acts Evaluated: {len(special_acts)}")
        for act in special_acts:
            if act.get('decision') == 'PROCESS':
                print(f"    • {act.get('act_title', 'N/A')}: {act.get('decision')}")

        print("\n" + "=" * 80)
        print("LEXIGRAPHBE STAGES 0-4 TEST COMPLETED SUCCESSFULLY!")
        print("=" * 80)

        return 0
        
    except Exception as e:
        print("\n" + "=" * 80)
        print("ERROR DURING PIPELINE EXECUTION:")
        print("=" * 80)
        print(f"\n{type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
