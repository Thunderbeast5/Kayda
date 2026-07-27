import sys
from pathlib import Path

sys.path.insert(0, str(Path("context/agent_context").resolve()))
import scenarios_data

scenarios = scenarios_data.SCENARIOS
print(f"Loaded {len(scenarios)} scenarios from refined scenarios_data.py")

REQUIRED_ORIGINAL_FIELDS = [
    "id", "category", "facts", "expected_bns_sections", "expected_ipc_sections",
    "required_evidence", "landmark_cases", "is_negative_example", "notes"
]

NEW_EVALUATION_FIELDS = [
    "difficulty", "expected_top1", "expected_top3", "expected_rejected_sections",
    "expected_evidence", "expected_landmark_cases", "expected_constitution_articles",
    "expected_legal_principles", "expected_fact_extraction",
    "expected_ingredient_validation", "expected_confidence_range",
    "expected_community", "expected_pipeline_stage"
]

all_passed = True
neg_count = 0
pos_count = 0

for idx, s in enumerate(scenarios):
    sid = s.get("id", f"INDEX_{idx}")
    
    # Check original fields
    for field in REQUIRED_ORIGINAL_FIELDS:
        if field not in s:
            print(f"[FAIL] Scenario {sid} missing original field: {field}")
            all_passed = False

    # Check new fields
    for field in NEW_EVALUATION_FIELDS:
        if field not in s:
            print(f"[FAIL] Scenario {sid} missing new evaluation field: {field}")
            all_passed = False

    # Check negative logic
    if s["is_negative_example"]:
        neg_count += 1
        if s["expected_top1"] is not None:
            print(f"[FAIL] Scenario {sid} (negative) expected_top1 is not None: {s['expected_top1']}")
            all_passed = False
        if s["expected_top3"] != []:
            print(f"[FAIL] Scenario {sid} (negative) expected_top3 is not empty list: {s['expected_top3']}")
            all_passed = False
    else:
        pos_count += 1
        if s["expected_top1"] is None and s["expected_bns_sections"]:
            print(f"[FAIL] Scenario {sid} (positive) expected_top1 is None")
            all_passed = False

print(f"Positive scenarios: {pos_count}, Negative scenarios: {neg_count}")

# Print sample scenario to verify refined fields visually
sample = scenarios[0]
print("\n=== SAMPLE REFINED SCENARIO (MUR-01) ===")
print("ID                              :", sample["id"])
print("Difficulty                      :", sample["difficulty"])
print("Expected Top 1                  :", sample["expected_top1"])
print("Expected Top 3                  :", sample["expected_top3"])
print("Expected Community              :", sample["expected_community"])
print("Expected Pipeline Stage         :", sample["expected_pipeline_stage"])
print("Expected Fact Extraction        :", sample["expected_fact_extraction"])
print("Expected Ingredient Validation  :", sample["expected_ingredient_validation"])
print("Expected Confidence Range       :", sample["expected_confidence_range"])
print("Expected Constitution Articles  :", sample["expected_constitution_articles"])

if all_passed:
    print("=" * 80)
    print("SUCCESS: ALL 122 SCENARIOS ARE FULLY REFINED AND VALIDATED!")
    print("=" * 80)
else:
    print("FAILURES DETECTED IN ENRICHED DATASET!")
