import asyncio
from typing import Dict, List
from fastapi import WebSocket

class GameConnectionManager:
    def __init__(self):
        # Maps game_id to a dictionary of user_id -> WebSocket
        self.active_games: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, game_id: str, user_id: str):
        await websocket.accept()
        if game_id not in self.active_games:
            self.active_games[game_id] = {}
        self.active_games[game_id][user_id] = websocket

    def disconnect(self, game_id: str, user_id: str):
        if game_id in self.active_games and user_id in self.active_games[game_id]:
            del self.active_games[game_id][user_id]
            if not self.active_games[game_id]:
                del self.active_games[game_id]

    async def broadcast(self, game_id: str, message: dict):
        if game_id in self.active_games:
            for connection in self.active_games[game_id].values():
                try:
                    await connection.send_json(message)
                except Exception as e:
                    print(f"[GameConnectionManager] Broadcast error: {e}")

manager = GameConnectionManager()
