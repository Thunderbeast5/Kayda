from typing import Dict, Any, Tuple, Optional
from .state import get_game_state, update_game_state, sync_to_firestore_sync, record_action_event_sync
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
        
        turn_required_actions = ["END_TURN", "SUBMIT_OPENING", "SUBMIT_ARGUMENT", "SUBMIT_REBUTTAL"]
        
        if action_type in turn_required_actions and not is_turn:
            return False, "Not your turn", None, None
            
        current_phase = state.get("phase")
        
        # 2. Process Action
        event_to_broadcast = None
        
        if action_type == "END_TURN":
            state = advance_turn(state)
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
                
        elif action_type in ["SUBMIT_OPENING", "SUBMIT_ARGUMENT", "SUBMIT_REBUTTAL"]:
            # Validate Phase
            if action_type == "SUBMIT_OPENING" and current_phase != "OPENING":
                return False, f"Action {action_type} not allowed in phase {current_phase}", None, None
            if action_type == "SUBMIT_ARGUMENT" and current_phase != "ARGUMENT":
                return False, f"Action {action_type} not allowed in phase {current_phase}", None, None
            if action_type == "SUBMIT_REBUTTAL" and current_phase != "REBUTTAL":
                return False, f"Action {action_type} not allowed in phase {current_phase}", None, None
                
            text = action_payload.get("text", "")
            
            # Save Event to Firestore
            asyncio.create_task(asyncio.to_thread(
                record_action_event_sync, game_id, user_id, action_type, {"content": text}, state["round"], current_phase
            ))
            
            # Advance Turn automatically
            state = advance_turn(state)
            
            event_to_broadcast = {
                "type": "ACTION_SUBMITTED",
                "action": action_type,
                "player_id": user_id,
                "payload": {"content": text},
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
