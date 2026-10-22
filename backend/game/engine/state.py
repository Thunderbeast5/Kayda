import json
from typing import Dict, Any, Optional
from backend.matchmaking.redis_client import redis_client
from backend.agents.evidence.evidence_analyzer import _get_firestore_client

async def init_game_state(game_id: str, firestore_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Initializes the live game state in Redis when a game starts.
    Guarantees both prosecution and defense slots are filled,
    registering the AI opponent when playing in Human vs AI mode.
    """
    # Build baseline live state
    players = firestore_data.get("players", [])
    
    prosecution_id = next((p.get("user_id") for p in players if p.get("role") == "PROSECUTION" and p.get("user_id")), None)
    defense_id = next((p.get("user_id") for p in players if p.get("role") == "DEFENSE" and p.get("user_id")), None)
    
    ai_opponent_id = None
    ai_role = None

    # Detect any AI player in the game doc
    for p in players:
        if p.get("type") == "AI" and p.get("role") in ("PROSECUTION", "DEFENSE"):
            role_lower = "prosecution" if p.get("role") == "PROSECUTION" else "defense"
            ai_role = role_lower
            ai_opponent_id = p.get("user_id") or f"ai_{role_lower}_{game_id}"
            p["user_id"] = ai_opponent_id
            if role_lower == "prosecution":
                prosecution_id = ai_opponent_id
            else:
                defense_id = ai_opponent_id

    # If only one role was filled by human, automatically configure the other as AI opponent
    if not defense_id and prosecution_id:
        defense_id = f"ai_defense_{game_id}"
        ai_opponent_id = defense_id
        ai_role = "defense"
    elif not prosecution_id and defense_id:
        prosecution_id = f"ai_prosecution_{game_id}"
        ai_opponent_id = prosecution_id
        ai_role = "prosecution"
    
    state = {
        "game_id": game_id,
        "case_id": str(firestore_data.get("case_id", "1")),
        "phase": "CASE_INTRO",
        "round": 1,
        "current_turn": prosecution_id,  # Prosecution starts
        "players": {
            "prosecution": prosecution_id,
            "defense": defense_id
        },
        "ai_opponent_id": ai_opponent_id,
        "ai_role": ai_role,
        "scores": {
            "prosecution": 0,
            "defense": 0
        },
        "transcript": [],
        "turn": {
            "player_id": prosecution_id,
            "started_at": 0,
            "time_remaining": 120
        },
        "status": "ACTIVE"
    }
    
    # Save to Redis
    await redis_client.set(f"game:{game_id}", json.dumps(state))
    return state

async def get_game_state(game_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves the live game state from Redis.
    """
    data = await redis_client.get(f"game:{game_id}")
    if data:
        return json.loads(data)
    return None

async def update_game_state(game_id: str, state: Dict[str, Any]) -> None:
    """
    Overwrites the live game state in Redis.
    """
    await redis_client.set(f"game:{game_id}", json.dumps(state))

def sync_to_firestore_sync(game_id: str, state: Dict[str, Any]) -> None:
    """
    Synchronous helper to push state to Firestore (meant to be run in asyncio.to_thread).
    """
    try:
        db = _get_firestore_client()
        game_ref = db.collection("games").document(game_id)
        
        # We sync core fields that need persistence
        updates = {
            "phase": state.get("phase"),
            "round": state.get("round"),
            "status": state.get("status"),
            "current_turn": state.get("current_turn"),
            "scores": state.get("scores", {"prosecution": 0, "defense": 0})
        }
        game_ref.update(updates)
    except Exception as e:
        print(f"[State] Failed to sync to firestore: {e}")

def record_action_event_sync(game_id: str, user_id: str, action_type: str, payload: Dict[str, Any], round_num: int, phase: str) -> None:
    """
    Synchronous helper to record a discrete game action event in Firestore.
    """
    try:
        from datetime import datetime, timezone
        import uuid
        db = _get_firestore_client()
        events_ref = db.collection("games").document(game_id).collection("events")
        
        event_doc = {
            "event_id": f"EVT_{uuid.uuid4().hex[:8]}",
            "user_id": user_id,
            "type": action_type,
            "payload": payload,
            "round": round_num,
            "phase": phase,
            "timestamp": datetime.now(timezone.utc)
        }
        
        events_ref.add(event_doc)
    except Exception as e:
        print(f"[State] Failed to record event in firestore: {e}")
