import json
from typing import Dict, Any, Optional
from backend.matchmaking.redis_client import redis_client
from backend.agents.evidence.evidence_analyzer import _get_firestore_client

async def init_game_state(game_id: str, firestore_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Initializes the live game state in Redis when a game starts.
    """
    # Build baseline live state
    players = firestore_data.get("players", [])
    
    prosecution_id = next((p.get("user_id") for p in players if p.get("role") == "PROSECUTION"), None)
    defense_id = next((p.get("user_id") for p in players if p.get("role") == "DEFENSE"), None)
    
    state = {
        "game_id": game_id,
        "phase": "CASE_INTRO",
        "round": 1,
        "current_turn": prosecution_id,  # Prosecution usually starts
        "players": {
            "prosecution": prosecution_id,
            "defense": defense_id
        },
        "scores": {
            "prosecution": 0,
            "defense": 0
        },
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
        
        # We only sync core fields that need persistence right now
        updates = {
            "phase": state.get("phase"),
            "round": state.get("round"),
            "status": state.get("status"),
            "current_turn": state.get("current_turn")
        }
        game_ref.update(updates)
    except Exception as e:
        print(f"[State] Failed to sync to firestore: {e}")
