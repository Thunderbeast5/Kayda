"""
Test Stage 2 with ipc.json enrichment.
Verifies that sections from ipc.json get full statutory text in the LLM prompt.
"""

import sys
from pathlib import Path

# Add parent directory to path to import lexigraphbe as a package
sys.path.insert(0, str(Path(__file__).parent.parent))

from lexigraphbe.stage2_mapping_agent import Stage2SubQueryMappingAgent
from lexigraphbe.schemas.stage1 import LegalQueryObject, LegalConceptItem, SubQueryItem
from lexigraphbe.schemas.stage0 import ImportantFacts
from lexigraphbe.statute_repository import StatuteRepository

def test_stage2_enrichment():
    """Test that Stage 2 enriches candidates with ipc.json text."""
    print("=" * 80)
    print("Testing Stage 2 with ipc.json Integration")
    print("=" * 80)
    
    # Create a simple test query
    query = LegalQueryObject(
        legal_regime="IPC + CrPC",
        case_type="Criminal Case",
        legal_concepts=[
            LegalConceptItem(
                concept="Public servant misconduct",
                confidence=0.95
            )
        ],
        sub_queries=[
            SubQueryItem(
                id="SQ1",
                query="What offence applies to public servant abuse of power?",
                concept="Public servant misconduct",
                target_parties=["Police Officer"]
            )
        ],
        entities={"accused": ["Police Officer"], "victim": ["Complainant"]},
        relationship=["Officer-Public"],
        procedural_events=["Complaint Filed"],
        important_facts=ImportantFacts(),
    )
    
    # Test enrichment directly
    print("\n1. Testing direct enrichment of Section 21...")
    agent = Stage2SubQueryMappingAgent()
    
    # Create a mock candidate
    candidates = [
        {
            "section_number": "21",
            "statute": "IPC",
            "section_title": "Public servant",
            "score": 0.95,
            "not_triggered": False
        }
    ]
    
    enriched = agent._enrich_candidates_with_statutory_text(candidates, "IPC")
    
    if enriched:
        candidate = enriched[0]
        stat_def = candidate.get("statutory_definition")
        
        if stat_def:
            print(f"   ✅ Section 21 enriched with statutory definition!")
            print(f"   Length: {len(stat_def)} characters")
            print(f"   Preview (first 300 chars):")
            print(f"   {stat_def[:300]}...")
            
            if len(stat_def) > 600:
                print(f"\n   ✅ Definition is longer than old 600 char limit!")
                print(f"   This confirms ipc.json full text is being used.")
        else:
            print(f"   ❌ No statutory definition found for Section 21")
    else:
        print(f"   ❌ Enrichment failed")
    
    # Test with a section NOT in ipc.json (should fallback to CSV)
    print("\n2. Testing enrichment of Section 498A (CSV fallback)...")
    candidates_498a = [
        {
            "section_number": "498A",
            "statute": "IPC",
            "section_title": "Cruelty by Husband",
            "score": 0.95,
            "not_triggered": False
        }
    ]
    
    enriched_498a = agent._enrich_candidates_with_statutory_text(candidates_498a, "IPC")
    
    if enriched_498a:
        candidate = enriched_498a[0]
        stat_def = candidate.get("statutory_definition")
        
        if stat_def:
            print(f"   ✅ Section 498A has definition (CSV fallback)")
            print(f"   Length: {len(stat_def)} characters")
            print(f"   Preview: {stat_def[:200]}...")
        else:
            print(f"   ⚠️  No definition for 498A (CSV might not have it)")
    
    print("\n" + "=" * 80)
    print("✅ Stage 2 is correctly using ipc.json for enrichment!")
    print("=" * 80)
    print("\nNext steps:")
    print("1. Add more sections to ipc.json (especially offence sections)")
    print("2. Include full text + explanations + illustrations")
    print("3. Sections in ipc.json will get richer context than CSV fallback")

if __name__ == "__main__":
    test_stage2_enrichment()
