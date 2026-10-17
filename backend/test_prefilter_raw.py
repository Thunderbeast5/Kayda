"""
Direct prefilter test with hardcoded Stage 1 output - minimal token usage.
"""
from lexigraphbe.classifier_prefilter import StatuteClassifierPrefilter
from lexigraphbe.schemas.stage1 import LegalQueryObject, LegalConceptItem, SubQueryItem, ImportantFacts

# Hardcoded Stage 1 output based on your run
query_obj = LegalQueryObject(
    case_type="Anticipatory Bail",
    legal_concepts=[
        LegalConceptItem(
            concept_id="LC1",
            concept="Causing death by negligence — failure to monitor patient condition and arrange specialist intervention",
            description="",
            confidence=0.85
        ),
        LegalConceptItem(
            concept_id="LC2",
            concept="Falsification of accounts — alteration of medical record entries",
            description="",
            confidence=0.80
        ),
        LegalConceptItem(
            concept_id="LC3",
            concept="Destruction of document to prevent its production as evidence — destruction of internal monitoring records",
            description="",
            confidence=0.75
        ),
        LegalConceptItem(
            concept_id="LC4",
            concept="Abetment — instruction to junior staff not to disclose sequence of events",
            description="",
            confidence=0.70
        ),
        LegalConceptItem(
            concept_id="LC5",
            concept="Anticipatory bail — grounds for custodial interrogation and witness influence risk",
            description="",
            confidence=0.65
        ),
    ],
    sub_queries=[
        SubQueryItem(
            id="SQ1",
            query="What evidence supports the allegation that the senior medical officer ignored warnings about the patient's deteriorating condition and failed to arrange timely specialist intervention?",
            concept="Causing death by negligence",
            concept_id="LC1",
            fact_ids=["F1"],
            confidence=0.85
        ),
        SubQueryItem(
            id="SQ2",
            query="What evidence supports the allegation that the senior medical officer falsified medical records?",
            concept="Falsification of accounts",
            concept_id="LC2",
            fact_ids=["F2"],
            confidence=0.80
        ),
        SubQueryItem(
            id="SQ3",
            query="What evidence supports the allegation that the senior medical officer and hospital administrator destroyed internal monitoring records?",
            concept="Destruction of document to prevent its production as evidence",
            concept_id="LC3",
            fact_ids=["F3"],
            confidence=0.75
        ),
        SubQueryItem(
            id="SQ4",
            query="What evidence supports the allegation that the senior medical officer instructed junior staff not to disclose the actual sequence of events?",
            concept="Abetment",
            concept_id="LC4",
            fact_ids=["F4"],
            confidence=0.70
        ),
        SubQueryItem(
            id="SQ5",
            query="What are the grounds for the prosecution's opposition to anticipatory bail regarding custodial interrogation and witness influence?",
            concept="Anticipatory bail grounds",
            concept_id="LC5",
            fact_ids=["F5"],
            confidence=0.65
        ),
    ],
    important_facts=ImportantFacts(),
    legal_regime="IPC + CrPC"
)

print("="*80)
print("PREFILTER RAW SCORES - MEDICAL NEGLIGENCE CASE")
print("="*80)

# Run prefilter with expanded parameters
prefilter = StatuteClassifierPrefilter()
matches = prefilter.retrieve_for_legal_query(
    query_obj,
    statute_type="IPC",
    top_k=50,
    per_concept=8
)

print(f"\nTotal matches: {len(matches)}\n")
print("="*80)
print(f"{'Rank':<6} {'Section':<10} {'Score':<8} {'Title':<55}")
print("-" * 80)

for idx, m in enumerate(matches, 1):
    sec_num = getattr(m, "section_number", "")
    score = getattr(m, "score", 0.0)
    title = getattr(m, "title", getattr(m, "section_title", ""))[:53]
    print(f"{idx:<6} {sec_num:<10} {score:<8.4f} {title}")

# Check specific sections
print("\n" + "="*80)
print("SECTIONS OF INTEREST CHECK")
print("="*80)

sections_of_interest = [
    ("192", "Fabricating false evidence"),
    ("193", "Punishment for false evidence"),
    ("202", "Intentional omission to give information"),
    ("203", "Giving false information"),
    ("204", "Destruction of document to prevent production"),
    ("463", "Forgery"),
    ("464", "Making a false document"),
    ("465", "Punishment for forgery"),
    ("466", "Forgery of record of court"),
    ("467", "Forgery of valuable security"),
    ("468", "Forgery for purpose of cheating"),
    ("471", "Using as genuine a forged document"),
    ("420", "Cheating"),
    ("34", "Common intention"),
    ("109", "Abetment"),
    ("120A", "Definition of criminal conspiracy"),
    ("120B", "Punishment of criminal conspiracy"),
]

found_sections = {getattr(m, "section_number", ""): (idx, getattr(m, "score", 0.0)) 
                  for idx, m in enumerate(matches, 1)}

print(f"\n{'Section':<10} {'Description':<45} {'Status':<12} {'Rank':<6} {'Score'}")
print("-" * 85)

for sec, desc in sections_of_interest:
    if sec in found_sections:
        rank, score = found_sections[sec]
        status = "TOP 20" if rank <= 20 else "FOUND"
        print(f"{sec:<10} {desc:<45} {status:<12} {rank:<6} {score:.4f}")
    else:
        print(f"{sec:<10} {desc:<45} {'MISSING':<12} {'N/A':<6} {'N/A'}")

# Summary
print("\n" + "="*80)
print("SUMMARY")
print("="*80)

missing = [s for s, _ in sections_of_interest if s not in found_sections]
low_ranked = [(s, d, rank, score) for (s, d) in sections_of_interest 
              if s in found_sections and (rank := found_sections[s][0]) > 20
              and (score := found_sections[s][1])]
top_20 = [(s, d, rank, score) for (s, d) in sections_of_interest 
          if s in found_sections and (rank := found_sections[s][0]) <= 20
          and (score := found_sections[s][1])]

print(f"\n✓ In top 20: {len(top_20)}")
for s, d, rank, score in sorted(top_20, key=lambda x: x[2]):
    print(f"    [{rank:2d}] {s}: {score:.4f}")

print(f"\n⚠ Ranked 21-50: {len(low_ranked)}")
for s, d, rank, score in sorted(low_ranked, key=lambda x: x[2]):
    print(f"    [{rank:2d}] {s}: {score:.4f}")

print(f"\n✗ Not retrieved: {len(missing)}")
for s in missing:
    print(f"    {s}")

print("\n" + "="*80)
if missing:
    print("DIAGNOSIS: KB/query issue - sections not being matched by BM25")
elif low_ranked:
    print("DIAGNOSIS: Ranking issue - sections found but scored too low")
else:
    print("DIAGNOSIS: Post-retrieval filtering issue")
print("="*80)
