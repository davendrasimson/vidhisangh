"""WebSocket endpoint for real-time messaging (delivery, presence, typing).

Messages are still *sent* over REST (validated, persisted); this socket only
*delivers* them live, plus presence and typing signals.

Authentication (audit A-26): the client first calls ``POST /auth/ws-ticket``
and connects with ``?ticket=`` — a 60-second, single-use opaque ticket, so the
long-lived access token never appears in a URL or an access log. ``?token=``
(the access token itself) is still accepted for one release with a deprecation
warning. Before accepting, the handshake is throttled per IP and the user is
checked to be active and not on the revocation denylist.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core import deps
from app.core.database import session_scope
from app.core.deps import client_ip
from app.core.exceptions import RateLimitError
from app.core.ratelimit import ws_handshake_rate_limit
from app.core.revocation import revoked_epoch
from app.core.security import TokenType, decode_token
from app.core.ws_tickets import redeem_ws_ticket
from app.modules.identity.repository import UserRepository
from app.modules.messaging.realtime import manager
from app.modules.messaging.repository import ConversationRepository

log = structlog.get_logger("app.ws")

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


async def _user_may_connect(user_id: uuid.UUID, tenant: str | None, token_epoch: int) -> bool:
    """Active account, and not revoked since the ticket/token was minted."""
    stored = await revoked_epoch(user_id)
    if stored is not None and token_epoch < stored:
        return False
    # Short pre-tenant lookup (same seam API-key auth uses; the test suite
    # points it at SQLite). The tenant claim must match the account's tenant.
    async with deps.bypass_session_scope() as session:
        user = await UserRepository(session).get_by_id_global(user_id)
        if user is None or not user.is_active:
            return False
        return tenant is None or str(user.tenant_id) == tenant


async def authenticate_handshake(
    websocket: WebSocket, *, ticket: str | None, token: str | None
) -> dict | None:
    """Resolve the handshake credential to claims, or ``None`` when rejected."""
    payload: dict | None = None
    if ticket:
        payload = await redeem_ws_ticket(ticket)
    elif token:
        log.warning(
            "ws_token_query_deprecated",
            detail="?token= on the WebSocket URL is deprecated; use POST /auth/ws-ticket and ?ticket=",
        )
        try:
            payload = decode_token(token, expected_type=TokenType.ACCESS)
        except Exception:  # noqa: BLE001
            payload = None
    if not payload or not payload.get("sub"):
        return None
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except ValueError:
        return None
    if not await _user_may_connect(user_id, _tenant(payload), int(payload.get("ep", 0) or 0)):
        return None
    return payload


@ws_router.websocket("/ws")
async def messaging_ws(
    websocket: WebSocket,
    ticket: str | None = Query(default=None),
    token: str | None = Query(default=None),
) -> None:
    try:
        await ws_handshake_rate_limit.check(client_ip(websocket))
    except RateLimitError:
        await websocket.close(code=4429)
        return
    except Exception:  # noqa: BLE001 - limiter outage never blocks a socket (fail-open scope)
        pass

    payload = await authenticate_handshake(websocket, ticket=ticket, token=token)
    if payload is None:
        await websocket.close(code=4401)
        return

    user_id = uuid.UUID(str(payload["sub"]))
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
