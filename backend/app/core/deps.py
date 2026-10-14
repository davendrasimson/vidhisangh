"""FastAPI dependency-injection helpers.

Exposes:
- ``AuthSessionDep`` — RLS-bypassing session for the auth endpoints only.
- ``CurrentUserDep`` — the authenticated principal decoded from the JWT
  (stateless: no DB round-trip; one cheap Redis lookup for the revocation
  denylist, skipped when Redis is down).
- ``TenantSessionDep`` — a DB session automatically scoped to the caller's
  tenant via row-level security.
- ``CurrentUserModelDep`` — the full ``User`` ORM aggregate when needed.
- ``require_permission("code")`` — RBAC guard factory for route protection.
- ``client_ip(request)`` — the real client address behind trusted proxies.
"""

from __future__ import annotations

import ipaddress
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from app.core.config import settings
from app.core.database import session_scope
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.revocation import revoked_epoch
from app.core.security import TokenType, decode_token
from app.modules.identity.schemas import CurrentUser

_bearer = HTTPBearer(auto_error=False, description="JWT access token")

# Routes a ``password_must_change`` session may still reach (path suffixes).
PASSWORD_CHANGE_ONLY_PATHS = ("/auth/change-password", "/auth/logout", "/auth/me")


# ─── Sessions ───────────────────────────────────────────────────────
async def get_auth_session() -> AsyncIterator[AsyncSession]:
    """Session for unauthenticated auth flows (login/register/refresh).

    Runs with ``app.bypass_rls='on'`` because these operations must resolve
    users before a tenant context exists. Used ONLY by the auth router.
    """
    async with session_scope(bypass_rls=True) as session:
        yield session


def bypass_session_scope() -> AbstractAsyncContextManager[AsyncSession]:
    """A bypass-RLS session context manager, opened and closed by the caller.

    Used to resolve an API key BEFORE a tenant context exists. Kept as a small
    indirection so the test suite can substitute a SQLite session; it is opened
    and closed immediately (not held open across the request) so it never
    overlaps the endpoint's own session.
    """
    return session_scope(bypass_rls=True)


# ─── Principal ──────────────────────────────────────────────────────
def principal_from_claims(payload: dict) -> CurrentUser:
    return CurrentUser(
        id=payload["sub"],
        tenant_id=payload.get("tid"),
        email=payload.get("email", ""),
        is_superuser=bool(payload.get("superuser", False)),
        scopes=payload.get("scopes", []),
        session_id=payload.get("rtid"),
        token_epoch=int(payload.get("ep", 0) or 0),
        password_must_change=bool(payload.get("pmc", False)),
    )


async def assert_not_revoked(user_id: str, token_epoch: int) -> None:
    """Reject a token issued before the user's most recent revocation event.

    The denylist is a short-TTL Redis key written on role change, deactivation,
    password change/reset and "revoke all"; its TTL equals the access-token
    lifetime, so no DB read is needed on the hot path. When Redis is
    unavailable the check is skipped (documented in DEPLOYMENT.md) — the token
    still dies at its normal expiry and the refresh token is already revoked
    in the database.
    """
    stored = await revoked_epoch(user_id)
    if stored is not None and token_epoch < stored:
        raise AuthenticationError("This session has been revoked. Please sign in again.")


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication credentials were not provided.")
    token = credentials.credentials
    # Programmatic access: an ``vsk_`` bearer is an API key resolved against the DB
    # on a short bypass-RLS session (opened and closed here). JWT requests skip
    # this entirely — no DB hit on the token hot path.
    if token.startswith("vsk_"):
        from app.modules.apikeys.service import authenticate_api_key

        async with bypass_session_scope() as session:
            return await authenticate_api_key(session, token)
    try:
        payload = decode_token(token, expected_type=TokenType.ACCESS)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired.") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid access token.") from exc

    current = principal_from_claims(payload)
    await assert_not_revoked(str(current.id), current.token_epoch)

    if current.password_must_change and not request.url.path.endswith(
        PASSWORD_CHANGE_ONLY_PATHS
    ):
        raise PermissionDeniedError(
            "You must change your temporary password before using the application "
            "(POST /auth/change-password)."
        )
    return current


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def get_tenant_session(current: CurrentUserDep) -> AsyncIterator[AsyncSession]:
    """DB session scoped to the caller's tenant via RLS."""
    tenant_id = str(current.tenant_id) if current.tenant_id else None
    async with session_scope(tenant_id=tenant_id) as session:
        yield session


# scope="function": commit when the endpoint returns, BEFORE the response is
# sent. With FastAPI's default ("request") the commit ran after the response, so
# a failed commit reached the client as 200/201 and the change was silently lost
# (seen in production: an accepted connection that was never saved).
TenantSessionDep = Annotated[AsyncSession, Depends(get_tenant_session, scope="function")]
AuthSessionDep = Annotated[AsyncSession, Depends(get_auth_session, scope="function")]


async def get_current_user_model(current: CurrentUserDep, session: TenantSessionDep):  # noqa: ANN201
    """Load the full ``User`` ORM aggregate for the authenticated principal."""
    from app.modules.identity.repository import UserRepository

    user = await UserRepository(session).get_for_tenant(current.tenant_id, current.id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is no longer active.")
    return user


# ─── RBAC guard ─────────────────────────────────────────────────────
def require_permission(*codes: str) -> object:
    """Return a dependency that admits the request only if the principal holds
    every listed permission (superuser and wildcard scopes always pass)."""

    async def _guard(current: CurrentUserDep) -> CurrentUser:
        missing = [c for c in codes if not current.has_permission(c)]
        if missing:
            raise PermissionDeniedError(
                f"Missing required permission(s): {', '.join(missing)}"
            )
        return current

    return Depends(_guard)


# ─── Client address ─────────────────────────────────────────────────
def _is_trusted_proxy(addr: str | None) -> bool:
    if not addr:
        return False
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in net for net in settings.trusted_proxies)


def client_ip(conn: HTTPConnection) -> str | None:
    """The client's address, honouring ``X-Forwarded-For`` only from trusted proxies.

    Walks the header right-to-left: every trusted proxy appends the address it
    saw, so the rightmost entry that is *not* itself a trusted proxy is the
    real client. Anything further left was supplied by the client and is
    ignored (audit A-2: the first element used to be trusted blindly).
    Works for HTTP requests and WebSocket handshakes alike.
    """
    peer = conn.client.host if conn.client else None
    if not _is_trusted_proxy(peer):
        return peer
    forwarded = conn.headers.get("x-forwarded-for", "")
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    for hop in reversed(hops):
        if not _is_trusted_proxy(hop):
            return hop
    return peer


# ─── Feature-flag guard (audit A-32) ────────────────────────────────
def require_flag(key: str) -> object:
    """Return a dependency that admits the request only when feature flag
    ``key`` resolves to *on* for the caller's tenant (catalog default merged
    with the tenant's override). Unknown keys fail closed."""

    async def _guard(current: CurrentUserDep, session: TenantSessionDep) -> None:
        from app.core.exceptions import TenantError
        from app.modules.featureflags.service import FeatureFlagService

        if current.tenant_id is None:
            raise TenantError("No tenant is associated with this session.")
        if not await FeatureFlagService(session, current.id, current.tenant_id).is_enabled(key):
            raise PermissionDeniedError(f"The '{key}' feature is not enabled for this organisation.")

    return Depends(_guard)
