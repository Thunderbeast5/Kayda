import time
from typing import Dict, Any

PHASES = [
    "CASE_INTRO",
    "OPENING",
    "ARGUMENT",
    "REBUTTAL",
    "JUDGMENT",
    "COMPLETED"
]

def _next_turn_order(phase: str) -> list[str]:
    """
    Returns the sequence of turns for a given phase.
    """
    if phase == "CASE_INTRO":
        return ["prosecution"] # Intro doesn't really have turns, but prosecution acts first if needed
    elif phase == "OPENING":
        return ["prosecution", "defense"]
    elif phase == "ARGUMENT":
        return ["prosecution", "defense"]
    elif phase == "REBUTTAL":
        return ["defense", "prosecution"]
    elif phase == "JUDGMENT":
        return [] # AI Judge's domain
    elif phase == "COMPLETED":
        return []
    
    return []

def advance_turn(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given the current state, advances to the next player's turn.
    If all players have gone for this phase, advances to the next phase.
    """
    current_phase = state.get("phase", "CASE_INTRO")
    current_turn_role = None
    
    # Identify what role the current turn belongs to
    prosecution_id = state["players"]["prosecution"]
    defense_id = state["players"]["defense"]
    
    if state["current_turn"] == prosecution_id:
        current_turn_role = "prosecution"
    elif state["current_turn"] == defense_id:
        current_turn_role = "defense"
        
    order = _next_turn_order(current_phase)
    
    if not order:
        # Phase has no turns (e.g. Judgment). We shouldn't normally be here.
        return _advance_phase(state)
        
    try:
        current_idx = order.index(current_turn_role)
    except ValueError:
        # Current role isn't in the order (or is None). Just start from beginning.
        current_idx = -1
        
    next_idx = current_idx + 1
    
    if next_idx < len(order):
        # Still in the same phase, just the next player's turn
        next_role = order[next_idx]
        state["current_turn"] = state["players"][next_role]
        state["turn"] = {
            "player_id": state["current_turn"],
            "started_at": time.time(),
            "time_remaining": 120
        }
    else:
        # Everyone has gone for this phase. Advance phase.
        state = _advance_phase(state)
        
    return state

def _advance_phase(state: Dict[str, Any]) -> Dict[str, Any]:
    current_phase = state.get("phase", "CASE_INTRO")
    try:
        idx = PHASES.index(current_phase)
        next_phase = PHASES[idx + 1] if idx + 1 < len(PHASES) else "COMPLETED"
    except ValueError:
        next_phase = "COMPLETED"
        
    state["phase"] = next_phase
    
    if next_phase == "COMPLETED":
        state["status"] = "COMPLETED"
        state["current_turn"] = None
        state["turn"] = None
    else:
        # Start the first turn of the new phase
        order = _next_turn_order(next_phase)
        if order:
            state["current_turn"] = state["players"][order[0]]
            state["turn"] = {
                "player_id": state["current_turn"],
                "started_at": time.time(),
                "time_remaining": 120
            }
        else:
            state["current_turn"] = None
            state["turn"] = None
            
    return state
