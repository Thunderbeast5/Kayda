import asyncio
import json
import random
import time
import sys
from typing import Optional
from datetime import datetime, timezone

from .redis_client import redis_client, hset_mapping
from backend.observer.case_service import list_cases
from backend.agents.evidence.evidence_analyzer import _get_firestore_client

async def matchmaking_loop():
    """
    Background worker that continuously scans the Redis queue to pair players.
    """
    print("[Matchmaking] Worker started...", file=sys.stderr)
    last_error_was_conn = False
    while True:
        try:
            await match_players()
            if last_error_was_conn:
                print("[Matchmaking] Redis connection established. Queue scanning active.", file=sys.stderr)
                last_error_was_conn = False
            await asyncio.sleep(2)
        except Exception as e:
            err_str = str(e)
            is_conn_error = "Connect call failed" in err_str or "ConnectionRefusedError" in err_str or "ConnectionError" in type(e).__name__
            if is_conn_error:
                if not last_error_was_conn:
                    print("[Matchmaking] Waiting for Redis connection at 127.0.0.1:6379...", file=sys.stderr)
                    last_error_was_conn = True
                await asyncio.sleep(5)
            else:
                print(f"[Matchmaking] Error in worker loop: {e}", file=sys.stderr)
                await asyncio.sleep(2)

async def match_players():
    # Get all users currently in the queue, sorted by join time (oldest first)
    queue = await redis_client.zrange("matchmaking:queue", 0, -1, withscores=False)
    if len(queue) < 2:
        return
        
    # We will fetch their data to see who is compatible
    users_data = []
    for uid in queue:
        data = await redis_client.hgetall(f"matchmaking:user:{uid}")
        if not data or data.get("status") != "WAITING":
            await redis_client.zrem("matchmaking:queue", uid)
            continue
        data["rating"] = int(data.get("rating", 1200))
        data["joined_at"] = float(data.get("joined_at", time.time()))
        users_data.append(data)
            
    # Try to find a valid pair
    matched_pair = None
    now = time.time()
    
    for i in range(len(users_data)):
        for j in range(i + 1, len(users_data)):
            p1 = users_data[i]
            p2 = users_data[j]
            
            # Condition 1: Not the same user
            if p1["user_id"] == p2["user_id"]:
                continue
                
            r1 = p1.get("preferred_role", "ANY").upper()
            r2 = p2.get("preferred_role", "ANY").upper()
            
            p1_final_role = None
            p2_final_role = None
            
            if r1 == "DEFENSE" and r2 == "PROSECUTION":
                p1_final_role, p2_final_role = "DEFENSE", "PROSECUTION"
            elif r1 == "PROSECUTION" and r2 == "DEFENSE":
                p1_final_role, p2_final_role = "PROSECUTION", "DEFENSE"
            elif r1 == "ANY" and r2 != "ANY":
                p2_final_role = r2
                p1_final_role = "PROSECUTION" if r2 == "DEFENSE" else "DEFENSE"
            elif r2 == "ANY" and r1 != "ANY":
                p1_final_role = r1
                p2_final_role = "PROSECUTION" if r1 == "DEFENSE" else "DEFENSE"
            elif r1 == "ANY" and r2 == "ANY":
                roles = ["DEFENSE", "PROSECUTION"]
                random.shuffle(roles)
                p1_final_role, p2_final_role = roles[0], roles[1]
            else:
                # Both requested the SAME strict role (e.g. both DEFENSE).
                # If either player has been waiting > 30 seconds, relax and assign roles randomly.
                p1_wait = now - p1.get("joined_at", now)
                p2_wait = now - p2.get("joined_at", now)
                if p1_wait >= 30 or p2_wait >= 30:
                    roles = ["DEFENSE", "PROSECUTION"]
                    random.shuffle(roles)
                    p1_final_role, p2_final_role = roles[0], roles[1]
                    print(f"[Matchmaking] Role relaxation applied after {max(p1_wait, p2_wait):.0f}s wait")
                else:
                    # Keep waiting for a proper complement
                    continue
                
            matched_pair = (p1, p2, p1_final_role, p2_final_role)
            break
            
        if matched_pair:
            break
            
    if matched_pair:
        p1, p2, p1_role, p2_role = matched_pair
        
        print(f"[Matchmaking] Match found: {p1['user_id']} ({p1_role}) vs {p2['user_id']} ({p2_role})")
        
        # 1. Remove both from queue
        await redis_client.zrem("matchmaking:queue", p1["user_id"], p2["user_id"])
        
        # 2. Pick a random case
        cases = list_cases()
        case_id = cases[0]["id"] if cases else "demo_case_id"
        if cases:
            case_id = random.choice(cases)["id"]
            
        # 3. Create the game in Redis (and Firestore if available)
        game_id = f"G_{int(time.time())}_{random.randint(100, 999)}"
        game_doc = {
            "mode": "MULTIPLAYER",
            "case_id": case_id,
            "status": "WAITING_FOR_PLAYERS",
            "phase": "CASE_INTRO",
            "current_turn": None,
            "round": 0,
            "created_by": "matchmaker",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "players": [
                {
                    "user_id": p1["user_id"],
                    "role": p1_role,
                    "type": "HUMAN",
                    "display_name": p1.get("username", "Player 1"),
                    "status": "WAITING"
                },
                {
                    "user_id": p2["user_id"],
                    "role": p2_role,
                    "type": "HUMAN",
                    "display_name": p2.get("username", "Player 2"),
                    "status": "WAITING"
                },
                {
                    "role": "JUDGE",
                    "type": "AI",
                    "display_name": "AI Judge",
                    "status": "READY"
                }
            ]
        }
        
        # Always persist game_doc in Redis so ready_player and engine can access it instantly
        await redis_client.set(f"game_doc:{game_id}", json.dumps(game_doc))
        
        try:
            db = _get_firestore_client()
            if db:
                game_ref = db.collection("games").document(game_id)
                await asyncio.to_thread(game_ref.set, game_doc)
                print(f"[Matchmaking] Synced game {game_id} to Firestore.")
        except Exception as e:
            print(f"[Matchmaking] Firestore sync bypassed ({e}). Using Redis game.")
            
        # 4. Update both players in Redis with MATCH_FOUND
        p1_opponent = {"username": p2.get("username", "Player 2"), "rating": p2.get("rating", 1200)}
        p2_opponent = {"username": p1.get("username", "Player 1"), "rating": p1.get("rating", 1200)}
        
        await hset_mapping(f"matchmaking:user:{p1['user_id']}", {
            "status": "MATCH_FOUND",
            "game_id": game_id,
            "your_role": p1_role,
            "opponent": json.dumps(p1_opponent)
        })
        
        await hset_mapping(f"matchmaking:user:{p2['user_id']}", {
            "status": "MATCH_FOUND",
            "game_id": game_id,
            "your_role": p2_role,
            "opponent": json.dumps(p2_opponent)
        })

def start_matchmaking_worker():
    """
    Helper to create the background task.
    """
    asyncio.create_task(matchmaking_loop())

if __name__ == "__main__":
    import asyncio
    print("Starting Matchmaking Worker...")
    asyncio.run(matchmaking_loop())
