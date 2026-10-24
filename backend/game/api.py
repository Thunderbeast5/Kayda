import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from typing import Dict, Any
from backend.agents.evidence.evidence_analyzer import _get_firestore_client
from backend.game.manager import manager
from backend.game.engine.state import init_game_state
from backend.game.engine.engine import engine
from datetime import datetime, timezone

game_router = APIRouter(prefix="/api/games", tags=["games"])
ws_router = APIRouter()

from backend.matchmaking.redis_client import redis_client
import json

async def _background_firestore_sync(game_id: str, game_data: dict):
    def _sync():
        try:
            db = _get_firestore_client()
            if db:
                db.collection("games").document(game_id).set(game_data, merge=True)
        except Exception as e:
            print(f"[API] Firestore sync skipped: {e}")
    try:
        await asyncio.wait_for(asyncio.to_thread(_sync), timeout=2.0)
    except Exception:
        pass

@game_router.get("/{game_id}")
async def get_game(game_id: str):
    # Try Redis first
    try:
        raw_doc = await redis_client.get(f"game_doc:{game_id}")
        if raw_doc:
            return {"success": True, "game": json.loads(raw_doc)}
    except Exception:
        pass
        
    try:
        def _get():
            db = _get_firestore_client()
            if db:
                doc = db.collection("games").document(game_id).get()
                if doc.exists:
                    return doc.to_dict()
            return None
        game = await asyncio.wait_for(asyncio.to_thread(_get), timeout=2.0)
        if game:
            return {"success": True, "game": game}
    except Exception:
        pass
        
    raise HTTPException(status_code=404, detail="Game not found")


@game_router.post("/{game_id}/ready")
async def ready_player(game_id: str, user_id: str = Query(...)):
    try:
        # 1. Fetch game doc from Redis or Firestore
        game_data = None
        raw_doc = await redis_client.get(f"game_doc:{game_id}")
        if raw_doc:
            game_data = json.loads(raw_doc)
            
        if not game_data:
            try:
                def _get():
                    db = _get_firestore_client()
                    if db:
                        doc = db.collection("games").document(game_id).get()
                        if doc.exists:
                            return doc.to_dict()
                    return None
                game_data = await asyncio.wait_for(asyncio.to_thread(_get), timeout=2.0)
            except Exception:
                pass
                
        if not game_data:
            raise HTTPException(status_code=404, detail="Game not found")

        # 2. Update player ready status
        players = game_data.get("players", [])
        updated = False
        for p in players:
            if p.get("type") == "AI":
                p["status"] = "READY"
            elif p.get("user_id") == user_id:
                p["status"] = "READY"
                updated = True
                
        if not updated:
            # If user not strictly matched, add them to avoid blocking
            players.append({"user_id": user_id, "type": "HUMAN", "status": "READY"})
            
        all_ready = all(p.get("status") == "READY" for p in players if p.get("type") == "HUMAN")
        print(f"[API] ready_player: user={user_id}, all_ready={all_ready}, players={[p.get('status') for p in players]}")
        
        if all_ready:
            game_data["status"] = "ACTIVE"
            game_data["phase"] = "OPENING"
            game_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            
        game_data["players"] = players
        
        # Persist to Redis
        await redis_client.set(f"game_doc:{game_id}", json.dumps(game_data))
        
        # Non-blocking async sync to Firestore in background
        asyncio.create_task(_background_firestore_sync(game_id, game_data))

        # Broadcast readiness over WebSocket
        await manager.broadcast(game_id, {
            "type": "PLAYER_READY",
            "player": {"user_id": user_id}
        })

        if all_ready:
            live_state = await init_game_state(game_id, game_data)
            
            await manager.broadcast(game_id, {
                "type": "GAME_STARTED",
                "game_id": game_id,
                "phase": live_state["phase"],
                "current_turn": live_state["current_turn"],
                "scores": live_state["scores"]
            })
            
            # Formally open the court with the Judge's address
            asyncio.create_task(engine.trigger_court_opening(game_id, live_state))
            
        return {"success": True, "ready": True, "game_started": all_ready}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@ws_router.websocket("/ws/games/{game_id}")
async def websocket_game_endpoint(websocket: WebSocket, game_id: str, user_id: str = Query(None)):
    if not user_id:
        print(f"[WS] Rejected: no user_id for game {game_id}")
        await websocket.close(code=1008)
        return
        
    try:
        game_data = None
        try:
            raw_doc = await redis_client.get(f"game_doc:{game_id}")
            if raw_doc:
                game_data = json.loads(raw_doc)
        except Exception:
            pass
            
        if not game_data:
            try:
                def _ws_get():
                    db = _get_firestore_client()
                    if db:
                        doc = db.collection("games").document(game_id).get()
                        if doc.exists:
                            return doc.to_dict()
                    return None
                game_data = await asyncio.wait_for(asyncio.to_thread(_ws_get), timeout=2.0)
            except Exception:
                pass
                
        if not game_data:
            print(f"[WS] Rejected: game {game_id} not found in Redis or Firestore")
            await websocket.close(code=1008)
            return
            
        players = game_data.get("players", [])
        is_player = any(p.get("user_id") == user_id for p in players)
        if not is_player:
            players.append({"user_id": user_id, "type": "HUMAN", "status": "CONNECTED"})
            game_data["players"] = players
            try:
                await redis_client.set(f"game_doc:{game_id}", json.dumps(game_data))
            except Exception:
                pass
                
        await manager.connect(websocket, game_id, user_id)
        
        # Optionally update Firestore to CONNECTED here, but broadcasting is sufficient for now
        await manager.broadcast(game_id, {
            "type": "PLAYER_CONNECTED",
            "player": {"user_id": user_id}
        })
        
        try:
            while True:
                action_data = await websocket.receive_json()
                success, error_msg, new_state, event_to_broadcast = await engine.process_action(game_id, user_id, action_data)
                
                if not success:
                    await websocket.send_json({"type": "ERROR", "message": error_msg})
                elif event_to_broadcast:
                    await manager.broadcast(game_id, event_to_broadcast)
                    
        except WebSocketDisconnect:
            manager.disconnect(game_id, user_id)
            await manager.broadcast(game_id, {
                "type": "PLAYER_DISCONNECTED",
                "player": {"user_id": user_id}
            })
            
    except Exception as e:
        print(f"[WebSocket] Error: {e}")
        try:
            await websocket.close(code=1011)
        except:
            pass
