"""Async database engine, session factory, and RLS tenant context.

Multi-tenancy uses a **shared database with PostgreSQL Row-Level Security**.
Every tenant-scoped table carries a ``tenant_id`` and an RLS policy that only
exposes rows matching the ``app.current_tenant`` session variable. This module
provides a session that sets that variable per request, so isolation is
enforced by the database itself — not just by application code.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


@lru_cache
def get_engine() -> AsyncEngine:
    """Lazily create the async engine.

    Constructed on first use (not at import) so importing this module does not
    require the database driver — tests that override the session dependencies
    with an in-memory engine never instantiate the production engine.
    """
    return create_async_engine(
        settings.async_database_url,
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
        pool_pre_ping=True,
        echo=settings.DEBUG and settings.LOG_LEVEL == "DEBUG",
        future=True,
    )


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
