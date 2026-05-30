# Location: ./backend/app/websockets/connection_manager.py

from fastapi import WebSocket
from typing import Dict, List
import json


class ConnectionManager:
    def __init__(self):
        # team_id -> list of connected websockets
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, team_id: str):
        await websocket.accept()
        if team_id not in self.active_connections:
            self.active_connections[team_id] = []
        self.active_connections[team_id].append(websocket)

    def disconnect(self, websocket: WebSocket, team_id: str):
        if team_id in self.active_connections:
            if websocket in self.active_connections[team_id]:
                self.active_connections[team_id].remove(websocket)
            if not self.active_connections[team_id]:
                del self.active_connections[team_id]

    async def broadcast_to_team(self, team_id: str, message: dict):
        if team_id not in self.active_connections:
            return
        dead = []
        for ws in self.active_connections[team_id]:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, team_id)

    def get_online_count(self, team_id: str) -> int:
        return len(self.active_connections.get(team_id, []))


manager = ConnectionManager()