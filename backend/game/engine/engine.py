from typing import Dict, Any, Tuple, Optional
from .state import get_game_state, update_game_state, sync_to_firestore_sync, record_action_event_sync
from .turn_manager import advance_turn
from .judge import game_judge
from backend.game.manager import manager
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
            
        # Determine player role
        prosecution_id = state.get("players", {}).get("prosecution")
        defense_id = state.get("players", {}).get("defense")
        player_role = "prosecution" if user_id == prosecution_id else ("defense" if user_id == defense_id else None)
        
        if not player_role:
            return False, "User is not a counsel in this courtroom", None, None

        # ── 1. Handle In-Court Objections (allowed anytime) ──
        if action_type == "RAISE_OBJECTION":
            reason = action_payload.get("text") or action_payload.get("reason") or "Counsel raises formal objection."
            case_id = state.get("case_id", "1")
            
            # Broadcast the objection immediately
            objection_event = {
                "type": "OBJECTION_RAISED",
                "player_id": user_id,
                "player_role": player_role,
                "text": reason,
                "timestamp": str(asyncio.get_event_loop().time())
            }
            
            # Record in Firestore
            asyncio.create_task(asyncio.to_thread(
                record_action_event_sync, game_id, user_id, "RAISE_OBJECTION", {"content": reason}, state.get("round", 1), state.get("phase", "ARGUMENT")
            ))
            
            # Schedule Judge's immediate ruling after 1 second
            asyncio.create_task(self._handle_judge_objection_ruling(game_id, case_id, player_role, reason, state.get("current_turn")))
            
            return True, "", state, objection_event

        # ── 2. Validate user's turn for speech actions ──
        is_turn = (state.get("current_turn") == user_id)
        turn_required_actions = ["END_TURN", "SUBMIT_OPENING", "SUBMIT_ARGUMENT", "SUBMIT_REBUTTAL"]
        
        if action_type in turn_required_actions and not is_turn:
            return False, "Not your turn", None, None
            
        current_phase = state.get("phase")
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
                # If advancing from CASE_INTRO to OPENING, have Judge announce
                if current_phase == "CASE_INTRO" and state["phase"] == "OPENING":
                    asyncio.create_task(self._announce_opening_phase(game_id, state))
                
        elif action_type in ["SUBMIT_OPENING", "SUBMIT_ARGUMENT", "SUBMIT_REBUTTAL"]:
            # Validate Phase
            if action_type == "SUBMIT_OPENING" and current_phase != "OPENING":
                return False, f"Action {action_type} not allowed in phase {current_phase}", None, None
            if action_type == "SUBMIT_ARGUMENT" and current_phase != "ARGUMENT":
                return False, f"Action {action_type} not allowed in phase {current_phase}", None, None
            if action_type == "SUBMIT_REBUTTAL" and current_phase != "REBUTTAL":
                return False, f"Action {action_type} not allowed in phase {current_phase}", None, None
                
            text = action_payload.get("text", "")
            case_id = state.get("case_id", "1")
            
            # Save Event to Firestore
            asyncio.create_task(asyncio.to_thread(
                record_action_event_sync, game_id, user_id, action_type, {"content": text}, state["round"], current_phase
            ))
            
            # ── 3. Real-Time Judge Monitoring & Scoring ──
            history = state.get("transcript", [])
            score_breakdown, score_delta, citations = await game_judge.evaluate_argument(
                case_id, player_role, current_phase, text, history
            )
            
            # Update cumulative scores
            state.setdefault("scores", {"prosecution": 0, "defense": 0})
            state["scores"][player_role] = state["scores"].get(player_role, 0) + score_delta
            
            # Append to transcript in state
            state.setdefault("transcript", []).append({
                "role": player_role,
                "text": text,
                "phase": current_phase,
                "citations": citations,
                "score_delta": score_delta
            })
            
            # Advance Turn
            state = advance_turn(state)
            
            event_to_broadcast = {
                "type": "ACTION_SUBMITTED",
                "action": action_type,
                "player_id": user_id,
                "payload": {"content": text},
                "next_turn": state["current_turn"],
                "phase": state["phase"],
                "scores": state["scores"]
            }
            
            # ── 4. Check Phase & Schedule Judge Reaction ──
            if state["phase"] == "JUDGMENT":
                # All arguments complete! Trigger final judgment and verdict
                asyncio.create_task(self.trigger_verdict(game_id, state))
            else:
                # Active trial: trigger judicial observation, question or interruption
                asyncio.create_task(self.trigger_judge_intervention(
                    game_id, case_id, player_role, current_phase, text, score_breakdown, state["current_turn"]
                ))
        else:
            return False, f"Unknown action: {action_type}", None, None
            
        # 5. Save state to Redis
        await update_game_state(game_id, state)
        
        # 6. Sync to Firestore (fire and forget)
        asyncio.create_task(asyncio.to_thread(sync_to_firestore_sync, game_id, state))
        
        return True, "", state, event_to_broadcast

    # ──────────────────────────────────────────────────────────────────────────
    # Asynchronous Judge Broadcast Routines
    # ──────────────────────────────────────────────────────────────────────────

    async def trigger_court_opening(self, game_id: str, live_state: Dict[str, Any]):
        """
        Called when all players connect and game starts.
        The Judge formally welcomes the court and invites counsel to proceed.
        """
        await asyncio.sleep(1.2)
        case_id = live_state.get("case_id", "1")
        opening_text = await game_judge.generate_opening_address(case_id)
        
        judge_event = {
            "type": "JUDGE_MESSAGE",
            "agent_id": "judge",
            "display_name": "Hon’ble Judge",
            "content": opening_text,
            "citations": ["Court Initiation"],
            "interruption_type": "ANNOUNCEMENT",
            "active_turn": live_state.get("current_turn"),
            "phase": live_state.get("phase", "CASE_INTRO")
        }
        await manager.broadcast(game_id, judge_event)

    async def _announce_opening_phase(self, game_id: str, state: Dict[str, Any]):
        """Announces commencement of opening statements."""
        await asyncio.sleep(1.0)
        judge_event = {
            "type": "JUDGE_MESSAGE",
            "agent_id": "judge",
            "display_name": "Hon’ble Judge",
            "content": "The bench is prepared to hear opening submissions. Public Prosecutor, present your opening framing.",
            "citations": [],
            "interruption_type": "PROCEED",
            "active_turn": state.get("current_turn"),
            "phase": "OPENING"
        }
        await manager.broadcast(game_id, judge_event)

    async def trigger_judge_intervention(
        self,
        game_id: str,
        case_id: str,
        role: str,
        phase: str,
        argument_text: str,
        scores: Dict[str, int],
        next_turn: Optional[str]
    ):
        """
        Evaluates whether the Judge should interrupt, ask a question, or make an observation.
        """
        # Natural pause so it feels like the judge is reflecting on counsel's argument
        await asyncio.sleep(1.5)
        
        state = await get_game_state(game_id)
        history = state.get("transcript", []) if state else []
        
        reaction = await game_judge.generate_interruption_or_question(
            case_id, role, phase, argument_text, scores, history
        )
        
        if reaction:
            judge_event = {
                "type": "JUDGE_MESSAGE",
                "agent_id": "judge",
                "display_name": "Hon’ble Judge",
                "content": reaction["content"],
                "citations": reaction.get("citations", []),
                "interruption_type": reaction.get("interruption_type", "OBSERVATION"),
                "target_role": reaction.get("target_role"),
                "active_turn": next_turn,
                "scores": state.get("scores") if state else None
            }
            await manager.broadcast(game_id, judge_event)
            
            # Record in Firestore events
            asyncio.create_task(asyncio.to_thread(
                record_action_event_sync, game_id, "ai_judge", "JUDGE_INTERVENTION",
                {"content": reaction["content"], "type": reaction.get("interruption_type")},
                state.get("round", 1) if state else 1, phase
            ))

    async def _handle_judge_objection_ruling(
        self,
        game_id: str,
        case_id: str,
        objecting_role: str,
        reason: str,
        active_turn: Optional[str]
    ):
        """Processes and broadcasts an immediate judicial ruling on an objection."""
        await asyncio.sleep(1.0)
        state = await get_game_state(game_id)
        last_arg = None
        if state and state.get("transcript"):
            last_arg = state["transcript"][-1].get("text")
        ruling = await game_judge.rule_on_objection(case_id, objecting_role, reason, last_argument=last_arg)
        
        judge_event = {
            "type": "JUDGE_MESSAGE",
            "agent_id": "judge",
            "display_name": "Hon’ble Judge",
            "content": ruling["content"],
            "citations": ruling.get("citations", []),
            "interruption_type": "RULING",
            "ruling": ruling["ruling"],
            "active_turn": active_turn
        }
        await manager.broadcast(game_id, judge_event)
        
        # Record in Firestore events
        asyncio.create_task(asyncio.to_thread(
            record_action_event_sync, game_id, "ai_judge", "OBJECTION_RULING",
            {"ruling": ruling["ruling"], "content": ruling["content"]},
            1, "TRIAL"
        ))

    async def trigger_verdict(self, game_id: str, state: Dict[str, Any]):
        """
        Executes the JUDGMENT phase: delivers judicial findings and final verdict,
        completing the trial.
        """
        await asyncio.sleep(2.0)
        case_id = state.get("case_id", "1")
        scores = state.get("scores", {"prosecution": 0, "defense": 0})
        transcript = state.get("transcript", [])
        
        verdict = await game_judge.render_final_verdict(case_id, scores, transcript)
        
        # 1. Broadcast the Judge's spoken final order
        verdict_event = {
            "type": "JUDGE_MESSAGE",
            "agent_id": "judge",
            "display_name": "Hon’ble Judge — Final Order",
            "content": verdict["summary"],
            "citations": verdict.get("citations", []),
            "interruption_type": "VERDICT",
            "verdict": verdict["verdict"],
            "winner": verdict["winner"],
            "scores": scores
        }
        await manager.broadcast(game_id, verdict_event)
        
        # 2. Advance state to COMPLETED
        state["phase"] = "COMPLETED"
        state["status"] = "COMPLETED"
        state["current_turn"] = None
        state["turn"] = None
        state["winner"] = verdict["winner"]
        state["verdict"] = verdict["verdict"]
        
        await update_game_state(game_id, state)
        asyncio.create_task(asyncio.to_thread(sync_to_firestore_sync, game_id, state))
        
        await asyncio.sleep(1.0)
        # 3. Broadcast GAME_COMPLETED
        completion_event = {
            "type": "GAME_COMPLETED",
            "winner": verdict["winner"],
            "verdict": verdict["verdict"],
            "scores": scores,
            "verdict_summary": verdict["summary"]
        }
        await manager.broadcast(game_id, completion_event)

engine = GameEngine()

