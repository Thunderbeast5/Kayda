import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from typing import Dict, Any
from agents.evidence.evidence_analyzer import _get_firestore_client
from backend.game.manager import manager
from backend.game.engine.state import init_game_state
from backend.game.engine.engine import engine
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
        
        from google.cloud import firestore
        
        @firestore.transactional
        def _update_ready_transaction(transaction, doc_ref):
            doc = doc_ref.get(transaction=transaction)
            if not doc.exists:
                raise HTTPException(status_code=404, detail="Game not found")
            
            data = doc.to_dict()
            players = data.get("players", [])
            updated = False
            
            for p in players:
                # the AI Judge is auto-READY
                if p.get("type") == "AI":
                    p["status"] = "READY"
                elif p.get("user_id") == user_id:
                    p["status"] = "READY"
                    updated = True
                
            all_ready = all(p.get("status") == "READY" for p in players)
            print(f"[API] _update_ready_transaction: all_ready={all_ready}, players={[p.get('status') for p in players]}")
            
            if not updated:
                raise HTTPException(status_code=400, detail="User not in this game")
            
            updates = {"players": players}
            if all_ready:
                updates["status"] = "ACTIVE"
                updates["phase"] = "CASE_INTRO"
                updates["updated_at"] = datetime.now(timezone.utc)
                
            transaction.update(doc_ref, updates)
            return all_ready

        all_ready = await asyncio.to_thread(_update_ready_transaction, db.transaction(), game_ref)
        
        # Broadcast readiness
        await manager.broadcast(game_id, {
            "type": "PLAYER_READY",
            "player": {"user_id": user_id}
        })
        
        if all_ready:
            # Initialize live game state in Redis
            db = _get_firestore_client()
            doc = await asyncio.to_thread(db.collection("games").document(game_id).get)
            live_state = await init_game_state(game_id, doc.to_dict())
            
            await manager.broadcast(game_id, {
                "type": "GAME_STARTED",
                "game_id": game_id,
                "phase": live_state["phase"],
                "current_turn": live_state["current_turn"],
                "scores": live_state["scores"]
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
