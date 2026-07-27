from pathlib import Path

root = Path("c:/proj/MootCourt")
found = list(root.rglob("scenarios_data.py"))
print("Found files:")
for f in found:
    print(" ", f.resolve())
