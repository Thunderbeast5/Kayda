import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = BASE_DIR / "backend" / ".env" if (BASE_DIR / "backend" / ".env").exists() else BASE_DIR / ".env"
load_dotenv(ENV_PATH)

# Add backend directory to sys.path
sys.path.insert(0, str(BASE_DIR / "backend"))
sys.path.insert(0, str(BASE_DIR / "backend" / "agents" / "lexigraph" / "cypher"))

from agents.lexigraph.cypher.legal_text2cypher.utils.neo4j_utils import fulltext_search_sections, run_cypher

print("=" * 80)
print(" END-TO-END APP SMOKE TEST FOR GRAPHRAG RETRIEVAL (BNS_8(1) & BNS_137(1))")
print("=" * 80 + "\n")

# 1. Smoke-test full-text search for BNS_137(1) via app retrieval helper
print("1. Full-Text Search via app helper `fulltext_search_sections('kidnapping')`:")
ft_hits = fulltext_search_sections("kidnapping", limit=5, min_score=0.1)

target_found_137 = False
for h in ft_hits:
    print(f"   * [{h['score']:.2f}] Node: {h['node_id']} ({h['act']} {h['section']}) | Title: '{h['title'][:60]}...'")
    if h['node_id'] in ['BNS_137', 'BNS_137(1)', 'BNS_137(1)(B)']:
        target_found_137 = True

print(f"   --> Hit BNS_137 / BNS_137(1) in production search helper? {'YES' if target_found_137 else 'NO'}\n")

# 2. Smoke-test full-text search for BNS_8(1) via app retrieval helper
print("2. Full-Text Search via app helper `fulltext_search_sections('fine')`:")
ft_fine_hits = fulltext_search_sections("fine", limit=5, min_score=0.1)

target_found_8 = False
for h in ft_fine_hits:
    print(f"   * [{h['score']:.2f}] Node: {h['node_id']} ({h['act']} {h['section']}) | Title: '{h['title'][:60]}...'")
    if h['node_id'] in ['BNS_8', 'BNS_8(1)', 'BNS_8(6)']:
        target_found_8 = True

print(f"   --> Hit BNS_8 / BNS_8(1) in production search helper? {'YES' if target_found_8 else 'NO'}\n")

# 3. Smoke-test End-to-End Cypher Context Retrieval Query for BNS_8(1) and BNS_137(1)
print("3. End-to-End Production Cypher Traversal for Subsections (BNS_8(1) & BNS_137(1)):")
context_query = """
    MATCH (parent:LawSection)-[h:HAS_SUBSECTION|HAS_CLAUSE]->(child:LawSection)
    WHERE child.id IN ['BNS_8(1)', 'BNS_137(1)', 'BNS_137(1)(B)']
    OPTIONAL MATCH (child)-[r_kw:HAS_KEYWORD]->(k:Keyword)
    OPTIONAL MATCH (child)-[r_p:HAS_PUNISHMENT]->(p:Punishment)
    RETURN child.id AS child_id,
           child.title AS child_title,
           parent.id AS parent_id,
           parent.title AS parent_title,
           collect(DISTINCT k.name)[..3] AS keywords,
           collect(DISTINCT p.description)[..1] AS punishments
"""
context_results = run_cypher(context_query)

for r in context_results:
    print(f"   * Subsection: {r['child_id']}")
    print(f"     - Title               : '{r['child_title']}'")
    print(f"     - Parent              : {r['parent_id']} ('{r['parent_title']}')")
    print(f"     - Inherited Keywords  : {r['keywords']}")
    print(f"     - Inherited Punishment: {r['punishments']}")
    print()

print("=" * 80)
print(" APP END-TO-END SMOKE TEST COMPLETE")
print("=" * 80)
