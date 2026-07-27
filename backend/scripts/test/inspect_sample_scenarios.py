import sys
from pathlib import Path
sys.path.insert(0, str(Path("context/agent_context").resolve()))
import scenarios_data

by_cat = {}
for s in scenarios_data.SCENARIOS:
    cat = s["category"]
    if cat not in by_cat:
        by_cat[cat] = s

for cat, s in by_cat.items():
    print(f"=== Category: {cat} ===")
    print(f"ID: {s['id']}, Negative: {s['is_negative_example']}")
    print(f"Facts: {s['facts'][:100]}...")
    print(f"BNS: {s['expected_bns_sections']}")
    print(f"IPC: {s['expected_ipc_sections']}")
    print(f"Cases: {s['landmark_cases']}")
    print()
