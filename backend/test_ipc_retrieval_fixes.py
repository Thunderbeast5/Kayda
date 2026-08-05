"""
Test script to verify IPC retrieval fixes:
1. IPC 120B (conspiracy) rejection when no agreement/multiple persons
2. IPC 406 vs IPC 420 distinction (entrustment vs inducement)
3. IPC 411 rejection when no receiving element
4. Candidate reduction from 63 to <10
"""

import sys
from pathlib import Path

# Add prosecutor directory to path
prosecutor_dir = Path(__file__).parent / "prosecutor"
sys.path.insert(0, str(prosecutor_dir.parent))

from prosecutor.services.llm_ipc_retrieval_service import LLMIPCRetrievalService

def test_investment_scam():
    """Test the investment scam fact pattern that previously had retrieval errors."""
    
    # Initialize service
    service = LLMIPCRetrievalService(prosecutor_dir=prosecutor_dir)
    
    # Investment scam facts
    case_facts = """
    The applicant seeks anticipatory bail in connection with an FIR registered under IPC sections 420, 406, 120B.
    
    The complainant alleges that the applicant falsely represented himself as a licensed real estate developer 
    and induced her to invest Rs 50 lakhs in a luxury apartment project. The applicant promised guaranteed 
    returns of 20% per annum and assured timely completion of the project within 2 years.
    
    Based on these false representations, the complainant handed over Rs 50 lakhs to the applicant through 
    multiple bank transfers between January 2023 and June 2023. However, no construction work was ever 
    undertaken, and the applicant misappropriated the funds for personal expenses.
    
    When the complainant demanded return of her money, the applicant gave evasive replies and subsequently 
    became untraceable. The complainant discovered that the applicant had defrauded multiple other investors 
    in a similar manner, collecting over Rs 2 crores in total.
    
    The applicant denies all allegations and states that this is a civil dispute arising from a legitimate 
    business transaction that failed due to market conditions. He claims he has cooperated with the investigation.
    """
    
    # Sub-queries (simplified - in real system these come from query expansion)
    sub_queries = [
        {
            "query": "False representation as licensed real estate developer to induce investment",
            "type": "OFFENCE"
        },
        {
            "query": "Dishonestly induced delivery of Rs 50 lakhs through false promises of guaranteed returns",
            "type": "OFFENCE"
        },
        {
            "query": "Misappropriation of invested funds for personal expenses",
            "type": "OFFENCE"
        },
        {
            "query": "Defrauding multiple investors in similar manner",
            "type": "OFFENCE"
        }
    ]
    
    print("="*80)
    print("TESTING IPC RETRIEVAL FIXES")
    print("="*80)
    print("\nCASE FACTS (first 200 chars):")
    print(case_facts[:200] + "...\n")
    
    print("SUB-QUERIES:")
    for i, sq in enumerate(sub_queries, 1):
        print(f"{i}. {sq['query']}")
    
    print("\n" + "="*80)
    print("RUNNING RETRIEVAL...")
    print("="*80 + "\n")
    
    # Run retrieval
    results = service.retrieve_sections(
        sub_queries=sub_queries,
        case_facts=case_facts,
        top_k=20
    )
    
    # Analyze results
    print("\n" + "="*80)
    print("RESULTS ANALYSIS")
    print("="*80 + "\n")
    
    if not results.get("retrieval_results"):
        print("❌ ERROR: No retrieval results returned")
        return
    
    all_matches = []
    for result in results["retrieval_results"]:
        all_matches.extend(result.get("matches", []))
    
    # Deduplicate by section ID
    unique_sections = {}
    for match in all_matches:
        section_id = match["id"]
        if section_id not in unique_sections:
            unique_sections[section_id] = match
    
    print(f"✓ Total unique candidate sections: {len(unique_sections)}")
    
    if len(unique_sections) > 10:
        print(f"⚠ WARNING: Expected <10 candidates, got {len(unique_sections)}")
    else:
        print(f"✓ SUCCESS: Candidate count reduced to {len(unique_sections)} (target: <10)")
    
    print("\n" + "-"*80)
    print("CRITICAL SECTION CHECKS")
    print("-"*80 + "\n")
    
    # Check IPC 120B (conspiracy)
    ipc_120b = unique_sections.get("IPC_120B")
    if ipc_120b:
        print("❌ FAIL: IPC 120B (conspiracy) was incorrectly selected")
        print("   Reason: No agreement between multiple persons in facts")
        print(f"   Score: {ipc_120b['score']:.2f}")
        print(f"   Reasoning: {ipc_120b['metadata'].get('reasoning', 'N/A')}")
    else:
        print("✓ PASS: IPC 120B (conspiracy) correctly rejected")
    
    # Check IPC 406 (criminal breach of trust)
    ipc_406 = unique_sections.get("IPC_406")
    if ipc_406:
        print("\n⚠ IPC 406 (criminal breach of trust) was selected")
        print("   This is INCORRECT if reasoning mentions 'inducement' or 'false promise'")
        print("   IPC 406 requires ENTRUSTMENT (fiduciary relationship)")
        print(f"   Score: {ipc_406['score']:.2f}")
        print(f"   Reasoning: {ipc_406['metadata'].get('reasoning', 'N/A')}")
        reasoning = ipc_406['metadata'].get('reasoning', '').lower()
        if 'entrustment' in reasoning or 'entrusted' in reasoning:
            print("   → Reasoning mentions entrustment (could be correct if fiduciary relationship exists)")
        elif 'induc' in reasoning or 'false promise' in reasoning:
            print("   ❌ FAIL: Reasoning shows IPC 406/420 confusion (inducement = IPC 420, not 406)")
    else:
        print("\n✓ PASS: IPC 406 correctly rejected (or not considered)")
        print("   Note: IPC 406 requires entrustment. False promise = IPC 420, not 406")
    
    # Check IPC 420 (cheating)
    ipc_420 = unique_sections.get("IPC_420")
    if ipc_420:
        print("\n✓ IPC 420 (cheating and dishonestly inducing delivery) selected")
        print("   This is CORRECT for false promise + induced delivery")
        print(f"   Score: {ipc_420['score']:.2f}")
        print(f"   Reasoning: {ipc_420['metadata'].get('reasoning', 'N/A')}")
    else:
        print("\n⚠ WARNING: IPC 420 (cheating) not selected")
        print("   IPC 420 should be selected for false representation + induced delivery")
    
    # Check IPC 411 (receiving stolen property)
    ipc_411 = unique_sections.get("IPC_411")
    if ipc_411:
        print("\n❌ FAIL: IPC 411 (receiving stolen property) was incorrectly selected")
        print("   Reason: No 'receiving' element - accused directly committed fraud")
        print(f"   Score: {ipc_411['score']:.2f}")
        print(f"   Reasoning: {ipc_411['metadata'].get('reasoning', 'N/A')}")
    else:
        print("\n✓ PASS: IPC 411 (receiving stolen property) correctly rejected")
    
    # List all selected sections
    print("\n" + "-"*80)
    print("ALL SELECTED SECTIONS")
    print("-"*80 + "\n")
    
    sorted_sections = sorted(unique_sections.values(), key=lambda x: x['score'], reverse=True)
    for i, match in enumerate(sorted_sections, 1):
        section_id = match['id']
        section_num = match['metadata'].get('section_num', section_id.replace('IPC_', ''))
        title = match['metadata'].get('title', 'N/A')
        score = match['score']
        chapter = match['metadata'].get('chapter_title', 'N/A')
        
        print(f"{i}. IPC {section_num} - {title[:60]}")
        print(f"   Chapter: {chapter}")
        print(f"   Score: {score:.2f}")
        print()
    
    print("="*80)
    print("TEST COMPLETE")
    print("="*80)

if __name__ == "__main__":
    test_investment_scam()
