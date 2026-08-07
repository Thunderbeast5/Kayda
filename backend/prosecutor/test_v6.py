"""
Test Script for Prosecutor Agent V6
====================================
Tests the multi-stage reasoning with RL loops
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from prosecutor.prosecutor_agent_v6 import ProsecutorAgentV6


def test_dowry_case():
    """Test with dowry threat case."""
    print("\n" + "="*90)
    print("TEST 1: DOWRY THREAT CASE")
    print("="*90 + "\n")
    
    query = """
    A man threatened his wife for dowry demanding Rs. 5 lakhs and gold jewelry.
    When she refused, he beat her severely causing injuries and threatened to kill her
    if she did not bring the money. He also went to her parents' house and threatened
    them with dire consequences. The wife filed a complaint with the police station
    alleging cruelty, criminal intimidation, and demand for dowry.
    """
    
    agent = ProsecutorAgentV6()
    result = agent.process_query(query)
    
    print("\n" + "="*90)
    print("RESULTS")
    print("="*90)
    
    for res in result.get("retrieval_results", []):
        query_text = res['query']
        if len(query_text) > 80:
            query_text = query_text[:77] + "..."
        
        print(f"\nQuery: {query_text}")
        print(f"Type: {res['sub_query_type']}")
        print(f"Matches: {len(res['matches'])}")
        
        for i, match in enumerate(res['matches'][:10], 1):
            meta = match['metadata']
            print(f"\n  {i}. {match['id']} (score: {match['score']:.3f})")
            print(f"     Title: {meta.get('title', '')[:70]}")
            print(f"     Ingredient: {meta.get('ingredient', '')[:70]}")
            print(f"     Reasoning: {meta.get('reasoning', '')[:100]}")


def test_assault_case():
    """Test with assault case."""
    print("\n" + "="*90)
    print("TEST 2: ASSAULT CASE")
    print("="*90 + "\n")
    
    query = """
    The accused voluntarily caused grievous hurt to the complainant by hitting him
    with an iron rod on the head, causing fracture of skull. The attack was
    premeditated and done with intent to cause death. Multiple witnesses saw the
    incident. The complainant is hospitalized in critical condition.
    """
    
    agent = ProsecutorAgentV6()
    result = agent.process_query(query)
    
    print("\n" + "="*90)
    print("RESULTS")
    print("="*90)
    
    for res in result.get("retrieval_results", []):
        if "[MERGED]" in res['query']:
            print(f"\nMERGED RESULTS: {len(res['matches'])} sections")
            for i, match in enumerate(res['matches'][:5], 1):
                meta = match['metadata']
                print(f"  {i}. {match['id']}: {meta.get('title', '')[:60]}")


def test_cheating_case():
    """Test with cheating case."""
    print("\n" + "="*90)
    print("TEST 3: CHEATING/FRAUD CASE")
    print("="*90 + "\n")
    
    query = """
    The accused dishonestly induced the complainant to deliver Rs. 10 lakhs by
    falsely promising to deliver land property. He created fake documents showing
    ownership of the land. When the complainant discovered the fraud, the accused
    threatened him and refused to return the money. The accused has been absconding
    since the complaint was filed.
    """
    
    agent = ProsecutorAgentV6()
    result = agent.process_query(query)
    
    print("\n" + "="*90)
    print("RESULTS")
    print("="*90)
    
    for res in result.get("retrieval_results", []):
        if "[MERGED]" in res['query']:
            print(f"\nFinal sections: {len(res['matches'])}")
            for match in res['matches'][:8]:
                meta = match['metadata']
                print(f"  - {match['id']}: {meta.get('title', '')[:65]}")


if __name__ == "__main__":
    print("\n" + "#"*90)
    print("PROSECUTOR AGENT V6 - TEST SUITE")
    print("#"*90)
    
    # Run all tests
    test_dowry_case()
    print("\n" + "-"*90 + "\n")
    
    test_assault_case()
    print("\n" + "-"*90 + "\n")
    
    test_cheating_case()
    
    print("\n" + "#"*90)
    print("ALL TESTS COMPLETE")
    print("#"*90 + "\n")
