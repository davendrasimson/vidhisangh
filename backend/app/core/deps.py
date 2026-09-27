"""FastAPI dependency-injection helpers.

Exposes:
- ``AuthSessionDep`` — RLS-bypassing session for the auth endpoints only.
- ``CurrentUserDep`` — the authenticated principal decoded from the JWT
  (stateless, no DB round-trip).
- ``TenantSessionDep`` — a DB session automatically scoped to the caller's
  tenant via row-level security.
- ``CurrentUserModelDep`` — the full ``User`` ORM aggregate when needed.
- ``require_permission("code")`` — RBAC guard factory for route protection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import session_scope
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import TokenType, decode_token
from app.modules.identity.schemas import CurrentUser

_bearer = HTTPBearer(auto_error=False, description="JWT access token")


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
async def get_current_user(
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
        payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired.") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid access token.") from exc

    return CurrentUser(
        id=payload["sub"],
        tenant_id=payload.get("tid"),
        email=payload.get("email", ""),
        is_superuser=bool(payload.get("superuser", False)),
        scopes=payload.get("scopes", []),
        session_id=payload.get("rtid"),
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def get_tenant_session(current: CurrentUserDep) -> AsyncIterator[AsyncSession]:
    """DB session scoped to the caller's tenant via RLS."""
    tenant_id = str(current.tenant_id) if current.tenant_id else None
    async with session_scope(tenant_id=tenant_id) as session:
        yield session


TenantSessionDep = Annotated[AsyncSession, Depends(get_tenant_session)]
AuthSessionDep = Annotated[AsyncSession, Depends(get_auth_session)]


async def get_current_user_model(current: CurrentUserDep, session: TenantSessionDep):  # noqa: ANN201
    """Load the full ``User`` ORM aggregate for the authenticated principal."""
    from app.modules.identity.repository import UserRepository

    user = await UserRepository(session).get_by_id(current.id)
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


def client_ip(request: Request) -> str | None:
    """Best-effort client IP honouring a trusted reverse proxy header."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None
