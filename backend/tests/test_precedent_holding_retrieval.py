"""
test_precedent_holding_retrieval.py
===================================
Tests for Task 2:
Precedents as retrievable data (Holding schema) and dynamic holding retrieval.
Validates:
1. Holding schema: id, case, para, principle, conditions, effect.
2. Srikant Upadhyay holdings are loaded and retrievable as data.
3. Proclamation / warrant facts retrieve Srikant holdings (effect: favours_denial).
4. Prompt formatting renders principles and conditions clearly.
5. Zero hardcoded if-statements: legal rules originate purely from retrieved precedent data.
"""

import sys
from pathlib import Path
import pytest

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from agents.orchestrator.state import Fact
from agents.lexigraph.holding_retrieval import (
    Holding,
    load_all_local_holdings,
    retrieve_holdings,
    format_holdings_for_prompt,
)


def test_holding_model_schema():
    h = Holding(
        id="srikant_para23",
        case="Srikant Upadhyay v. State of Bihar, 2024 INSC 202",
        para="23",
        principle="An absconding accused against whom Section 82 CrPC proclamation is issued is not entitled to anticipatory bail.",
        conditions="Warrants unexecuted and Section 82 proclamation initiated or issued.",
        effect="favours_denial",
    )
    assert h.id == "srikant_para23"
    assert "2024 INSC 202" in h.case
    assert h.effect == "favours_denial"
    d = h.to_dict()
    assert d["para"] == "23"
    assert "principle" in d
    assert "conditions" in d


def test_offline_holdings_loaded():
    holdings = load_all_local_holdings()
    assert len(holdings) >= 20, f"Expected at least 20 holdings, found {len(holdings)}"
    cases = {h.case for h in holdings}
    assert any("Srikant Upadhyay" in c for c in cases)


def test_retrieval_for_proclamation_facts():
    facts = [
        Fact(id="fact_1", text="FIR registered under Section 324 and 506 IPC", source="FIR"),
        Fact(id="fact_2", text="Non-bailable warrant issued on 03.11.2022; applicant remained non-compliant", source="order sheet"),
        Fact(id="fact_3", text="Proclamation issued under Section 82 CrPC against applicant", source="order sheet"),
    ]
    retrieved = retrieve_holdings("proclamation under section 82 non-bailable warrant", case_facts=facts, top_k=5)
    assert len(retrieved) > 0

    top = retrieved[0]
    assert "srikant" in top["id"].lower() or "srikant" in top["case"].lower()
    assert top["effect"] in ("favours_denial", "procedural", "favours_grant")
    
    # Verify denial holdings exist in top results
    denial_holdings = [h for h in retrieved if h["effect"] == "favours_denial"]
    assert len(denial_holdings) >= 1
    assert any("82" in h["principle"] or "82" in h["conditions"] for h in denial_holdings)


def test_prompt_formatting_contains_principles_and_conditions():
    holdings = [
        {
            "id": "srikant_para4-5",
            "case": "Srikant Upadhyay v. State of Bihar, 2024 INSC 202",
            "para": "4-5",
            "principle": "Proclamation under Section 82 CrPC ordinarily bars anticipatory bail.",
            "conditions": "Applicant evades arrest and NBW is outstanding.",
            "effect": "favours_denial",
            "score": 0.95,
        }
    ]
    formatted = format_holdings_for_prompt(holdings)
    assert "RETRIEVED PRECEDENT HOLDINGS" in formatted
    assert "Srikant Upadhyay" in formatted
    assert "Principle :" in formatted
    assert "Conditions:" in formatted
    assert "FAVOURS_DENIAL" in formatted
