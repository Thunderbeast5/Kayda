import sys
import json
from pathlib import Path

# Set up paths
backend_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(backend_dir))

from lexigraphbe.runner import run_stage0, run_stage1
from lexigraphbe.stage2_mapping_agent import Stage2SubQueryMappingAgent
from lexigraphbe.schemas.stage1 import LegalQueryObject

case_text = (
    "The applicant, a senior medical officer at a private hospital, seeks anticipatory bail after an "
    "FIR was registered following the death of a patient who underwent emergency surgery at the hospital. "
    "The complainant, a relative of the deceased, alleges that the applicant deliberately ignored repeated "
    "warnings regarding the patient's deteriorating condition, failed to arrange timely specialist intervention, "
    "and falsified certain entries in the medical records to conceal negligence. The FIR further alleges that "
    "the applicant, along with the hospital administrator, destroyed internal monitoring records and instructed "
    "junior staff members not to disclose the actual sequence of events. The applicant denies these allegations "
    "and submits that the patient was admitted in a critical condition, all necessary medical procedures were "
    "followed, and the death resulted from complications that could not have been reasonably anticipated. "
    "The applicant contends that the allegations arise from a medical dispute and that criminal liability "
    "cannot be imposed merely because a treatment was unsuccessful. The applicant has already provided medical "
    "records and cooperated with the investigating agency. The prosecution opposes anticipatory bail, arguing "
    "that the alleged manipulation of hospital records requires custodial interrogation and that the applicant "
    "may influence hospital employees who are material witnesses."
)

print("=" * 65)
print("  STEP 1: RUNNING STAGE 0 (INTAKE) & STAGE 1 (QUERY DECONSTRUCTION)")
print("=" * 65)
stage0_res = run_stage0(text=case_text)
stage1_res = run_stage1(stage0_res)

query_obj = LegalQueryObject.model_validate(stage1_res)

print("\n" + "=" * 65)
print("  STAGE 1 EXTRACTED LEGAL CONCEPTS & SUB-QUERIES")
print("=" * 65)
for idx, c in enumerate(query_obj.legal_concepts, 1):
    print(f"  [Concept {idx}] {c.concept}")

for idx, sq in enumerate(query_obj.sub_queries, 1):
    print(f"  [Sub-Query {idx}] {sq.query}")
    print(f"    -> Associated Concept: {sq.concept}")

regime = query_obj.legal_regime or "IPC + CrPC"
statute_type = "BNS" if ("BNS" in regime.upper() or "BNSS" in regime.upper()) else "IPC"
print(f"\n  [Statute Regime]: {regime} -> Querying {statute_type} sections")

agent = Stage2SubQueryMappingAgent()

import lexigraphbe.classifier_prefilter as _cp
print(f"  [Prefilter module] {_cp.__file__}")
assert hasattr(agent.prefilter, "retrieve_for_legal_query"), "OLD classifier_prefilter.py is being imported"

print("\n" + "=" * 65)
print("  STEP 2: RUNNING LOCAL CLASSIFIER PRE-FILTER (ZERO LLM CALLS)")
print("=" * 65)

candidates = agent.prefilter.retrieve_for_legal_query(
    query_obj, statute_type=statute_type, top_k=20, per_concept=4
)

print(f"\n  Total Candidates Retrieved: {len(candidates)}")
print("\n" + "=" * 65)
print("  RETRIEVED CANDIDATE SECTIONS (FUSED RANK)")
print("=" * 65)
for idx, c in enumerate(candidates, 1):
    print(f" {idx:2d}. [{c.statute} Sec {c.section_number:<6}] {c.title}")
    print(f"     Score: {c.score:<5} | Chapter: {c.chapter}")
    print(f"     Concepts: {c.matched_concepts} | Terms: {c.matched_terms[:8]}")

print("\n" + "=" * 65)
print("  END OF PREFILTER CANDIDATE RETRIEVAL")
print("=" * 65)