"""
Dump raw prefilter scores for medical negligence case to diagnose missing sections.
"""
import sys
from lexigraphbe.classifier_prefilter import StatuteClassifierPrefilter
from lexigraphbe.runner import run_stage0, run_stage1

# Medical negligence test case
text = """The applicant, a senior medical officer at a private hospital, seeks anticipatory bail after an FIR was registered following the death of a patient who underwent emergency surgery at the hospital. The complainant, a relative of the deceased, alleges that the applicant deliberately ignored repeated warnings regarding the patient's deteriorating condition, failed to arrange timely specialist intervention, and falsified certain entries in the medical records to conceal negligence. The FIR further alleges that the applicant, along with the hospital administrator, destroyed internal monitoring records and instructed junior staff members not to disclose the actual sequence of events. The applicant denies these allegations and submits that the patient was admitted in a critical condition, all necessary medical procedures were followed, and the death resulted from complications that could not have been reasonably anticipated. The applicant contends that the allegations arise from a medical dispute and that criminal liability cannot be imposed merely because a treatment was unsuccessful. The applicant has already provided medical records and cooperated with the investigating agency. The prosecution opposes anticipatory bail, arguing that the alleged manipulation of hospital records requires custodial interrogation and that the applicant may influence hospital employees who are material witnesses."""

print("="*80)
print("RAW PREFILTER SCORES DIAGNOSTIC")
print("="*80)

# Run Stage 0 and Stage 1 to get LegalQueryObject
print("\n[1] Running Stage 0 (Intake)...")
stage0_res = run_stage0(text)

print("[2] Running Stage 1 (Query Deconstruction)...")
stage1_dict = run_stage1(stage0_res)

# Extract the query object
from lexigraphbe.schemas.stage1 import LegalQueryObject
stage1_res = stage1_dict.get("verified_query_object") or LegalQueryObject.model_validate(stage1_dict)

print(f"\n[3] Legal concepts identified: {len(stage1_res.legal_concepts)}")
for lc in stage1_res.legal_concepts:
    print(f"    - {lc.concept}")

print(f"\n[4] Sub-queries identified: {len(stage1_res.sub_queries)}")
for sq in stage1_res.sub_queries:
    print(f"    - SQ{sq.id}: {sq.query[:80]}...")

# Run prefilter with expanded parameters
print("\n" + "="*80)
print("[5] Running prefilter with top_k=50, per_concept=8")
print("="*80)

prefilter = StatuteClassifierPrefilter()
matches = prefilter.retrieve_for_legal_query(
    stage1_res,
    statute_type="IPC",
    top_k=50,
    per_concept=8
)

print(f"\nTotal matches retrieved: {len(matches)}")
print("\n" + "="*80)
print("RANKED RESULTS (all scores)")
print("="*80)
print(f"{'Rank':<6} {'Section':<10} {'Score':<8} {'Title':<60}")
print("-" * 84)

for idx, m in enumerate(matches, 1):
    sec_num = getattr(m, "section_number", "")
    score = getattr(m, "score", 0.0)
    title = getattr(m, "title", getattr(m, "section_title", ""))[:58]
    print(f"{idx:<6} {sec_num:<10} {score:<8.4f} {title}")

# Check for specific sections of interest
print("\n" + "="*80)
print("CHECKING SPECIFIC SECTIONS OF INTEREST")
print("="*80)

sections_of_interest = [
    "192", "193", "202", "203", "204",  # False evidence / document destruction
    "463", "464", "465", "466", "467", "468", "471",  # Forgery chain
    "420",  # Cheating
    "34", "109", "120A", "120B"  # Conspiracy / common intention
]

found_sections = {getattr(m, "section_number", ""): (idx, getattr(m, "score", 0.0)) 
                  for idx, m in enumerate(matches, 1)}

print(f"\n{'Section':<10} {'Status':<15} {'Rank':<8} {'Score'}")
print("-" * 50)

for sec in sections_of_interest:
    if sec in found_sections:
        rank, score = found_sections[sec]
        print(f"{sec:<10} {'FOUND':<15} {rank:<8} {score:.4f}")
    else:
        print(f"{sec:<10} {'NOT RETRIEVED':<15} {'N/A':<8} {'N/A'}")

# Also show what concepts matched each section
print("\n" + "="*80)
print("CONCEPT MATCHING DETAILS (Top 20)")
print("="*80)

for idx, m in enumerate(matches[:20], 1):
    sec_num = getattr(m, "section_number", "")
    title = getattr(m, "title", getattr(m, "section_title", ""))
    score = getattr(m, "score", 0.0)
    
    # Try to get matched concepts if available
    matched_concepts = getattr(m, "matched_concepts", [])
    matched_terms = getattr(m, "matched_terms", [])
    
    print(f"\n[{idx}] Section {sec_num}: {title}")
    print(f"    Score: {score:.4f}")
    if matched_concepts:
        print(f"    Concepts: {matched_concepts[:3]}")
    if matched_terms:
        print(f"    Terms: {matched_terms[:10]}")

print("\n" + "="*80)
print("DIAGNOSTIC SUMMARY")
print("="*80)

missing = [s for s in sections_of_interest if s not in found_sections]
low_ranked = [(s, rank, score) for s, (rank, score) in found_sections.items() 
              if s in sections_of_interest and rank > 20]
retrieved = [(s, rank, score) for s, (rank, score) in found_sections.items() 
             if s in sections_of_interest and rank <= 20]

print(f"\n✓ Retrieved in top 20: {len(retrieved)}")
for s, rank, score in sorted(retrieved, key=lambda x: x[1]):
    print(f"    {s}: rank {rank}, score {score:.4f}")

print(f"\n⚠ Retrieved but low-ranked (21-50): {len(low_ranked)}")
for s, rank, score in sorted(low_ranked, key=lambda x: x[1]):
    print(f"    {s}: rank {rank}, score {score:.4f}")

print(f"\n✗ Not retrieved at all: {len(missing)}")
for s in sorted(missing):
    print(f"    {s}")

print("\n" + "="*80)
print("DIAGNOSIS:")
if missing:
    print("Issue: KB content or query formulation (sections not being matched)")
elif low_ranked:
    print("Issue: Ranking algorithm (sections found but scored too low)")
else:
    print("Issue: Post-retrieval gates (sections filtered after retrieval)")
print("="*80)
