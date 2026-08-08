"""
Test prosecutor with assault case (no dowry involved)
"""

import json
from prosecutor import ProsecutorAgent

def test_assault_case():
    """Test with assault case to verify no dowry hallucination"""
    
    print("=" * 80)
    print("PROSECUTOR AGENT - ASSAULT CASE TEST")
    print("=" * 80)
    
    case_file = """On 10 Jan 2026, Rohan Patil demanded Rs 75,000 from Rahul Sharma; on 12 Jan Rahul threatened to finish him if he returned; on 15 Jan Rahul, Amit Verma and Sameer Khan confronted Rohan, Rahul pushed him, Amit struck his head and arm with a wooden stick while Sameer restrained him, causing a 4 cm scalp laceration and bruising; Rohan was medically examined that night, FIR was filed on 16 Jan, the stick was recovered on 17 Jan and later tested positive for human blood, though DNA was inconclusive; eyewitness Mahesh supports the assault, while Suresh corroborates the prior threat through Rohan's disclosure."""
    
    print("\nCase File:")
    print(case_file)
    print("\n" + "=" * 80)
    
    try:
        # Initialize prosecutor
        print("\n[TEST 1] Initializing Prosecutor Agent...")
        prosecutor = ProsecutorAgent()
        print("[OK] Initialization successful")
        
        # Analyze case
        print("\n[TEST 2] Analyzing assault case...")
        analysis = prosecutor.analyze_case(case_file)
        print("[OK] Case analysis complete")
        
        print(f"\n  Primary Crime: {analysis.primary_crime}")
        print(f"  Prosecution Theory: {analysis.prosecution_theory[:150]}...")
        print(f"\n  Identified Crimes: {len(analysis.identified_crimes)}")
        for crime in analysis.identified_crimes:
            print(f"    - {crime.crime_name} ({crime.severity})")
            print(f"      Elements: {', '.join(crime.legal_elements[:3])}...")
        
        # Verify no dowry hallucination
        print("\n[TEST 3] Verifying no dowry hallucination...")
        crime_names = [c.crime_name.lower() for c in analysis.identified_crimes]
        
        if any('dowry' in name for name in crime_names):
            print("[FAIL] Dowry detected in crimes (hallucination)")
            print(f"  Crime names: {crime_names}")
            return False
        else:
            print("[OK] No dowry hallucination detected")
        
        # Verify correct crimes are identified
        print("\n[TEST 4] Verifying correct crimes...")
        expected_concepts = ['assault', 'intimidation', 'hurt', 'threat', 'violence']
        
        found_relevant = False
        for crime in analysis.identified_crimes:
            crime_lower = crime.crime_name.lower()
            if any(exp in crime_lower for exp in expected_concepts):
                found_relevant = True
                print(f"  [OK] Found relevant crime: {crime.crime_name}")
        
        if not found_relevant:
            print("[WARN] No assault/violence related crimes identified")
        
        print("\n" + "=" * 80)
        print("ASSAULT CASE TEST PASSED [OK]")
        print("=" * 80)
        
        return True
        
    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_assault_case()
    exit(0 if success else 1)
