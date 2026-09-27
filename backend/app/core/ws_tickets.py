"""Single-use WebSocket handshake tickets (audit A-26).

Browsers cannot set an ``Authorization`` header on a WebSocket handshake, so the
credential ends up in the URL — and URLs are logged. Instead of the long-lived
access token, the client asks ``POST /auth/ws-ticket`` for an opaque ticket
that lives ``WS_TICKET_TTL_SECONDS`` and is consumed on first use (Redis
``GETDEL``). When Redis is down the ticket degrades to a signed JWT of type
``ws`` with the same short lifetime (not single-use, but still not the access
token and dead within a minute).
"""

from __future__ import annotations

import json
import secrets
from datetime import timedelta

import jwt
import structlog

from app.core.config import settings
from app.core.redis import get_redis
from app.core.security import TokenType, create_access_token, decode_token
from app.modules.identity.schemas import CurrentUser

log = structlog.get_logger("app.ws_tickets")

_KEY = "vs:ws_ticket:{}"


def _payload(current: CurrentUser) -> dict:
    return {
        "sub": str(current.id),
        "tid": str(current.tenant_id) if current.tenant_id else None,
        "ep": current.token_epoch,
    }


async def issue_ws_ticket(current: CurrentUser) -> tuple[str, int]:
    """Return ``(ticket, ttl_seconds)``. Opaque + Redis-backed, JWT fallback."""
    ttl = settings.WS_TICKET_TTL_SECONDS
    ticket = secrets.token_urlsafe(32)
    try:
        await get_redis().set(_KEY.format(ticket), json.dumps(_payload(current)), ex=ttl)
        return ticket, ttl
    except Exception as exc:  # noqa: BLE001 - degrade to a signed short token
        log.warning("ws_ticket_store_unavailable", error=str(exc))
        token = create_access_token(
            subject=str(current.id),
            tenant_id=str(current.tenant_id) if current.tenant_id else None,
            scopes=[],
            extra={"ep": current.token_epoch},
            expires_delta=timedelta(seconds=ttl),
            token_type=TokenType.WS,
        )
        return token, ttl


async def redeem_ws_ticket(ticket: str) -> dict | None:
    """Consume a ticket; returns its claims (``sub``, ``tid``, ``ep``) or ``None``."""
    if ticket.count(".") == 2:  # JWT fallback
        try:
            return decode_token(ticket, expected_type=TokenType.WS)
        except jwt.PyJWTError:
            return None
    try:
        redis = get_redis()
        key = _KEY.format(ticket)
        raw = await redis.getdel(key) if hasattr(redis, "getdel") else None
        if raw is None and not hasattr(redis, "getdel"):  # pragma: no cover - old redis
            raw = await redis.get(key)
            if raw is not None:
                await redis.delete(key)
    except Exception as exc:  # noqa: BLE001
        log.warning("ws_ticket_store_unavailable", error=str(exc))
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None
