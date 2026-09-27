"""WebSocket endpoint for real-time messaging (delivery, presence, typing).

Messages are still *sent* over REST (validated, persisted); this socket only
*delivers* them live, plus presence and typing signals. Authenticated via the
JWT access token passed as a ``?token=`` query parameter (browsers can't set
Authorization headers on a WebSocket handshake).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.database import session_scope
from app.core.security import TokenType, decode_token
from app.modules.messaging.realtime import manager
from app.modules.messaging.repository import ConversationRepository

ws_router = APIRouter()


def _tenant(payload: dict) -> str | None:
    tid = payload.get("tid")
    return str(tid) if tid else None


async def _partner_ids(user_id: uuid.UUID, tenant: str | None) -> list[uuid.UUID]:
    async with session_scope(tenant_id=tenant) as session:
        conversations = await ConversationRepository(session).list_for_user(user_id)
        ids: set[uuid.UUID] = set()
        for conversation in conversations:
            for participant in conversation.participants:
                if participant.user_id != user_id:
                    ids.add(participant.user_id)
        return list(ids)


async def _co_participants(
    conversation_id: uuid.UUID, user_id: uuid.UUID, tenant: str | None
) -> list[uuid.UUID]:
    async with session_scope(tenant_id=tenant) as session:
        conversation = await ConversationRepository(session).get(conversation_id)
        if conversation is None:
            return []
        members = {p.user_id for p in conversation.participants}
        if user_id not in members:
            return []
        return [uid for uid in members if uid != user_id]


@ws_router.websocket("/ws")
async def messaging_ws(websocket: WebSocket, token: str = Query(...)) -> None:
    try:
        payload = decode_token(token, expected_type=TokenType.ACCESS)
    except Exception:
        await websocket.close(code=4401)
        return

    user_id = uuid.UUID(payload["sub"])
    tenant = _tenant(payload)
    await websocket.accept()
    became_online = manager.add(user_id, websocket)
    partner_ids = await _partner_ids(user_id, tenant)

    if became_online:
        await manager.send_to_users(
            partner_ids, {"type": "presence", "user_id": str(user_id), "online": True}
        )
    # Seed the just-connected client with who of its partners is already online.
    await websocket.send_json(
        {"type": "presence_snapshot", "online": [str(u) for u in manager.online_among(partner_ids)]}
    )

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "typing" and data.get("conversation_id"):
                try:
                    conversation_id = uuid.UUID(str(data["conversation_id"]))
                except ValueError:
                    continue
                recipients = await _co_participants(conversation_id, user_id, tenant)
                await manager.send_to_users(
                    recipients,
                    {
                        "type": "typing",
                        "conversation_id": str(conversation_id),
                        "user_id": str(user_id),
                    },
                )
    except WebSocketDisconnect:
        pass
    finally:
        if manager.remove(user_id, websocket):
            await manager.send_to_users(
                partner_ids, {"type": "presence", "user_id": str(user_id), "online": False}
            )
