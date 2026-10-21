"""
Unit and Integration Tests for Orchestrator Role Selection (AI vs Human)
========================================================================
Tests:
1. Role normalization ('prosecutor', 'prosecution', 'defence', 'defense', etc.)
2. Mode normalization and AI opponent role resolution
3. SessionInputManager thread-safe wait and submit mechanism
4. Orchestrator pipeline initialization and event emission with chosen roles
5. FastAPI REST endpoints for roles and human argument submission
"""

import sys
import threading
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
agents_dir = backend_dir / "agents"
if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))

from agents.orchestrator.session_input import (
    normalize_role,
    normalize_mode,
    get_ai_role,
    session_input_manager,
)


def test_role_normalization():
    """Verify all aliases normalize to canonical 'prosecutor' or 'defense'."""
    assert normalize_role("prosecutor") == "prosecutor"
    assert normalize_role("Prosecutor") == "prosecutor"
    assert normalize_role("prosecution") == "prosecutor"
    assert normalize_role("PROSECUTION") == "prosecutor"
    assert normalize_role("pros") == "prosecutor"
    assert normalize_role("state") == "prosecutor"
    assert normalize_role("public_prosecutor") == "prosecutor"

    assert normalize_role("defense") == "defense"
    assert normalize_role("Defense") == "defense"
    assert normalize_role("defence") == "defense"
    assert normalize_role("DEFENCE") == "defense"
    assert normalize_role("def") == "defense"
    assert normalize_role("accused_counsel") == "defense"

    assert normalize_role(None) is None
    assert normalize_role("") is None
    assert normalize_role("invalid_role") is None


def test_mode_and_ai_role():
    """Verify mode resolution and opponent AI assignment."""
    assert normalize_mode("ai_vs_human", "prosecutor") == "ai_vs_human"
    assert normalize_mode("ai_vs_ai", "prosecutor") == "ai_vs_ai"
    assert normalize_mode(None, "prosecutor") == "ai_vs_human"
    assert normalize_mode(None, None) == "ai_vs_ai"

    # AI vs Human: user is prosecutor -> AI is defense
    assert get_ai_role("prosecutor", "ai_vs_human") == "defense"
    # AI vs Human: user is defense -> AI is prosecutor
    assert get_ai_role("defense", "ai_vs_human") == "prosecutor"
    # AI vs AI: both are AI
    assert get_ai_role(None, "ai_vs_ai") == "both"


def test_session_input_manager():
    """Verify SessionInputManager enables asynchronous turn submission."""
    sid = "test_sess_001"
    session_input_manager.clear(sid)

    # 1. Background submit after a brief delay
    def _submit_worker():
        time.sleep(0.1)
        session_input_manager.submit_argument(
            session_id=sid,
            argument="Your Honor, the prosecution has failed to establish prima facie ingredients.",
            role="defense",
            round_no=1,
        )

    t = threading.Thread(target=_submit_worker)
    t.start()

    arg = session_input_manager.wait_for_argument(
        session_id=sid,
        role="defense",
        round_no=1,
        timeout=2.0,
    )
    t.join()

    assert arg is not None
    assert "prima facie ingredients" in arg

    # Verify cleared
    session_input_manager.clear(sid)
    assert sid not in session_input_manager._arguments


def test_app_endpoints():
    """Verify role endpoints and argument submission on app.py."""
    from app import app
    client = TestClient(app)

    # 1. Roles metadata endpoint
    r = client.get("/api/orchestrator/roles")
    assert r.status_code == 200
    data = r.json()
    assert "modes" in data
    assert "roles" in data
    role_ids = [item["id"] for item in data["roles"]]
    assert "prosecutor" in role_ids
    assert "defense" in role_ids

    # 2. Argument submission endpoint
    test_sid = "test_app_sess"
    session_input_manager.clear(test_sid)
    res = client.post(
        "/api/orchestrator/submit-argument",
        json={
            "session_id": test_sid,
            "argument": "The accused was not present at the scene.",
            "role": "defence",
            "round_no": 1,
        },
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Check that session_input_manager stored it normalized to 'defense'
    arg = session_input_manager.wait_for_argument(test_sid, "defense", 1, timeout=0.5)
    assert arg == "The accused was not present at the scene."
    session_input_manager.clear(test_sid)


def test_app_orchestrator_endpoints():
    """Verify endpoints on app_orchestrator.py."""
    from app_orchestrator import app as orch_app
    client = TestClient(orch_app)

    # 1. Health
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "supported_roles" in r.json()

    # 2. Roles
    r = client.get("/api/roles")
    assert r.status_code == 200
    data = r.json()
    assert any(x["id"] == "prosecutor" for x in data["roles"])
    assert any(x["id"] == "defense" for x in data["roles"])

    # 3. Simulate argument endpoint
    sid = "orch_test_sess"
    session_input_manager.clear(sid)
    r = client.post(
        "/api/simulate/argument",
        json={
            "session_id": sid,
            "argument": "We submit that bail should be granted under S.438 CrPC.",
            "role": "defense",
            "round_no": 1,
        },
    )
    assert r.status_code == 200
    assert r.json()["success"] is True

    arg = session_input_manager.wait_for_argument(sid, "defense", 1, timeout=0.5)
    assert "bail should be granted" in arg
    session_input_manager.clear(sid)


def test_nodes_role_behavior():
    """Verify node_prosecutor and node_defense behavior in AI vs Human role assignment."""
    from agents.orchestrator.orchestrator_graph import node_prosecutor, node_defense
    from agents.orchestrator.state import SimulationState

    events_captured = []
    def _emit(evt):
        events_captured.append(evt)

    # ── Test 1: User is Prosecutor ──
    state_pros = {
        "session_id": "test_role_p",
        "case_id": "demo",
        "mode": "ai_vs_human",
        "user_role": "prosecutor",
        "ai_role": "defense",
        "human_argument": "Your Honor, the State submits that Section 324 IPC ingredients are met.",
        "phase": "COURTROOM",
        "round_no": 1,
        "case_facts": [],
        "evidence_inventory": [],
        "transcript": [],
        "lexigraph_output": {},
        "holdings": [],
    }

    events_captured.clear()
    res_pros = node_prosecutor(state_pros, emit=_emit)
    transcript_p = res_pros["transcript"]
    assert len(transcript_p) == 1
    turn_p = transcript_p[0]
    assert turn_p["speaker"] == "prosecutor"
    assert turn_p["is_human"] is True
    assert turn_p["display_name"] == "[YOU] Public Prosecutor"
    assert "Section 324 IPC" in turn_p["content"]
    assert any(e.get("type") == "awaiting_human_input" and e.get("role") == "prosecutor" for e in events_captured)

    # ── Test 2: User is Defense ──
    state_def = {
        "session_id": "test_role_d",
        "case_id": "demo",
        "mode": "ai_vs_human",
        "user_role": "defense",
        "ai_role": "prosecutor",
        "human_argument": "Your Honor, the defense submits that the accused has established absence of intention.",
        "phase": "COURTROOM",
        "round_no": 1,
        "case_facts": [],
        "evidence_inventory": [],
        "transcript": [{"speaker": "prosecutor", "content": "State argument."}],
        "lexigraph_output": {},
        "holdings": [],
    }

    events_captured.clear()
    res_def = node_defense(state_def, emit=_emit)
    transcript_d = res_def["transcript"]
    assert len(transcript_d) == 2
    turn_d = transcript_d[-1]
    assert turn_d["speaker"] == "defense"
    assert turn_d["is_human"] is True
    assert turn_d["display_name"] == "[YOU] Defense Counsel"
    assert "absence of intention" in turn_d["content"]
    assert any(e.get("type") == "awaiting_human_input" and e.get("role") == "defense" for e in events_captured)


if __name__ == "__main__":
    print("Running test_role_normalization...")
    test_role_normalization()
    print("Running test_mode_and_ai_role...")
    test_mode_and_ai_role()
    print("Running test_session_input_manager...")
    test_session_input_manager()
    print("Running test_nodes_role_behavior...")
    test_nodes_role_behavior()
    print("Running test_app_endpoints...")
    test_app_endpoints()
    print("Running test_app_orchestrator_endpoints...")
    test_app_orchestrator_endpoints()
    print("ALL TESTS PASSED SUCCESSFULLY!")
