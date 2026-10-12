"""
Test script for orchestrator without interactive input
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from orchestrator_agent import OrchestratorAgent

# Test case text
TEST_CASE = """
Case Facts:
The accused, Mr. Rajesh Kumar, is charged under Section 420 IPC (Cheating) and Section 
406 IPC (Criminal Breach of Trust) in connection with a property transaction dispute. 

The complainant alleges that the accused entered into an agreement to purchase a 
commercial property worth Rs. 75 lakhs but failed to complete the transaction despite 
receiving an advance of Rs. 15 lakhs.

The accused contends that this is a purely civil dispute arising from a commercial 
transaction, and that the complainant has given it a criminal color to exert pressure. 
The accused states that he was unable to complete the transaction due to financial 
difficulties arising from the COVID-19 pandemic.

Current Status:
- Investigation is complete and chargesheet has been filed
- Accused has surrendered his passport voluntarily
- Accused has deep roots in the community
- No history of witness tampering or intimidation
- Accused is seeking anticipatory bail under Section 438 CrPC
"""

def test_lexigraphbe_pipeline():
    """Test just the lexigraphbe pipeline part"""
    print("\n" + "="*60)
    print("TESTING ORCHESTRATOR - LEXIGRAPHBE PIPELINE")
    print("="*60 + "\n")
    
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("Error: OPENAI_API_KEY not set!")
        return
    
    orchestrator = OrchestratorAgent(api_key=api_key)
    
    # Test lexigraphbe pipeline
    print("Running lexigraphbe pipeline on test case...")
    result = orchestrator.run_lexigraphbe_pipeline(TEST_CASE)
    
    print(f"\n✓ Pipeline completed!")
    print(f"✓ Retrieved {len(result.verified_sections)} sections")
    
    for section in result.verified_sections:
        print(f"  - § {section.section_number} {section.statute}: {section.title}")
        print(f"    Status: {section.overall_status}")
        print(f"    Strength: {section.overall_prima_facie_strength}")
    
    print(f"\n✓ Bail Recommendation: {result.bail_recommendation}")
    
    print("\n" + "="*60)
    print("TEST COMPLETED SUCCESSFULLY")
    print("="*60 + "\n")

if __name__ == "__main__":
    test_lexigraphbe_pipeline()
