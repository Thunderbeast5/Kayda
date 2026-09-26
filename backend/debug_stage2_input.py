"""
Debug script to show EXACTLY what is sent to the Stage 2 LLM.
Runs only the prefilter + enrichment, then prints the prompt that would be sent to the LLM.
"""

import sys
import json
from lexigraphbe.stage2_mapping_agent import Stage2SubQueryMappingAgent
from lexigraphbe.schemas.stage1 import LegalQueryObject, LegalConceptItem, SubQueryItem
from lexigraphbe.statute_repository import StatuteRepository
from lexigraphbe.prompts import STAGE2_MAPPING_SYSTEM_PROMPT, STAGE2_MAPPING_USER_PROMPT_TEMPLATE

# Reset repository to ensure fresh load
StatuteRepository.reset_instance()

# Sample query - you can change this
query_text = input("Enter your case text: ").strip() or "The applicant seeks anticipatory bail after an FIR alleges that he forged ownership documents of agricultural land, executed a fraudulent sale deed, and dishonestly transferred the property to a third party."

# Create a mock Stage 1 output
legal_query = LegalQueryObject(
    legal_regime="IPC + CrPC",
    legal_concepts=[
        LegalConceptItem(concept="Forgery", confidence=0.95),
        LegalConceptItem(concept="Fraudulent Sale Deed", confidence=0.95),
        LegalConceptItem(concept="Dishonest Transfer", confidence=0.90)
    ],
    sub_queries=[
        SubQueryItem(
            id="SQ1",
            query="The applicant forged ownership documents",
            concept="Forgery",
            target_parties=["Applicant"]
        ),
        SubQueryItem(
            id="SQ2", 
            query="The applicant executed a fraudulent sale deed",
            concept="Fraudulent Sale Deed",
            target_parties=["Applicant"]
        )
    ]
)

print("\n" + "="*80)
print("STAGE 2 DEBUG - WHAT GETS SENT TO THE LLM")
print("="*80)

# Initialize Stage 2 agent
agent = Stage2SubQueryMappingAgent()

# Extract facts text (same logic as Stage 2 agent)
facts_text_parts = []
for concept_item in legal_query.legal_concepts:
    if concept_item.concept:
        facts_text_parts.append(concept_item.concept)
for sq in legal_query.sub_queries:
    facts_text_parts.append(sq.query)
    if sq.concept:
        facts_text_parts.append(sq.concept)
facts_text = " ".join(facts_text_parts)

print(f"\n1. FACTS TEXT EXTRACTED:")
print(f"   {facts_text}")

# Run prefilter (0 API calls, pure keyword matching)
print(f"\n2. RUNNING PREFILTER (keyword matching)...")
regime = legal_query.legal_regime or "IPC + CrPC"
statute_type = "BNS" if "BNS" in regime.upper() else "IPC"

prefiltered_matches = []
for concept_item in legal_query.legal_concepts:
    matches = agent.prefilter.prefilter_candidates(
        query_text=concept_item.concept,
        statute_type=statute_type,
        top_k=10,
    )
    prefiltered_matches.extend(matches)

print(f"\n3. PREFILTER RETURNED {len(prefiltered_matches)} CANDIDATES:")
for i, match in enumerate(prefiltered_matches[:15], 1):
    print(f"   {i:2d}. Section {match.section_number:4s} - {match.title[:60]:60s} (score: {match.score})")

# Deduplicate
from collections import OrderedDict
dedup_dict = OrderedDict()
for m in prefiltered_matches:
    key = f"{m.statute}_{m.section_number}"
    if key not in dedup_dict:
        dedup_dict[key] = {
            "section_number": m.section_number,
            "statute": m.statute,
            "title": m.title,
            "score": m.score,
            "not_triggered": False,
            "not_triggered_reason": None,
        }

print(f"\n4. AFTER DEDUPLICATION: {len(dedup_dict)} UNIQUE SECTIONS")

# Run scope check on borderline candidates
print(f"\n5. RUNNING SCOPE CHECKS ON BORDERLINE CANDIDATES...")
_SCOPE_CHECK_SCORE_CEILING = 0.85
checked_count = 0
for k, candidate in dedup_dict.items():
    if candidate.get("not_triggered"):
        continue
    if candidate.get("score", 1.0) >= _SCOPE_CHECK_SCORE_CEILING:
        continue
    
    checked_count += 1
    sec_num = candidate["section_number"]
    statute = candidate["statute"]
    
    print(f"   Checking Section {sec_num} {statute} (score {candidate['score']})...")
    compatible, reason = agent._check_scope_compatibility(
        section_number=sec_num,
        statute=statute,
        facts_text=facts_text,
    )
    if not compatible:
        candidate["not_triggered"] = True
        candidate["not_triggered_reason"] = f"Definition-grounded scope check: {reason}"
        print(f"      → REJECTED: {reason}")
    else:
        print(f"      → PASSED: {reason}")

print(f"\n   Total scope checks performed: {checked_count}")

# Split active vs not_triggered
active_candidates = [c for c in dedup_dict.values() if not c.get("not_triggered")]
not_triggered_candidates = [c for c in dedup_dict.values() if c.get("not_triggered")]

print(f"\n6. AFTER SCOPE CHECKS:")
print(f"   Active candidates: {len(active_candidates)}")
print(f"   Not triggered: {len(not_triggered_candidates)}")

# Enrich with statutory definitions
print(f"\n7. ENRICHING ACTIVE CANDIDATES WITH STATUTORY DEFINITIONS...")
enriched = agent._enrich_candidates_with_statutory_text(active_candidates, statute_type)

print(f"\n8. ENRICHED CANDIDATES (what LLM sees):")
print(f"   Total: {len(enriched)}")
for i, cand in enumerate(enriched[:5], 1):
    print(f"\n   [{i}] Section {cand['section_number']} {cand['statute']} - {cand['title']}")
    stat_def = cand.get('statutory_definition', 'N/A')
    print(f"       Definition: {stat_def[:150]}..." if len(stat_def) > 150 else f"       Definition: {stat_def}")

# Build the actual prompt
query_json_str = legal_query.model_dump_json(indent=2)
prefilter_json_str = json.dumps(enriched, indent=2)

user_prompt = STAGE2_MAPPING_USER_PROMPT_TEMPLATE.format(
    legal_query_json=query_json_str,
    prefilter_candidates_json=prefilter_json_str,
    correction_feedback_section="",
)

print(f"\n" + "="*80)
print("FINAL PROMPT SENT TO LLM")
print("="*80)
print(f"\n--- SYSTEM PROMPT ({len(STAGE2_MAPPING_SYSTEM_PROMPT)} chars) ---")
print(STAGE2_MAPPING_SYSTEM_PROMPT[:500] + "...")

print(f"\n--- USER PROMPT ({len(user_prompt)} chars) ---")
print(user_prompt[:1000])
print("\n...")
print(user_prompt[-500:])

print(f"\n" + "="*80)
print(f"TOTAL PROMPT SIZE: {len(STAGE2_MAPPING_SYSTEM_PROMPT) + len(user_prompt):,} characters")
print("="*80)

# Save full prompt to file
with open('stage2_llm_prompt.txt', 'w', encoding='utf-8') as f:
    f.write("="*80 + "\n")
    f.write("SYSTEM PROMPT\n")
    f.write("="*80 + "\n")
    f.write(STAGE2_MAPPING_SYSTEM_PROMPT)
    f.write("\n\n" + "="*80 + "\n")
    f.write("USER PROMPT\n")
    f.write("="*80 + "\n")
    f.write(user_prompt)

print(f"\nFull prompt saved to: stage2_llm_prompt.txt")
