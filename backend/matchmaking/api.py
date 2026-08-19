from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import json
import time

from .redis_client import redis_client

router = APIRouter(prefix="/api/matchmaking", tags=["matchmaking"])

class JoinQueueRequest(BaseModel):
    user_id: str
    username: str
    rating: int = 1200
    preferred_role: str = "ANY"  # "DEFENSE", "PROSECUTION", "ANY"

class StatusResponse(BaseModel):
    status: str
    game_id: Optional[str] = None
    opponent: Optional[dict] = None
    your_role: Optional[str] = None

@router.post("/join")
async def join_queue(req: JoinQueueRequest):
    """
    Adds a user to the matchmaking queue in Redis.
    """
    # 1. Store the user's data in a hash so we can retrieve it during matching
    user_data = {
        "user_id": req.user_id,
        "username": req.username,
        "rating": req.rating,
        "preferred_role": req.preferred_role,
        "joined_at": time.time(),
        "status": "WAITING"
    }
    
    await redis_client.hset(f"matchmaking:user:{req.user_id}", mapping=user_data)
    
    # 2. Add user to a sorted set for the queue (score = join time)
    await redis_client.zadd("matchmaking:queue", {req.user_id: user_data["joined_at"]})
    
    return {"success": True, "message": "Joined matchmaking queue."}


@router.post("/leave")
async def leave_queue(req: dict):
    """
    Removes a user from the matchmaking queue.
    Expected body: {"user_id": "..."}
    """
    user_id = req.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
        
    await redis_client.zrem("matchmaking:queue", user_id)
    await redis_client.delete(f"matchmaking:user:{user_id}")
    
    return {"success": True, "message": "Left matchmaking queue."}


@router.get("/status")
async def get_status(user_id: str):
    """
    Poll this endpoint to see if a match is found.
    """
    user_key = f"matchmaking:user:{user_id}"
    user_data = await redis_client.hgetall(user_key)
    
    if not user_data:
        # Maybe they cancelled or were never in queue
        return StatusResponse(status="NOT_IN_QUEUE")
        
    if user_data.get("status") == "MATCH_FOUND":
        # The worker matched them and populated these fields
        opponent = None
        if user_data.get("opponent"):
            try:
                opponent = json.loads(user_data["opponent"])
            except:
                pass
                
        # Optional: delete the user data once they've successfully polled the match
        # so it doesn't stay in Redis forever. We'll set an expire.
        await redis_client.expire(user_key, 60) 
                
        return StatusResponse(
            status="MATCH_FOUND",
            game_id=user_data.get("game_id"),
            your_role=user_data.get("your_role"),
            opponent=opponent
        )
        
    return StatusResponse(status="WAITING")
