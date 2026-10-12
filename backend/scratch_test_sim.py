import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(r"c:\proj\MootCourt\backend")
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir / "agents"))

from agents.orchestrator.orchestrator_graph import run_orchestrator

case_text = (
    "FIR No. 45/2023 was registered at Police Station Sadar under Sections 324 and 506 IPC. "
    "The applicant was summoned by the Trial Court but failed to appear. "
    "Subsequent bailable warrants and non-bailable warrants issued against the applicant remained unexecuted. "
    "On 15.01.2023, the learned Magistrate initiated and issued a proclamation under Section 82 CrPC against the applicant. "
    "The applicant now moves this application seeking anticipatory bail under Section 438 CrPC."
)

print("\n--- RUNNING ORCHESTRATOR TEST SIMULATION WITH PRECEDENTS AS DATA ---")
result = run_orchestrator(case_id=case_text, session_id="test_prec_01", max_rounds=1)
print("\n--- FINAL SIMULATION RESULT ---")
print(f"Phase: {result.get('phase')}")
verdict = result.get('verdict') or {}
print(f"Decision: {verdict.get('decision')}")
print(f"Confidence: {verdict.get('confidence')}")
print(f"Laws/Precedents Applied: {verdict.get('laws_applied')}")
print(f"Reasoning summary: {verdict.get('reasoning')[:300]}...")
