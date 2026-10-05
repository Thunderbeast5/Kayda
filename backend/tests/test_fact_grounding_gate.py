"""
tests/test_fact_grounding_gate.py
==================================
Unit tests for the inventory-aware Fact Grounding Gate in MootCourt orchestrator.

Tests:
1. Fabricated absence of a present weapon -> Rejected (False).
2. Fabricated absence of present eyewitnesses -> Rejected (False).
3. Legitimate "not on record" claim for evidence not present -> Accepted (True).
4. Clean argument arguing intention / mens rea -> Accepted (True).
5. Fabricated weapon not matching facts -> Rejected (False).
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from agents.orchestrator.orchestrator_graph import _verify_fact_references
from agents.orchestrator.state import Fact


SAMPLE_FACTS = [
    Fact(id="fact_1", text="Ramesh Kumar is named as the accused.", source="FIR"),
    Fact(id="fact_2", text="Suresh Gupta is named as the victim/complainant.", source="FIR"),
    Fact(id="fact_3", text="Ramesh Kumar stabbed Suresh Gupta with a kitchen knife outside a restaurant.", source="FIR"),
    Fact(id="fact_4", text="Incident date is 12/03/2026 outside a restaurant.", source="FIR"),
    Fact(id="fact_5", text="Two eyewitnesses were present at the scene.", source="witness statement"),
    Fact(id="fact_6", text="A blood-stained kitchen knife was recovered from the accused's bag.", source="recovery memo"),
]

SAMPLE_INVENTORY = [
    {
        "item": "eyewitnesses",
        "status": "present",
        "details": "Two eyewitnesses were present outside restaurant."
    },
    {
        "item": "weapon",
        "status": "present",
        "details": "Blood-stained kitchen knife recovered from accused's bag."
    },
    {
        "item": "medical_report",
        "status": "not_on_record",
        "details": "No medical report or injury certificate produced on record."
    },
    {
        "item": "cctv_digital",
        "status": "not_on_record",
        "details": "No CCTV footage or recording produced."
    },
    {
        "item": "fir",
        "status": "present",
        "details": "FIR lodged following incident."
    }
]


def test_fabricated_absence_of_present_weapon():
    """Argument claims knife was not recovered, but inventory marks it present."""
    arg = (
        "May it please the Court, the prosecution's case is completely uncorroborated. "
        "The knife was not recovered from the accused, and there is no physical link connecting him to the crime."
    )
    result = _verify_fact_references(arg, SAMPLE_FACTS, SAMPLE_INVENTORY)
    assert result is False, "Gate should reject fabricated absence of recovered knife"


def test_fabricated_absence_of_present_eyewitnesses():
    """Argument claims there were no eyewitnesses, but inventory marks them present."""
    arg = (
        "The defense submits that there were no eyewitnesses to the alleged altercation outside the restaurant. "
        "The prosecution's entire narrative rests on conjecture."
    )
    result = _verify_fact_references(arg, SAMPLE_FACTS, SAMPLE_INVENTORY)
    assert result is False, "Gate should reject claim of 'no eyewitnesses' when eyewitnesses are on record"


def test_legitimate_not_on_record_claim():
    """Argument states record does not contain medical report, which is true (not on record)."""
    arg = (
        "May it please the Court, the record before the court does not contain any medical reports, "
        "wound certificates, or MLC to substantiate the gravity of the alleged injury. "
        "Without documentary evidence produced before this court, the charge of attempt to murder cannot stand."
    )
    result = _verify_fact_references(arg, SAMPLE_FACTS, SAMPLE_INVENTORY)
    assert result is True, "Gate should accept legitimate 'record does not contain' arguments for unproduced evidence"


def test_clean_argument():
    """Clean legal argument on intention, sudden quarrel, and statutory ingredients."""
    arg = (
        "May it please the Court, the defense submits that the prosecution has failed to establish "
        "premeditation or common intention. The alleged incident arose out of a sudden dispute, bringing "
        "the matter within the exceptions to Section 300 IPC. In view of the accused's deep roots in society "
        "and cooperation with investigation, anticipatory bail may kindly be granted."
    )
    result = _verify_fact_references(arg, SAMPLE_FACTS, SAMPLE_INVENTORY)
    assert result is True, "Gate should accept clean legal and procedural arguments"


def test_fabricated_weapon():
    """Argument asserts a firearm was used when case facts specify a kitchen knife."""
    arg = (
        "The prosecution alleges the accused brandished an unlicensed revolver and threatened bystanders. "
        "This allegation is completely unsubstantiated."
    )
    result = _verify_fact_references(arg, SAMPLE_FACTS, SAMPLE_INVENTORY)
    assert result is False, "Gate should reject argument asserting a fabricated firearm/revolver"


def test_fabricated_absence_of_present_complainant():
    """Argument asserts there is no complainant when complainant/victim is present."""
    inventory_with_comp = SAMPLE_INVENTORY + [{
        "item": "complainant",
        "status": "present",
        "details": "Complainant/victim Suresh Gupta identified on record."
    }]
    arg = (
        "May it please the Court, there is no complainant before this court and no person has come forward "
        "to lodge a grievance against my client."
    )
    result = _verify_fact_references(arg, SAMPLE_FACTS, inventory_with_comp)
    assert result is False, "Gate should reject claim of 'no complainant' when complainant is on record"


if __name__ == "__main__":
    print("Running fact grounding gate unit tests...")
    test_fabricated_absence_of_present_weapon()
    print("PASS: test_fabricated_absence_of_present_weapon")
    test_fabricated_absence_of_present_eyewitnesses()
    print("PASS: test_fabricated_absence_of_present_eyewitnesses")
    test_legitimate_not_on_record_claim()
    print("PASS: test_legitimate_not_on_record_claim")
    test_clean_argument()
    print("PASS: test_clean_argument")
    test_fabricated_weapon()
    print("PASS: test_fabricated_weapon")
    test_fabricated_absence_of_present_complainant()
    print("PASS: test_fabricated_absence_of_present_complainant")
    print("\nALL 6 UNIT TESTS PASSED!")
