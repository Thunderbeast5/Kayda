"""
verify_successor_mappings.py
=============================
Step 5 Verification Script for IPC <-> BNS Successor Mappings.

Tests every required mapping against Neo4j via VerificationService.get_equivalent_ipc_section().
Outputs PASS or FAIL for each mapping.
"""

import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add backend root to sys.path
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(BASE_DIR))

from agents.lexigraph.services.verification_service import VerificationService

PASS = "  [PASS]"
FAIL = "  [FAIL]"


def run_verification():
    print("=" * 80)
    print("STEP 5: VERIFYING IPC <-> BNS SUCCESSOR MAPPINGS AGAINST NEO4J")
    print("=" * 80)

    vs = VerificationService()

    # List of required test cases: (requested_act, requested_sec, expected_act, expected_sec_options)
    test_cases = [
        ("BNS", "355", "IPC", ["354"]),
        ("BNS", "74",  "IPC", ["354"]),
        ("BNS", "76",  "IPC", ["354B"]),
        ("BNS", "80",  "IPC", ["304B"]),
        ("BNS", "63",  "IPC", ["375"]),
        ("BNS", "124", "IPC", ["326A"]),
        ("IPC", "354", "BNS", ["355", "74"]),
        ("IPC", "304B", "BNS", ["80"])
    ]

    total_passed = 0
    total_tests = len(test_cases)

    for req_act, req_sec, exp_act, exp_sec_options in test_cases:
        res = vs.get_equivalent_ipc_section(req_act, req_sec)
        
        if res and res.get("act") == exp_act and res.get("section") in exp_sec_options:
            print(f"{PASS} {req_act} {req_sec:<4} -> {res['act']} {res['section']} (Verified: {res.get('mapping_verified')})")
            total_passed += 1
        else:
            actual_str = f"{res.get('act')} {res.get('section')}" if res else "None"
            print(f"{FAIL} {req_act} {req_sec:<4} -> Expected {exp_act} {exp_sec_options}, Got {actual_str}")

    print("\n" + "=" * 80)
    if total_passed == total_tests:
        print(f"RESULT: ALL {total_tests} MAPPING TESTS PASSED SUCCESSFULLY!")
    else:
        print(f"RESULT: {total_passed}/{total_tests} PASSED. SOME MAPPINGS FAILED!")
    print("=" * 80)

    if total_passed < total_tests:
        sys.exit(1)


if __name__ == "__main__":
    run_verification()
