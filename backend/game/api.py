import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from typing import Dict, Any
from agents.evidence.evidence_analyzer import _get_firestore_client
from backend.game.manager import manager
from datetime import datetime, timezone

game_router = APIRouter(prefix="/api/games", tags=["games"])
ws_router = APIRouter()

@game_router.get("/{game_id}")
async def get_game(game_id: str):
    try:
        db = _get_firestore_client()
        doc = db.collection("games").document(game_id).get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Game not found")
        return {"success": True, "game": doc.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@game_router.post("/{game_id}/ready")
async def ready_player(game_id: str, user_id: str = Query(...)):
    try:
        db = _get_firestore_client()
        game_ref = db.collection("games").document(game_id)
        
        def _update_ready():
            doc = game_ref.get()
            if not doc.exists:
                raise HTTPException(status_code=404, detail="Game not found")
            
            data = doc.to_dict()
            players = data.get("players", [])
            updated = False
            all_ready = True
            
            for p in players:
                # the AI Judge is auto-READY
                if p.get("type") == "AI":
                    p["status"] = "READY"
                elif p.get("user_id") == user_id:
                    p["status"] = "READY"
                    updated = True
                
                if p.get("status") != "READY":
                    all_ready = False
                    
            if not updated:
                raise HTTPException(status_code=400, detail="User not in this game")
            
            updates = {"players": players}
            if all_ready:
                updates["status"] = "ACTIVE"
                updates["phase"] = "CASE_INTRO"
                updates["updated_at"] = datetime.now(timezone.utc)
                
            game_ref.update(updates)
            return all_ready

        all_ready = await asyncio.to_thread(_update_ready)
        
        # Broadcast readiness
        await manager.broadcast(game_id, {
            "type": "PLAYER_READY",
            "player": {"user_id": user_id}
        })
        
        if all_ready:
            await manager.broadcast(game_id, {
                "type": "GAME_STARTED",
                "phase": "CASE_INTRO"
            })
            
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
        db = _get_firestore_client()
        doc = await asyncio.to_thread(db.collection("games").document(game_id).get)
        if not doc.exists:
            print(f"[WS] Rejected: doc {game_id} does not exist")
            await websocket.close(code=1008)
            return
            
        data = doc.to_dict()
        players = data.get("players", [])
        
        # Verify user is in game
        is_player = any(p.get("user_id") == user_id for p in players)
        if not is_player:
            print(f"[WS] Rejected: user {user_id} not in players {players}")
            await websocket.close(code=1008)
            return
            
        await manager.connect(websocket, game_id, user_id)
        
        # Optionally update Firestore to CONNECTED here, but broadcasting is sufficient for now
        await manager.broadcast(game_id, {
            "type": "PLAYER_CONNECTED",
            "player": {"user_id": user_id}
        })
        
        try:
            while True:
                data = await websocket.receive_json()
                # Handle incoming ws messages here in the future
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
