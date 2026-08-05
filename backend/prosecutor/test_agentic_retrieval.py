"""
Test script for Agentic IPC Retrieval Service

This script demonstrates the new agentic retrieval pipeline with self-correction loops.
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Add parent directory to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from prosecutor.services.agentic_ipc_retrieval_service import AgenticIPCRetrievalService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

logger = logging.getLogger(__name__)

def test_criminal_intimidation_case():
    """Test with the criminal intimidation land dispute case"""
    print("\n" + "="*80)
    print("TEST 1: Criminal Intimidation (Land Dispute)")
    print("="*80 + "\n")
    
    full_query = (
        "The applicant seeks anticipatory bail after an FIR alleges that he threatened "
        "the complainant with death over a long-standing land dispute, causing fear and "
        "preventing the complainant from accessing the property; the applicant denies "
        "the allegations, claims they are exaggerated, and has cooperated with the investigation."
    )
    
    sub_queries = [
        "Threatened the complainant with death.",
        "Criminal intimidation by threatening to cause death.",
        "Threat caused fear and alarm to the complainant.",
        "Threat prevented the complainant from accessing the disputed property."
    ]
    
    # Initialize service
    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    service = AgenticIPCRetrievalService(client)
    
    # Run retrieval
    results = service.retrieve_sections(
        sub_queries=sub_queries,
        full_query=full_query,
        max_retries_per_query=2
    )
    
    # Print results
    print_results(results)


def test_sexual_harassment_case():
    """Test with the sexual harassment case from your output"""
    print("\n" + "="*80)
    print("TEST 2: Sexual Harassment (Workplace)")
    print("="*80 + "\n")
    
    full_query = (
        "The applicant seeks anticipatory bail after an FIR alleges that he repeatedly "
        "subjected a female colleague to unwelcome physical advances, inappropriate messages, "
        "and threats affecting her employment after she rejected his advances; the applicant "
        "denies the allegations, claims the complaint is retaliatory, and has cooperated "
        "with the investigation."
    )
    
    sub_queries = [
        "The applicant allegedly subjected a female colleague to unwelcome physical advances, "
        "inappropriate messages, and threats affecting her employment after she rejected his advances.",
        "Stalking and following woman repeatedly or monitoring electronic communication",
        "Cyber stalking and sending threatening electronic messages to woman",
        "Criminal intimidation and persistent unwanted following of female victim"
    ]
    
    # Initialize service
    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    service = AgenticIPCRetrievalService(client)
    
    # Run retrieval
    results = service.retrieve_sections(
        sub_queries=sub_queries,
        full_query=full_query,
        max_retries_per_query=2
    )
    
    # Print results
    print_results(results)


def print_results(results):
    """Pretty print the retrieval results"""
    print(f"\n{'='*80}")
    print(f"FINAL RESULTS: {len(results)} validated sections")
    print(f"{'='*80}\n")
    
    if not results:
        print("❌ No sections retrieved\n")
        return
    
    for idx, r in enumerate(results, 1):
        print(f"{idx}. {r['section']}")
        print(f"   Act: {r.get('act', 'N/A')}")
        print(f"   Section Number: {r.get('section_num', 'N/A')}")
        print(f"   Description: {r.get('description', 'N/A')[:150]}...")
        print(f"   Offense: {r.get('offense', 'N/A')[:100]}...")
        print(f"   Punishment: {r.get('punishment', 'N/A')[:100]}...")
        
        if 'verification' in r:
            print(f"   ✅ Verification:")
            print(f"      Confidence: {r['verification'].get('confidence', 0.0):.2f}")
            print(f"      Reasoning: {r['verification'].get('reasoning', 'N/A')[:150]}...")
        
        if 'ingredients' in r and r['ingredients']:
            print(f"   Ingredients: {len(r['ingredients'])} total")
            for ing in r['ingredients'][:3]:  # Show first 3
                print(f"      - {ing}")
        
        print()


def main():
    """Run all tests"""
    print("\n" + "#"*80)
    print("# AGENTIC IPC RETRIEVAL SERVICE - TEST SUITE")
    print("#"*80)
    
    try:
        # Test 1: Criminal intimidation
        test_criminal_intimidation_case()
        
        # Test 2: Sexual harassment  
        test_sexual_harassment_case()
        
        print("\n" + "#"*80)
        print("# ALL TESTS COMPLETED")
        print("#"*80 + "\n")
        
    except Exception as e:
        logger.error(f"\n❌ Test failed with error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
