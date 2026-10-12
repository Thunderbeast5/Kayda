"""
Debug script to trace orchestrator vs direct lexigraphbe call
"""
import sys
import os

# Ensure we're using the same environment
print(f"Python: {sys.executable}")
print(f"Working dir: {os.getcwd()}")
print(f"sys.path[0]: {sys.path[0]}")

# Test 1: Direct lexigraphbe import
print("\n=== TEST 1: Direct lexigraphbe call ===")
from lexigraphbe.runner import run_full_pipeline
import inspect
print(f"lexigraphbe.runner location: {inspect.getfile(run_full_pipeline)}")

text = "The applicant seeks anticipatory bail after an FIR alleges that he forged ownership documents of agricultural land, executed a fraudulent sale deed, and dishonestly transferred the property to a third party; the applicant claims the documents are genuine, asserts that the dispute concerns title over immovable property, and has cooperated with the investigating agency."

result1 = run_full_pipeline(text=text)
s2_1 = result1.get("stage2_subquery_mapping", {})
mappings1 = s2_1.get("mappings", [])
print(f"\nStage 2 mappings: {len(mappings1)}")
for m in mappings1:
    primary = [s.get("section_number") for s in m.get("primary_candidate_sections", [])]
    print(f"  {m.get('sub_query_id')}: primary={primary}")

s3_1 = result1.get("stage3_chapter_identification", {})
verified1 = [v.get("section_number") for v in s3_1.get("verified_offences", [])]
print(f"\nStage 3 verified sections: {verified1}")

# Test 2: Through orchestrator
print("\n\n=== TEST 2: Through orchestrator (internal call) ===")
from prosecutor.orchestrator_agent import OrchestratorAgent
from prosecutor.schemas import OrchestratorInput

# Call run_full_pipeline directly (bypassing orchestrator wrapper)
result2 = run_full_pipeline(text=text)
s2_2 = result2.get("stage2_subquery_mapping", {})
mappings2 = s2_2.get("mappings", [])
print(f"\nDirect call #2 Stage 2 mappings: {len(mappings2)}")
for m in mappings2:
    primary = [s.get("section_number") for s in m.get("primary_candidate_sections", [])]
    print(f"  {m.get('sub_query_id')}: primary={primary}")

s3_2 = result2.get("stage3_chapter_identification", {})
verified2 = [v.get("section_number") for v in s3_2.get("verified_offences", [])]
print(f"\nDirect call #2 Stage 3 verified sections: {verified2}")

# Test 3: Through orchestrator wrapper
print("\n\n=== TEST 3: Through orchestrator wrapper ===")
orch = OrchestratorAgent()
print(f"Orchestrator's run_full_pipeline location: {inspect.getfile(orch._run_full_pipeline)}")

orch_result = orch.run(OrchestratorInput(case_text=text))
print(f"\nOrchestrator verified sections: {[s.section_number for s in orch_result.verified_sections]}")

# Compare
print("\n\n=== COMPARISON ===")
print(f"Direct Stage 3: {verified1}")
print(f"Orchestrator:   {[s.section_number for s in orch_result.verified_sections]}")
print(f"Match: {set(verified1) == set([s.section_number for s in orch_result.verified_sections])}")
