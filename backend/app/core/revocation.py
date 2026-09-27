"""Immediate access-token revocation (audit A-24c).

Access tokens are stateless JWTs that live ``ACCESS_TOKEN_EXPIRE_MINUTES``.
To cut a session off *now* (role change, deactivation, password change or
reset, "sign out everywhere") the user's ``token_epoch`` is bumped in the
database — every new token carries it as the ``ep`` claim — and the new epoch
is written to Redis under ``vs:revoked_user:{user_id}`` with a TTL equal to the
access-token lifetime. ``get_current_user`` rejects any token whose ``ep`` is
older than the stored epoch, without touching the database.

Redis unavailable → the write/read is skipped and logged. Old tokens then live
out their normal expiry (≤ 15 min); the refresh token is already revoked in
the database, so no new access token can be minted.
"""

from __future__ import annotations

import uuid

import structlog

from app.core.config import settings
from app.core.redis import get_redis

log = structlog.get_logger("app.revocation")

_KEY = "vs:revoked_user:{}"


def _ttl() -> int:
    # A little longer than the access-token lifetime so clock skew cannot let
    # a token outlive the denylist entry.
    return settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60 + 60


async def mark_user_revoked(user_id: uuid.UUID | str, epoch: int) -> None:
    """Deny every access token issued with ``ep < epoch`` for one token lifetime."""
    try:
        await get_redis().set(_KEY.format(user_id), str(int(epoch)), ex=_ttl())
    except Exception as exc:  # noqa: BLE001 - degrade, never block the request
        log.warning("revocation_denylist_unavailable", error=str(exc), user_id=str(user_id))


async def revoked_epoch(user_id: uuid.UUID | str) -> int | None:
    """The epoch a token must reach to be accepted, or ``None`` if unknown/unreachable."""
    try:
        value = await get_redis().get(_KEY.format(user_id))
    except Exception as exc:  # noqa: BLE001 - fall through (documented)
        log.warning("revocation_denylist_unavailable", error=str(exc))
        return None
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
