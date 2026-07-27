import sys
from pathlib import Path

# Add directory to sys.path
sys.path.insert(0, str(Path("context/agent_context").resolve()))
import scenarios_data

scenarios = scenarios_data.SCENARIOS
print(f"Total scenarios in scenarios_data.py: {len(scenarios)}")

categories = {}
for s in scenarios:
    cat = s["category"]
    categories[cat] = categories.get(cat, 0) + 1

for cat, count in categories.items():
    print(f"  {cat}: {count}")
