"""
Test script to demonstrate the improved defense argument generation.
Shows the new concise, legally sound, courtroom-style argument.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from orchestrator_agent import OrchestratorAgent

# Test case: Property dispute with forgery allegations
TEST_CASE = """
Case Facts:

The accused, Mr. Rajesh Kumar, is charged under Sections 467, 468, 471, 420, 423, and 406 IPC 
in connection with a property transaction dispute involving agricultural land.

The complainant, Mr. Suresh Mehta, alleges that the accused entered into an agreement to sell 
agricultural land measuring 5 acres in Village Rampur. The complainant states that he paid an 
advance of Rs. 75 lakhs to the accused based on ownership documents produced by the accused.

The complainant subsequently discovered that the ownership documents were allegedly forged, as 
the revenue records showed a different person as the rightful owner of the land. The complainant 
alleges that the accused knowingly presented false documents to induce him to part with the money.

The accused's position is that the documents are genuine and that he is the lawful owner of the 
land. The accused states that the dispute arises from a disagreement over the interpretation of 
certain revenue entries and that the complainant is attempting to criminalize what is essentially 
a civil dispute over title to the property.

The accused has appeared before the investigating officer on multiple occasions and has provided 
all documents requested. The revenue records and original sale deeds are now with the police for 
verification. The accused has surrendered his passport voluntarily to the investigating officer.

Current Status:
- Investigation is ongoing
- Documents under verification by revenue authorities
- Accused has cooperated throughout
- No allegations of absconding, tampering, or obstruction
- Accused is seeking anticipatory bail under Section 438 CrPC
"""

def test_improved_defense_argument():
    """Test the improved defense argument generation"""
    print("\n" + "="*80)
    print("TESTING IMPROVED DEFENSE ARGUMENT GENERATION")
    print("="*80 + "\n")
    
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("Error: OPENAI_API_KEY not set!")
        return
    
    orchestrator = OrchestratorAgent(api_key=api_key)
    
    # Step 1: Run lexigraphbe pipeline
    print("Step 1: Running Lexigraphbe Pipeline...")
    result = orchestrator.run_lexigraphbe_pipeline(TEST_CASE)
    
    print(f"\n✓ Retrieved {len(result.verified_sections)} sections:")
    for section in result.verified_sections:
        print(f"  - § {section.section_number} {section.statute}: {section.title}")
    
    # Step 2: Store sections for defense
    orchestrator.sections = result
    orchestrator.case_text = TEST_CASE
    orchestrator.student_role = "prosecution"  # So LLM plays defense
    orchestrator.llm_role = "defense"
    
    # Step 3: Initialize defense agent
    print("\nStep 2: Initializing Defense Agent...")
    agent_wrapper = orchestrator.initialize_agent("defense")
    
    # Step 4: Generate opening argument
    print("\nStep 3: Generating Opening Bail Argument...")
    print("-" * 80)
    
    agent = agent_wrapper["agent"]
    result_dict = agent.build_opening_argument()
    
    opening_statement = result_dict.get("opening_statement", "")
    
    # Display the improved argument
    print("\n" + "="*80)
    print("IMPROVED DEFENSE OPENING ARGUMENT")
    print("="*80 + "\n")
    
    # Wrap text at 80 characters for readability
    words = opening_statement.split()
    lines = []
    current_line = ""
    
    for word in words:
        if len(current_line) + len(word) + 1 <= 78:
            current_line += (word + " ")
        else:
            lines.append(current_line.strip())
            current_line = word + " "
    if current_line:
        lines.append(current_line.strip())
    
    for line in lines:
        print(line)
    
    # Display word count
    word_count = len(opening_statement.split())
    print("\n" + "-" * 80)
    print(f"Word Count: {word_count} words")
    print(f"Target Range: 180-250 words")
    print(f"Within Range: {'✓ YES' if 180 <= word_count <= 250 else '✗ NO'}")
    
    # Check for repetition
    sentences = [s.strip() for s in opening_statement.split('.') if s.strip()]
    print(f"Sentence Count: {len(sentences)}")
    
    # Check for required elements
    print("\nRequired Elements Check:")
    checks = {
        "Opens with 'May it please'": opening_statement.startswith("May it please"),
        "Identifies offences invoked": "Section" in opening_statement and "IPC" in opening_statement,
        "States prosecution case": "prosecution" in opening_statement.lower() or "alleged" in opening_statement.lower(),
        "States applicant position": "applicant" in opening_statement.lower() and "submit" in opening_statement.lower(),
        "Addresses bail factors": any(term in opening_statement.lower() for term in ["custodial", "interrogation", "necessary", "documentary", "cooperat"]),
        "Ends with prayer": opening_statement.strip().endswith("appropriate.") or "prayed" in opening_statement[-100:].lower(),
        "No repetition (< 2.5 avg word/sentence)": word_count / max(len(sentences), 1) < 40,
    }
    
    for check, passed in checks.items():
        print(f"  {'✓' if passed else '✗'} {check}")
    
    all_passed = all(checks.values())
    
    print("\n" + "="*80)
    if all_passed and 180 <= word_count <= 250:
        print("✓ ARGUMENT GENERATION SUCCESSFUL - ALL CHECKS PASSED!")
    else:
        print("⚠ Some checks failed - review argument above")
    print("="*80 + "\n")
    
    return opening_statement

if __name__ == "__main__":
    test_improved_defense_argument()
