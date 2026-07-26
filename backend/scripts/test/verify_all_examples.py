import os
import sys

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(BASE_DIR))

from agents.lexigraph.services.verification_service import VerificationService

vs = VerificationService()

test_cases = [
    ("BNS", "74"),
    ("BNS", "76"),
    ("BNS", "80"),
    ("BNS", "63"),
    ("BNS", "124"),
    ("BNS", "355"),
    ("IPC", "354"),
    ("IPC", "304B"),
    ("BNS", "9999")
]

print("=" * 80)
print("TESTING DYNAMIC IPC <-> BNS EQUIVALENT SECTION RETRIEVAL FROM NEO4J")
print("=" * 80)

for act, sec in test_cases:
    eq = vs.get_equivalent_ipc_section(act, sec)
    print(f"  {act} {sec:<5} => {eq}")

print("=" * 80)
