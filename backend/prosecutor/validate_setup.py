"""
Validation script to confirm all imports and basic setup work correctly
without actually running the full pipeline (which requires external services)
"""
import sys
from pathlib import Path

# Add parent directory to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

print("=" * 80)
print("PROSECUTOR AGENT SETUP VALIDATION")
print("=" * 80)
print()

# Test 1: Import lexigraph_agent
print("Test 1: Importing lexigraph_agent...")
try:
    from lexigraph_agent import LexiGraphAgent
    print("  ✓ LexiGraphAgent class imported successfully")
except ImportError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# Test 2: Import prosecutor_agent
print("\nTest 2: Importing prosecutor_agent...")
try:
    from prosecutor_agent import ProsecutorAgent, ProsecutorTurnResult
    print("  ✓ ProsecutorAgent class imported successfully")
    print("  ✓ ProsecutorTurnResult dataclass imported successfully")
except ImportError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# Test 3: Check anthropic import
print("\nTest 3: Checking anthropic library...")
try:
    import anthropic
    print("  ✓ anthropic library is installed")
except ImportError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# Test 4: Check config modules
print("\nTest 4: Checking config modules...")
try:
    from agents.config.llm_config import get_llm
    print("  ✓ agents.config.llm_config accessible")
except ImportError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

try:
    from agents.config.retrieval_config import (
        PINECONE_TOP_K, FILTER_TOP_K, GRAPH_TOP_K,
        COMMUNITY_TOP_K, RERANK_TOP_K, FINAL_OUTPUT_TOP_K
    )
    print("  ✓ agents.config.retrieval_config accessible")
    print(f"    - PINECONE_TOP_K: {PINECONE_TOP_K}")
    print(f"    - FINAL_OUTPUT_TOP_K: {FINAL_OUTPUT_TOP_K}")
except ImportError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# Test 5: Verify class instantiation (without external connections)
print("\nTest 5: Verifying class structure...")
try:
    # Check if LexiGraphAgent has expected methods
    assert hasattr(LexiGraphAgent, 'process_query'), "LexiGraphAgent missing process_query method"
    assert hasattr(LexiGraphAgent, 'render_context_for_agent'), "LexiGraphAgent missing render_context_for_agent method"
    assert hasattr(LexiGraphAgent, 'verify_claims'), "LexiGraphAgent missing verify_claims method"
    print("  ✓ LexiGraphAgent has all expected methods")
    
    # Check if ProsecutorAgent has expected methods
    assert hasattr(ProsecutorAgent, 'generate_turn'), "ProsecutorAgent missing generate_turn method"
    print("  ✓ ProsecutorAgent has all expected methods")
    
except AssertionError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("✅ ALL TESTS PASSED!")
print("=" * 80)
print()
print("The import errors have been successfully resolved.")
print()
print("Next steps:")
print("  1. Ensure your .env file has the required API keys:")
print("     - ANTHROPIC_API_KEY")
print("     - PINECONE_API_KEY")
print("     - NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD")
print()
print("  2. To run the full prosecutor agent:")
print("     python prosecutor_agent.py")
print()
print("  3. To run the lexigraph agent:")
print("     python lexigraph_agent.py")
print()
