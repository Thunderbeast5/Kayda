"""
Debug script to trace what happened to Section 204 during Stage 2 processing.
"""
import json
from lexigraphbe.stage2_mapping_agent import Stage2SubQueryMappingAgent
from lexigraphbe.schemas.stage1 import LegalQueryObject
from lexigraphbe.runner import run_stage0, run_stage1

# Sample text from your test case
text = """The applicant, a senior medical officer at a private hospital, seeks anticipatory bail after an FIR was registered following the death of a patient who underwent emergency surgery at the hospital. The complainant, a relative of the deceased, alleges that the applicant deliberately ignored repeated warnings regarding the patient's deteriorating condition, failed to arrange timely specialist intervention, and falsified certain entries in the medical records to conceal negligence. The FIR further alleges that the applicant, along with the hospital administrator, destroyed internal monitoring records and instructed junior staff members not to disclose the actual sequence of events. The applicant denies these allegations and submits that the patient was admitted in a critical condition, all necessary medical procedures were followed, and the death resulted from complications that could not have been reasonably anticipated. The applicant contends that the allegations arise from a medical dispute and that criminal liability cannot be imposed merely because a treatment was unsuccessful. The applicant has already provided medical records and cooperated with the investigating agency. The prosecution opposes anticipatory bail, arguing that the alleged manipulation of hospital records requires custodial interrogation and that the applicant may influence hospital employees who are material witnesses."""

print("Running Stage 0 and Stage 1...")
stage0_res = run_stage0(text)
stage1_res = run_stage1(stage0_res)

print("\n" + "="*80)
print("TRACING SECTION 204 IN STAGE 2")
print("="*80)

# Create agent
agent = Stage2SubQueryMappingAgent()

# Extract facts text (same logic as in run method)
query_obj = stage1_res
facts_text_parts = []
if query_obj.important_facts:
    facts_dict = query_obj.important_facts.model_dump()
    for v in facts_dict.values():
        if isinstance(v, str) and v:
            facts_text_parts.append(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str) and item:
                    facts_text_parts.append(item)
for concept_item in query_obj.legal_concepts:
    if concept_item.concept:
        facts_text_parts.append(concept_item.concept)
facts_text = " ".join(facts_text_parts)

print(f"\nFacts text (first 300 chars): {facts_text[:300]}...\n")

# Run prefilter
print("Step 1: Running prefilter...")
prefiltered_matches = agent.prefilter.retrieve_for_legal_query(
    query_obj,
    statute_type="IPC",
    top_k=20,
    per_concept=4,
)

section_204_found = False
for m in prefiltered_matches:
    sec_num = getattr(m, "section_number", "")
    if sec_num == "204":
        section_204_found = True
        print(f"✓ Section 204 FOUND in prefilter results")
        print(f"  Score: {getattr(m, 'score', 0.0)}")
        print(f"  Title: {getattr(m, 'title', '')}")
        break

if not section_204_found:
    print("✗ Section 204 NOT in prefilter results")
else:
    # Check fatal disqualification
    print("\nStep 2: Checking fatal disqualification...")
    is_not_triggered, elim_reason, missing_mands = agent.prefilter.evaluate_fatal_disqualification(
        "204", "IPC", facts_text
    )
    print(f"  not_triggered: {is_not_triggered}")
    print(f"  Reason: {elim_reason}")
    print(f"  Missing mandatory ingredients: {missing_mands}")
    
    if not is_not_triggered:
        # Check scope compatibility
        print("\nStep 3: Checking scope compatibility...")
        compatible, reason = agent._check_scope_compatibility(
            section_number="204",
            statute="IPC",
            facts_text=facts_text,
        )
        print(f"  Compatible: {compatible}")
        print(f"  Reason: {reason}")
        
        if compatible:
            print("\n✓ Section 204 should have been sent to mapping LLM")
        else:
            print("\n✗ Section 204 was filtered out by scope check")
    else:
        print("\n✗ Section 204 was filtered out by fatal disqualification")

# Also check Section 201 for comparison
print("\n" + "="*80)
print("CHECKING SECTION 201 (which WAS included)")
print("="*80)

for m in prefiltered_matches:
    sec_num = getattr(m, "section_number", "")
    if sec_num == "201":
        print(f"✓ Section 201 FOUND in prefilter results")
        print(f"  Score: {getattr(m, 'score', 0.0)}")
        print(f"  Title: {getattr(m, 'title', '')}")
        
        is_not_triggered, elim_reason, missing_mands = agent.prefilter.evaluate_fatal_disqualification(
            "201", "IPC", facts_text
        )
        print(f"\nFatal disqualification check:")
        print(f"  not_triggered: {is_not_triggered}")
        print(f"  Reason: {elim_reason}")
        
        if not is_not_triggered:
            compatible, reason = agent._check_scope_compatibility(
                section_number="201",
                statute="IPC",
                facts_text=facts_text,
            )
            print(f"\nScope compatibility check:")
            print(f"  Compatible: {compatible}")
            print(f"  Reason: {reason}")
        break
