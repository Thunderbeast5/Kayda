"""
Stage 2 Demo with hardcoded Stage 0/1 output for the medical negligence case.
Minimal token usage - only tests Stage 2 mapping.
"""
import json
from lexigraphbe.stage2_mapping_agent import Stage2SubQueryMappingAgent
from lexigraphbe.schemas.stage1 import (
    LegalQueryObject, 
    LegalConceptItem, 
    SubQueryItem, 
    FactualAllegation,
    ImportantFacts
)

print("="*80)
print("STAGE 2 DEMO - MEDICAL NEGLIGENCE CASE")
print("="*80)

# Hardcoded Stage 1 output based on your actual run
query_obj = LegalQueryObject(
    schema_version="2.0",
    case_type="Anticipatory Bail",
    entities={
        "applicant": ["senior medical officer"],
        "accused": ["senior medical officer", "hospital administrator"]
    },
    relationship=["hospital employment"],
    factual_allegations=[
        FactualAllegation(
            fact_id="F1",
            description="Senior medical officer ignored warnings about patient's deteriorating condition",
            actor="senior medical officer",
            affected_party_or_object="patient",
            conduct_type="OMISSION",
            factual_status="ALLEGED"
        ),
        FactualAllegation(
            fact_id="F2",
            description="Senior medical officer failed to arrange timely specialist intervention",
            actor="senior medical officer",
            affected_party_or_object="patient",
            conduct_type="OMISSION",
            factual_status="ALLEGED"
        ),
        FactualAllegation(
            fact_id="F3",
            description="Senior medical officer falsified entries in medical records",
            actor="senior medical officer",
            affected_party_or_object="medical records",
            conduct_type="ACT",
            factual_status="ALLEGED"
        ),
        FactualAllegation(
            fact_id="F4",
            description="Senior medical officer and hospital administrator destroyed internal monitoring records",
            actor="senior medical officer, hospital administrator",
            affected_party_or_object="internal monitoring records",
            conduct_type="ACT",
            factual_status="ALLEGED"
        ),
        FactualAllegation(
            fact_id="F5",
            description="Senior medical officer instructed junior staff not to disclose actual sequence of events",
            actor="senior medical officer",
            affected_party_or_object="junior staff",
            conduct_type="ACT",
            factual_status="ALLEGED"
        ),
    ],
    legal_concepts=[
        LegalConceptItem(
            concept_id="LC1",
            concept="Causing death by negligence — failure to arrange timely specialist intervention",
            description="Medical officer's omission to provide adequate care leading to patient death",
            supporting_fact_ids=["F1", "F2"],
            confidence=0.85
        ),
        LegalConceptItem(
            concept_id="LC2",
            concept="Falsification of accounts — falsification of entries in medical records",
            description="Deliberate alteration of medical documentation to conceal negligence",
            supporting_fact_ids=["F3"],
            confidence=0.80
        ),
        LegalConceptItem(
            concept_id="LC3",
            concept="Destruction of document to prevent its production as evidence — destruction of internal monitoring records",
            description="Intentional destruction of records to prevent evidence production",
            supporting_fact_ids=["F4"],
            confidence=0.75
        ),
        LegalConceptItem(
            concept_id="LC4",
            concept="Abetment — instruction to junior staff not to disclose sequence of events",
            description="Instigating others to conceal facts",
            supporting_fact_ids=["F5"],
            confidence=0.70
        ),
        LegalConceptItem(
            concept_id="LC5",
            concept="Anticipatory bail — grounds for opposing bail due to risk of influencing witnesses",
            description="Prosecution's concerns about witness tampering",
            supporting_fact_ids=[],
            confidence=0.65
        ),
    ],
    sub_queries=[
        SubQueryItem(
            id="SQ1",
            query="What evidence supports the allegation that the senior medical officer's failure to arrange timely specialist intervention caused the patient's death?",
            concept="Causing death by negligence",
            concept_id="LC1",
            fact_ids=["F1", "F2"],
            target_parties=["senior medical officer"],
            role_alleged="medical officer",
            conduct_type="OMISSION",
            confidence=0.85
        ),
        SubQueryItem(
            id="SQ2",
            query="What evidence supports the allegation of falsification of entries in the medical records by the senior medical officer?",
            concept="Falsification of accounts",
            concept_id="LC2",
            fact_ids=["F3"],
            target_parties=["senior medical officer"],
            role_alleged="medical officer",
            conduct_type="ACT",
            confidence=0.80
        ),
        SubQueryItem(
            id="SQ3",
            query="What evidence supports the allegation of destruction of internal monitoring records by the senior medical officer and hospital administrator?",
            concept="Destruction of document to prevent its production as evidence",
            concept_id="LC3",
            fact_ids=["F4"],
            target_parties=["senior medical officer", "hospital administrator"],
            conduct_type="ACT",
            confidence=0.75
        ),
        SubQueryItem(
            id="SQ4",
            query="What evidence supports the allegation of instruction to junior staff not to disclose the sequence of events?",
            concept="Abetment",
            concept_id="LC4",
            fact_ids=["F5"],
            target_parties=["senior medical officer"],
            role_alleged="medical officer",
            conduct_type="ACT",
            confidence=0.70
        ),
        SubQueryItem(
            id="SQ5",
            query="What are the grounds for opposing anticipatory bail based on the risk of influencing witnesses?",
            concept="Anticipatory bail grounds",
            concept_id="LC5",
            fact_ids=[],
            target_parties=["prosecution"],
            conduct_type="STATEMENT",
            confidence=0.65
        ),
    ],
    important_facts=ImportantFacts(
        location=["private hospital"],
        dates=["date of surgery", "date of death", "date of FIR"],
        medical_injury=["patient death", "deteriorating condition"],
        documents=["medical records", "internal monitoring records"],
        witnesses=["junior staff members", "hospital employees"]
    ),
    legal_regime="IPC + CrPC",
    flag_for_confirmation=False,
    verification_status="VERIFIED"
)

print("\n[Stage 0/1 Output - Hardcoded]")
print(f"  Legal Concepts: {len(query_obj.legal_concepts)}")
print(f"  Sub-Queries: {len(query_obj.sub_queries)}")
print(f"  Factual Allegations: {len(query_obj.factual_allegations)}")
print(f"  Legal Regime: {query_obj.legal_regime}")

print("\n" + "="*80)
print("RUNNING STAGE 2: SUB-QUERY TO SECTION MAPPING")
print("="*80)

# Create Stage 2 agent
stage2_agent = Stage2SubQueryMappingAgent()

# Run Stage 2
print("\n[Stage 2] Running batched sub-query mapping...")
stage2_result = stage2_agent.run(query_obj)

print("\n" + "="*80)
print("STAGE 2 RESULTS")
print("="*80)

print(f"\nTotal mappings: {len(stage2_result.mappings)}")

for mapping in stage2_result.mappings:
    print(f"\n{'='*80}")
    print(f"[{mapping.sub_query_id}] {mapping.sub_query_text[:80]}...")
    print(f"{'='*80}")
    
    print(f"\nTarget Parties: {', '.join(mapping.target_parties)}")
    
    if mapping.primary_candidate_sections:
        print(f"\n  PRIMARY CANDIDATES ({len(mapping.primary_candidate_sections)}):")
        for sec in mapping.primary_candidate_sections:
            print(f"    • Section {sec.section_number}: {sec.section_title}")
            print(f"      Score: {sec.score:.3f} | Type: {sec.candidate_type}")
            print(f"      Reasoning: {sec.relevance_reasoning[:100]}...")
    
    if mapping.secondary_candidate_sections:
        print(f"\n  SECONDARY CANDIDATES ({len(mapping.secondary_candidate_sections)}):")
        for sec in mapping.secondary_candidate_sections:
            print(f"    • Section {sec.section_number}: {sec.section_title}")
    
    if hasattr(mapping, 'conditional_candidate_sections') and mapping.conditional_candidate_sections:
        print(f"\n  CONDITIONAL CANDIDATES ({len(mapping.conditional_candidate_sections)}):")
        for sec in mapping.conditional_candidate_sections:
            print(f"    • Section {sec.section_number}: {sec.section_title}")
    
    if mapping.not_triggered_sections:
        print(f"\n  NOT TRIGGERED ({len(mapping.not_triggered_sections)}):")
        for sec in mapping.not_triggered_sections:
            print(f"    • Section {sec.section_number}: {sec.section_title}")
            if hasattr(sec, 'relevance_reasoning'):
                print(f"      Reason: {sec.relevance_reasoning[:80]}...")

# Collect all unique sections across mappings
print("\n" + "="*80)
print("ALL SECTIONS IDENTIFIED")
print("="*80)

all_sections = set()
for mapping in stage2_result.mappings:
    for sec in mapping.primary_candidate_sections:
        all_sections.add(sec.section_number)
    for sec in mapping.secondary_candidate_sections:
        all_sections.add(sec.section_number)
    if hasattr(mapping, 'conditional_candidate_sections'):
        for sec in mapping.conditional_candidate_sections or []:
            all_sections.add(sec.section_number)

print(f"\nTotal unique sections: {len(all_sections)}")
print(f"Sections: {', '.join(sorted(all_sections, key=lambda x: int(x) if x.isdigit() else 999))}")

print("\n" + "="*80)
print("STAGE 2 COMPLETE")
print("="*80)

# Optionally save output
output_file = "stage2_output.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(stage2_result.model_dump(), f, indent=2)
print(f"\nFull output saved to: {output_file}")
