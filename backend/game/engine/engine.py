from typing import Dict, Any, Tuple, Optional
from .state import get_game_state, update_game_state, sync_to_firestore_sync
from .turn_manager import advance_turn
import asyncio

class GameEngine:
    async def process_action(self, game_id: str, user_id: str, action_payload: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Validates and processes an incoming action from the frontend.
        Returns:
            (success: bool, error_message: str, new_state: dict, event_to_broadcast: dict)
        """
        state = await get_game_state(game_id)
        if not state:
            return False, "Game state not found", None, None
            
        if state.get("status") != "ACTIVE":
            return False, "Game is not active", None, None
            
        action_type = action_payload.get("action")
        if not action_type:
            return False, "Missing action type", None, None
            
        # 1. Validate user's turn
        is_turn = (state.get("current_turn") == user_id)
        
        # Some actions might not require it to be your turn (e.g. OBJECTION), but END_TURN and SUBMIT_ARGUMENT do.
        turn_required_actions = ["END_TURN", "SUBMIT_ARGUMENT", "PRESENT_EVIDENCE"]
        
        if action_type in turn_required_actions and not is_turn:
            return False, "Not your turn", None, None
            
        # 2. Process Action
        event_to_broadcast = None
        
        if action_type == "END_TURN":
            # Advance the turn
            state = advance_turn(state)
            
            # If the phase changed as a result of advancing turn
            if state["status"] == "COMPLETED":
                event_to_broadcast = {
                    "type": "GAME_COMPLETED",
                    "scores": state["scores"]
                }
            else:
                event_to_broadcast = {
                    "type": "TURN_CHANGED",
                    "current_turn": state["current_turn"],
                    "phase": state["phase"]
                }
                
        elif action_type == "SUBMIT_ARGUMENT":
            # For now, just record it and advance turn
            # In the future, this is where we'd score the argument
            argument_text = action_payload.get("text", "")
            # Advance the turn automatically after submitting an argument
            state = advance_turn(state)
            
            event_to_broadcast = {
                "type": "ACTION_SUBMITTED",
                "action": "SUBMIT_ARGUMENT",
                "player_id": user_id,
                "text": argument_text,
                "next_turn": state["current_turn"],
                "phase": state["phase"]
            }
        else:
            return False, f"Unknown action: {action_type}", None, None
            
        # 3. Save state
        await update_game_state(game_id, state)
        
        # 4. Sync to Firestore (fire and forget)
        asyncio.create_task(asyncio.to_thread(sync_to_firestore_sync, game_id, state))
        
        return True, "", state, event_to_broadcast

engine = GameEngine()
