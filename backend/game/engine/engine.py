from typing import Dict, Any, Tuple, Optional
from .state import get_game_state, update_game_state, sync_to_firestore_sync, record_action_event_sync
from .turn_manager import advance_turn
from .judge import game_judge
from backend.game.manager import manager
import asyncio
import os

# ── AI Counsel Generation ──────────────────────────────────────────────────────

async def _generate_ai_argument(
    case_id: str,
    ai_role: str,
    phase: str,
    transcript: list,
    last_human_argument: str
) -> str:
    """
    Generates an AI legal argument using OpenAI gpt-5.4-mini.
    Falls back to a deterministic heuristic if the API call fails.
    """
    ctx = game_judge.get_case_context(case_id)

    role_label = "Defense Counsel" if ai_role == "defense" else "Public Prosecutor"
    opposing_label = "Public Prosecutor" if ai_role == "defense" else "Defense Counsel"
    phase_instruction = {
        "OPENING":  f"Deliver your opening statement as {role_label}.",
        "ARGUMENT": f"Counter the {opposing_label}'s argument and advance your own submission as {role_label}.",
        "REBUTTAL": f"Rebut the {opposing_label}'s position and strengthen your case as {role_label}.",
    }.get(phase, f"Present your legal submission as {role_label}.")

    # Build transcript context (last 4 turns)
    transcript_lines = []
    for t in transcript[-4:]:
        r = "Prosecution" if t.get("role") in ["prosecutor", "prosecution"] else "Defense"
        transcript_lines.append(f"{r}: {t.get('text', '')[:200]}")
    transcript_ctx = "\n".join(transcript_lines) if transcript_lines else "No prior submissions."

    system_prompt = (
        f"You are the {role_label} in an Indian criminal court hearing. "
        f"Case: {ctx['title']}. Applicable law: {ctx['charges']}. "
        f"Reason strictly from Indian statutory law (IPC, CrPC, BNSS, BNS, Constitution). "
        f"Cite specific sections. Be formal, concise, and persuasive. "
        f"Write 3-5 sentences maximum."
    )

    user_prompt = (
        f"Trial Phase: {phase}\n"
        f"Opposing Counsel's Last Argument: \"{last_human_argument}\"\n"
        f"Prior Transcript:\n{transcript_ctx}\n\n"
        f"{phase_instruction} Respond directly to the opposing submission. "
        f"Cite at least one specific statutory provision or precedent."
    )

    # Try OpenAI API
    try:
        import openai
        client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=3.0)
        model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=300,
            temperature=0.7,
        )
        text = response.choices[0].message.content.strip()
        if text:
            return text
    except Exception as e:
        print(f"[AIOpponent] OpenAI call failed ({type(e).__name__}: {e}). Using heuristic fallback.")

    # Deterministic fallback
    if ai_role == "defense":
        return (
            f"May it please the Hon'ble Court. The {opposing_label}'s submissions are, with respect, legally unsound. "
            f"Under Section 438 CrPC, anticipatory bail is a right grounded in Article 21 of the Constitution. "
            f"There exists no credible prima facie evidence establishing a statutory ingredient of the offence charged under {ctx['charges']}. "
            f"We respectfully submit that custodial interrogation is wholly unwarranted and the petitioner cooperates fully with investigation. "
            f"The relief sought may therefore be graciously granted subject to appropriate conditions."
        )
    else:
        return (
            f"May it please this Hon'ble Court. The defense's submission must fail on first principles. "
            f"The State has established a credible prima facie nexus with the offences charged under {ctx['charges']}. "
            f"The accused's conduct discloses deliberate intent and the recovery of material evidence corroborates the FIR. "
            f"In the interest of unhindered investigation and public justice under Section 437 CrPC, anticipatory bail ought to be denied. "
            f"We respectfully pray this Court refuse the relief sought."
        )


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
            
            objection_event = {
                "type": "OBJECTION_RAISED",
                "player_id": user_id,
                "player_role": player_role,
                "text": reason,
                "timestamp": str(asyncio.get_event_loop().time())
            }
            
            asyncio.create_task(asyncio.to_thread(
                record_action_event_sync, game_id, user_id, "RAISE_OBJECTION", {"content": reason}, state.get("round", 1), state.get("phase", "ARGUMENT")
            ))
            
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
            
            asyncio.create_task(asyncio.to_thread(
                record_action_event_sync, game_id, user_id, action_type, {"content": text}, state["round"], current_phase
            ))
            
            # ── 3. Real-Time Judge Monitoring & Scoring ──
            history = state.get("transcript", [])
            score_breakdown, score_delta, citations = await game_judge.evaluate_argument(
                case_id, player_role, current_phase, text, history
            )
            
            state.setdefault("scores", {"prosecution": 0, "defense": 0})
            state["scores"][player_role] = state["scores"].get(player_role, 0) + score_delta
            
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
                "player_role": player_role,
                "payload": {"content": text, "text": text},
                "next_turn": state["current_turn"],
                "phase": state["phase"],
                "scores": state["scores"]
            }
            
            # ── 4. Check Phase & Schedule Judge Reaction / AI Opponent ──
            if state["phase"] == "JUDGMENT":
                asyncio.create_task(self.trigger_verdict(game_id, state))
            else:
                asyncio.create_task(self.trigger_judge_intervention(
                    game_id, case_id, player_role, current_phase, text, score_breakdown, state["current_turn"]
                ))
                
                # ── 5. If next turn is the AI opponent, generate its argument ──
                ai_id = state.get("ai_opponent_id")
                if ai_id and state["current_turn"] == ai_id:
                    ai_role = state.get("ai_role", "defense")
                    asyncio.create_task(self.trigger_ai_opponent_turn(
                        game_id, case_id, ai_id, ai_role, state["phase"], text, state
                    ))
        else:
            return False, f"Unknown action: {action_type}", None, None
            
        # Save state to Redis
        await update_game_state(game_id, state)
        asyncio.create_task(asyncio.to_thread(sync_to_firestore_sync, game_id, state))
        
        return True, "", state, event_to_broadcast

    # ──────────────────────────────────────────────────────────────────────────
    # AI Opponent Turn
    # ──────────────────────────────────────────────────────────────────────────

    async def trigger_ai_opponent_turn(
        self,
        game_id: str,
        case_id: str,
        ai_user_id: str,
        ai_role: str,
        phase: str,
        last_human_text: str,
        state: Dict[str, Any]
    ):
        """
        Generates and broadcasts the AI opposing counsel's argument after
        the human player submits. Waits 2.5s so the Judge's remark appears first.
        """
        await asyncio.sleep(2.5)

        current_state = await get_game_state(game_id)
        if not current_state or current_state.get("status") != "ACTIVE":
            return
        if current_state.get("current_turn") != ai_user_id:
            return

        ai_text = await _generate_ai_argument(
            case_id=case_id,
            ai_role=ai_role,
            phase=phase,
            transcript=current_state.get("transcript", []),
            last_human_argument=last_human_text
        )

        score_breakdown, score_delta, citations = await game_judge.evaluate_argument(
            case_id, ai_role, phase, ai_text, current_state.get("transcript", [])
        )

        current_state.setdefault("scores", {"prosecution": 0, "defense": 0})
        current_state["scores"][ai_role] = current_state["scores"].get(ai_role, 0) + score_delta
        current_state.setdefault("transcript", []).append({
            "role": ai_role,
            "text": ai_text,
            "phase": phase,
            "citations": citations,
            "score_delta": score_delta
        })

        current_state = advance_turn(current_state)

        await update_game_state(game_id, current_state)
        asyncio.create_task(asyncio.to_thread(sync_to_firestore_sync, game_id, current_state))

        action_map = {"OPENING": "SUBMIT_OPENING", "REBUTTAL": "SUBMIT_REBUTTAL"}
        ai_action = action_map.get(phase, "SUBMIT_ARGUMENT")
        asyncio.create_task(asyncio.to_thread(
            record_action_event_sync, game_id, ai_user_id, ai_action,
            {"content": ai_text}, current_state.get("round", 1), phase
        ))

        ai_event = {
            "type": "ACTION_SUBMITTED",
            "action": ai_action,
            "player_id": ai_user_id,
            "player_role": ai_role,
            "payload": {"content": ai_text, "text": ai_text},
            "next_turn": current_state["current_turn"],
            "phase": current_state["phase"],
            "scores": current_state["scores"]
        }
        await manager.broadcast(game_id, ai_event)

        if current_state["phase"] != "JUDGMENT":
            asyncio.create_task(self.trigger_judge_intervention(
                game_id, case_id, ai_role, phase, ai_text, score_breakdown, current_state["current_turn"]
            ))
        else:
            asyncio.create_task(self.trigger_verdict(game_id, current_state))

    # ──────────────────────────────────────────────────────────────────────────
    # Asynchronous Judge Broadcast Routines
    # ──────────────────────────────────────────────────────────────────────────

    async def trigger_court_opening(self, game_id: str, live_state: Dict[str, Any]):
        await asyncio.sleep(1.2)
        case_id = live_state.get("case_id", "1")
        opening_text = await game_judge.generate_opening_address(case_id)
        
        judge_event = {
            "type": "JUDGE_MESSAGE",
            "agent_id": "judge",
            "display_name": "Hon'ble Judge",
            "content": opening_text,
            "citations": ["Court Initiation"],
            "interruption_type": "ANNOUNCEMENT",
            "active_turn": live_state.get("current_turn"),
            "phase": live_state.get("phase", "CASE_INTRO")
        }
        await manager.broadcast(game_id, judge_event)

    async def _announce_opening_phase(self, game_id: str, state: Dict[str, Any]):
        await asyncio.sleep(1.0)
        judge_event = {
            "type": "JUDGE_MESSAGE",
            "agent_id": "judge",
            "display_name": "Hon'ble Judge",
            "content": "The bench is prepared to hear opening submissions. Public Prosecutor, present your opening framing.",
            "citations": [],
            "interruption_type": "PROCEED",
            "active_turn": state.get("current_turn"),
            "phase": "OPENING"
        }
        await manager.broadcast(game_id, judge_event)

        # If AI opponent is prosecution, auto-trigger their opening submission
        ai_id = state.get("ai_opponent_id")
        if ai_id and state.get("current_turn") == ai_id:
            case_id = state.get("case_id", "1")
            ai_role = state.get("ai_role", "prosecution")
            asyncio.create_task(self.trigger_ai_opponent_turn(
                game_id, case_id, ai_id, ai_role, "OPENING", "", state
            ))

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
                "display_name": "Hon'ble Judge",
                "content": reaction["content"],
                "citations": reaction.get("citations", []),
                "interruption_type": reaction.get("interruption_type", "OBSERVATION"),
                "target_role": reaction.get("target_role"),
                "active_turn": next_turn,
                "scores": state.get("scores") if state else None
            }
            await manager.broadcast(game_id, judge_event)
            
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
        await asyncio.sleep(1.0)
        state = await get_game_state(game_id)
        last_arg = None
        if state and state.get("transcript"):
            last_arg = state["transcript"][-1].get("text")
        ruling = await game_judge.rule_on_objection(case_id, objecting_role, reason, last_argument=last_arg)
        
        judge_event = {
            "type": "JUDGE_MESSAGE",
            "agent_id": "judge",
            "display_name": "Hon'ble Judge",
            "content": ruling["content"],
            "citations": ruling.get("citations", []),
            "interruption_type": "RULING",
            "ruling": ruling["ruling"],
            "active_turn": active_turn
        }
        await manager.broadcast(game_id, judge_event)
        
        asyncio.create_task(asyncio.to_thread(
            record_action_event_sync, game_id, "ai_judge", "OBJECTION_RULING",
            {"ruling": ruling["ruling"], "content": ruling["content"]},
            1, "TRIAL"
        ))

    async def trigger_verdict(self, game_id: str, state: Dict[str, Any]):
        await asyncio.sleep(2.0)
        case_id = state.get("case_id", "1")
        scores = state.get("scores", {"prosecution": 0, "defense": 0})
        transcript = state.get("transcript", [])
        
        verdict = await game_judge.render_final_verdict(case_id, scores, transcript)
        
        verdict_event = {
            "type": "JUDGE_MESSAGE",
            "agent_id": "judge",
            "display_name": "Hon'ble Judge — Final Order",
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

