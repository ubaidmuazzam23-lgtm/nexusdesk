# Location: ./backend/app/websockets/team_chat_ws.py

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.security import decode_token
from app.models.user import User
from app.models.team import Team, TeamMember, TeamMessage
from app.websockets.connection_manager import manager
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)

_MAX_WS_MSG_LEN = 4_000


def _get_user_from_token(token: str, db: Session):
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.query(User).filter(
        User.id == user_id,
        User.is_active == True
    ).first()


def _is_allowed(user: User, team: Team, db: Session) -> bool:
    role = user.role.lower() if isinstance(user.role, str) else user.role.value.lower()
    if role == "admin":
        return True
    if team.manager_id and str(team.manager_id) == str(user.id):
        return True
    member = db.query(TeamMember).filter(
        TeamMember.team_id == team.id,
        TeamMember.user_id == user.id,
    ).first()
    return member is not None


def _get_role_str(user: User) -> str:
    if isinstance(user.role, str):
        return user.role.lower()
    return user.role.value.lower()


@router.websocket("/api/v1/teams/{team_id}/ws")
async def team_chat_websocket(websocket: WebSocket, team_id: str):
    """
    Authentication: client must send {"type":"auth","token":"<access_token>"}
    as the first message after the connection is established.
    Token is NOT accepted as a URL query parameter.
    """
    await websocket.accept()
    db = SessionLocal()
    try:
        # Wait for auth message — first frame only
        try:
            raw_auth = await websocket.receive_text()
            auth_data = json.loads(raw_auth)
            token = auth_data.get("token", "")
        except Exception:
            await websocket.close(code=4001)
            return

        user = _get_user_from_token(token, db)
        if not user:
            await websocket.send_text(json.dumps({"type": "error", "message": "Unauthorized"}))
            await websocket.close(code=4001)
            return

        team = db.query(Team).filter(Team.team_id == team_id).first()
        if not team:
            await websocket.close(code=4004)
            return

        if not _is_allowed(user, team, db):
            await websocket.send_text(json.dumps({"type": "error", "message": "Forbidden"}))
            await websocket.close(code=4003)
            return

        await manager.connect(websocket, team_id)

        await manager.broadcast_to_team(team_id, {
            "type":         "system",
            "message":      f"{user.full_name} joined the chat",
            "sender_name":  "System",
            "sender_id":    str(user.id),
            "timestamp":    datetime.utcnow().isoformat(),
            "online_count": manager.get_online_count(team_id),
        })

        try:
            while True:
                data = await websocket.receive_text()
                if not data.strip():
                    continue
                if len(data) > _MAX_WS_MSG_LEN:
                    await websocket.send_text(json.dumps({
                        "type":    "error",
                        "message": f"Message too long (max {_MAX_WS_MSG_LEN} chars).",
                    }))
                    continue

                msg = TeamMessage(
                    team_id=team.id,
                    sender_id=user.id,
                    message=data.strip()[:_MAX_WS_MSG_LEN],
                )
                db.add(msg)
                db.commit()
                db.refresh(msg)

                await manager.broadcast_to_team(team_id, {
                    "type":         "message",
                    "id":           str(msg.id),
                    "message":      msg.message,
                    "sender_id":    str(user.id),
                    "sender_name":  user.full_name,
                    "sender_role":  _get_role_str(user),
                    "timestamp":    msg.created_at.isoformat(),
                    "online_count": manager.get_online_count(team_id),
                })

        except WebSocketDisconnect:
            manager.disconnect(websocket, team_id)
            await manager.broadcast_to_team(team_id, {
                "type":         "system",
                "message":      f"{user.full_name} left the chat",
                "sender_name":  "System",
                "sender_id":    str(user.id),
                "timestamp":    datetime.utcnow().isoformat(),
                "online_count": manager.get_online_count(team_id),
            })
    finally:
        db.close()