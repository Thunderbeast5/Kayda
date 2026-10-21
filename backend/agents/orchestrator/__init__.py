"""
agents/orchestrator/__init__.py
Public API for the orchestrator package.

Imports are intentionally lazy so that
  python -m agents.orchestrator.orchestrator_graph
does not trigger a RuntimeWarning about the module already being in
sys.modules (which runpy emits when a package __init__ eagerly imports
the same submodule that -m is about to execute).

Consumers can still do:
  from agents.orchestrator import run_orchestrator, build_graph
and get the real symbols on first access.
"""
from __future__ import annotations

# Names that are part of the public API.
__all__ = [
    "run_orchestrator",
    "build_graph",
    "SimulationState",
    "Fact",
    "Turn",
    "Question",
    "Verdict",
    "session_input_manager",
    "normalize_role",
    "normalize_mode",
    "get_ai_role",
]


def __getattr__(name: str):
    """
    PEP 562 lazy attribute access for this package.
    Triggered only when a name from __all__ is first accessed.
    """
    if name in ("session_input_manager", "normalize_role", "normalize_mode", "get_ai_role"):
        from .session_input import session_input_manager, normalize_role, normalize_mode, get_ai_role
        globals()["session_input_manager"] = session_input_manager
        globals()["normalize_role"]        = normalize_role
        globals()["normalize_mode"]        = normalize_mode
        globals()["get_ai_role"]           = get_ai_role
        return globals()[name]

    if name in ("run_orchestrator", "build_graph"):
        from .orchestrator_graph import run_orchestrator, build_graph  # noqa: F401
        globals()["run_orchestrator"] = run_orchestrator
        globals()["build_graph"]      = build_graph
        return globals()[name]

    if name in ("SimulationState", "Fact", "Turn", "Question", "Verdict"):
        from .state import SimulationState, Fact, Turn, Question, Verdict  # noqa: F401
        globals()["SimulationState"] = SimulationState
        globals()["Fact"]            = Fact
        globals()["Turn"]            = Turn
        globals()["Question"]        = Question
        globals()["Verdict"]         = Verdict
        return globals()[name]

    raise AttributeError(f"module 'agents.orchestrator' has no attribute {name!r}")
