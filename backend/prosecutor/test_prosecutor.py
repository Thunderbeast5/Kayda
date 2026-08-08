"""
Test script for Prosecutor Agent
"""

import json
from prosecutor import ProsecutorAgent

def test_basic_flow():
    """Test basic prosecutor agent flow without full lexigraphbe integration"""
    
    print("=" * 80)
    print("PROSECUTOR AGENT TEST")
    print("=" * 80)
    
    # Simple test case
    case_file = """
A complaint has been filed against Mr. Rajesh Kumar for dowry harassment.
According to the complaint, since their marriage in January 2023, Rajesh and 
his family have been demanding additional dowry of 5 lakhs rupees.
When the family refused, the wife was subjected to physical and mental cruelty 
including beatings and verbal abuse. The wife has filed an FIR.
"""
    
    print("\nTest Case:")
    print(case_file)
    print("\n" + "=" * 80)
    
    try:
        # Initialize prosecutor
        print("\n[TEST 1] Initializing Prosecutor Agent...")
        prosecutor = ProsecutorAgent()
        print("✓ Initialization successful (using Groq API)")
        
        # Analyze case
        print("\n[TEST 2] Analyzing case (this will call Groq LLM)...")
        print("Note: This may take 5-10 seconds...")
        analysis = prosecutor.analyze_case(case_file)
        print("✓ Case analysis complete")
        
        print(f"\n  Primary Crime: {analysis.primary_crime}")
        print(f"  Prosecution Theory: {analysis.prosecution_theory[:100]}...")
        print(f"  Identified Crimes: {len(analysis.identified_crimes)}")
        for crime in analysis.identified_crimes:
            print(f"    - {crime.crime_name} ({crime.severity})")
            print(f"      Elements: {', '.join(crime.legal_elements[:2])}...")
        
        # Get summary
        print("\n[TEST 3] Getting analysis summary...")
        summary = prosecutor.get_analysis_summary()
        print("✓ Summary retrieved")
        print(f"\n  Primary Crime: {summary['primary_crime']}")
        print(f"  Total Crimes Identified: {len(summary['identified_crimes'])}")
        print(f"  Cached Queries: {summary['cached_queries']}")
        
        print("\n" + "=" * 80)
        print("ALL TESTS PASSED ✓")
        print("=" * 80)
        print("\nNote: To test with lexigraphbe retrieval, you would call:")
        print("  opening = prosecutor.build_opening_argument()")
        print("This requires the full lexigraph agent to be available.")
        
        return True
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_basic_flow()
    exit(0 if success else 1)
