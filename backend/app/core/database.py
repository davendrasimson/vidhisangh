"""Async database engine, session factory, and RLS tenant context.

Multi-tenancy uses a **shared database with PostgreSQL Row-Level Security**.
Every tenant-scoped table carries a ``tenant_id`` and an RLS policy that only
exposes rows matching the ``app.current_tenant`` session variable. This module
provides a session that sets that variable per request, so isolation is
enforced by the database itself — not just by application code.
"""

from __future__ import annotations

import os
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}
# Settings the config module may not declare yet — read with a fallback so
# the engine builds before they are added (VS_DB_SSL_MODE, VS_DB_STATEMENT_TIMEOUT_MS).
_DEFAULT_STATEMENT_TIMEOUT_MS = 30_000
_DEFAULT_IDLE_IN_TXN_TIMEOUT_MS = 60_000


def _setting(name: str, default: Any) -> Any:
    value = getattr(settings, name, None)
    if value is None:
        value = os.environ.get(f"VS_{name}")
    return default if value in (None, "") else value


def _dsn_host(dsn: str) -> str:
    try:
        return (urlsplit(dsn).hostname or "").lower()
    except ValueError:
        return ""


def db_ssl_mode() -> str:
    """Effective TLS mode for the database connection.

    ``VS_DB_SSL_MODE`` wins when set (``disable`` | ``require`` | ``verify-ca`` |
    ``verify-full``). Otherwise loopback hosts (same-host Postgres over a unix
    socket or 127.0.0.1) default to ``disable`` and every other host — a pod
    network, a managed database — defaults to ``require`` so credentials and
    client data never cross a network in the clear.
    """
    explicit = str(_setting("DB_SSL_MODE", "") or "").lower()
    if explicit:
        return explicit
    host = _dsn_host(settings.async_database_url)
    return "disable" if (not host or host in _LOOPBACK_HOSTS) else "require"


def _ssl_context(mode: str) -> ssl.SSLContext | bool | None:
    """asyncpg ``ssl`` connect argument for the given mode."""
    if mode == "disable":
        return None
    if mode == "require":
        # Encrypt, but do not verify the chain (self-signed managed DBs, MinIO-
        # style internal CAs). Matches libpq's sslmode=require.
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    if mode in ("verify-ca", "verify-full"):
        ca = _setting("DB_SSL_ROOT_CERT", None)
        ctx = ssl.create_default_context(cafile=str(ca) if ca else None)
        ctx.check_hostname = mode == "verify-full"
        ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx
    raise RuntimeError(
        f"Unknown VS_DB_SSL_MODE={mode!r}; expected disable, require, verify-ca or verify-full."
    )


def statement_timeout_ms() -> int:
    return int(_setting("DB_STATEMENT_TIMEOUT_MS", _DEFAULT_STATEMENT_TIMEOUT_MS))


def _connect_args() -> dict[str, Any]:
    url = settings.async_database_url
    args: dict[str, Any] = {}
    if url.startswith("postgresql"):
        ssl_arg = _ssl_context(db_ssl_mode())
        if ssl_arg is not None:
            args["ssl"] = ssl_arg
        # asyncpg: fail a stalled TCP connect instead of hanging a worker.
        args["timeout"] = 10
    return args


def _install_session_defaults(engine: AsyncEngine) -> None:
    """Apply per-connection Postgres timeouts as soon as a connection is made.

    ``statement_timeout`` bounds any single query so a runaway search or a lock
    wait fails as a catchable error instead of holding a gunicorn worker until
    it is SIGKILLed; ``idle_in_transaction_session_timeout`` releases sessions
    a crashed client left open mid-transaction (they otherwise pin locks and
    block VACUUM). Both are plain ``SET`` (session scope), so they survive for
    the life of the pooled connection and are re-applied on reconnect. Code
    that needs longer (research facets) still uses ``SET LOCAL`` per transaction.
    """
    if engine.dialect.name != "postgresql":
        return
    timeout_ms = statement_timeout_ms()
    idle_ms = int(_setting("DB_IDLE_IN_TRANSACTION_TIMEOUT_MS", _DEFAULT_IDLE_IN_TXN_TIMEOUT_MS))

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:  # pragma: no cover - needs PG
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"SET statement_timeout = {int(timeout_ms)}")
            cursor.execute(f"SET idle_in_transaction_session_timeout = {int(idle_ms)}")
        finally:
            cursor.close()


@lru_cache
def get_engine() -> AsyncEngine:
    """Lazily create the async engine.

    Constructed on first use (not at import) so importing this module does not
    require the database driver — tests that override the session dependencies
    with an in-memory engine never instantiate the production engine.

    Pool hygiene: ``pool_recycle`` retires connections after 30 minutes so a
    server-side restart, a rotated certificate or an idle-killing firewall
    never leaves a dead socket in the pool; ``pool_timeout`` bounds how long a
    request waits for a free connection before failing (instead of queueing
    forever under load); ``pool_pre_ping`` validates before use.
    """
    engine = create_async_engine(
        settings.async_database_url,
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_timeout=30,
        connect_args=_connect_args(),
        echo=settings.DEBUG and settings.LOG_LEVEL == "DEBUG",
        future=True,
    )
    _install_session_defaults(engine)
    return engine


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def apply_rls_context(
    session: AsyncSession, tenant_id: str | None, *, bypass: bool = False
) -> None:
    """Bind the RLS session variables that policies read.

    ``app.current_tenant`` scopes visibility to a single tenant. ``app.bypass_rls``
    is an escape hatch used **only** by the authentication service, which must
    query across tenants before a tenant context is established (e.g. login by
    email). Both use ``set_config(..., is_local => true)`` so they are scoped to
    the current transaction and never leak across pooled connections.
    """
    # RLS session variables are a PostgreSQL feature; no-op on other backends
    # (e.g. SQLite used in unit tests) so the same code path runs everywhere.
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return
    await session.execute(
        text("SELECT set_config('app.current_tenant', :tid, true)"),
        {"tid": tenant_id or ""},
    )
    await session.execute(
        text("SELECT set_config('app.bypass_rls', :b, true)"),
        {"b": "on" if bypass else "off"},
    )


@asynccontextmanager
async def session_scope(
    tenant_id: str | None = None, *, bypass_rls: bool = False
) -> AsyncIterator[AsyncSession]:
    """Transactional session with the tenant RLS context applied.

    Commits on success, rolls back on exception, always closes.
    """
    async with get_session_factory()() as session:
        await apply_rls_context(session, tenant_id, bypass=bypass_rls)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db(tenant_id: str | None = None) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a tenant-scoped session (see app.core.deps)."""
    async with session_scope(tenant_id) as session:
        yield session


async def ping_database() -> bool:
    """Lightweight connectivity check for health probes."""
    async with get_session_factory()() as session:
        await session.execute(text("SELECT 1"))
    return True


async def dispose_engine() -> None:
    await get_engine().dispose()
