"""Pytest fixtures: an isolated in-memory database + seeded RBAC + HTTP client.

Tests run against SQLite (aiosqlite) so they need no external services. RLS is a
PostgreSQL feature and is exercised in integration tests against a real
Postgres; here we verify application-level tenant scoping and the full auth
flow. The app's session dependencies are overridden to use the test engine.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.core.deps as deps
from app.core.deps import get_auth_session, get_tenant_session
from app.core.storage import MemoryStorage, get_storage
from app.core.webauthn import MockVerifier, set_webauthn_verifier
from app.core.webhook_transport import RecordingTransport, set_webhook_transport
from app.db.base import Base
from app.main import app
from app.modules.identity.models import Permission, Role
from app.modules.identity.rbac import (
    ALL_PERMISSION_CODES,
    PERMISSIONS,
    SYSTEM_ROLES,
    WILDCARD,
)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[object]:
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: object) -> async_sessionmaker:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    # Seed the RBAC catalog once per test database.
    async with factory() as s:
        perms = {
            p.code: Permission(code=p.code, name=p.name, module=p.module, description=p.description)
            for p in PERMISSIONS
        }
        s.add_all(perms.values())
        await s.flush()
        for rdef in SYSTEM_ROLES:
            codes = ALL_PERMISSION_CODES if rdef.permissions == [WILDCARD] else rdef.permissions
            s.add(
                Role(
                    code=rdef.code,
                    name=rdef.name,
                    description=rdef.description,
                    is_system=True,
                    tenant_id=None,
                    permissions=[perms[c] for c in codes if c in perms],
                )
            )
        await s.commit()
    return factory


@pytest.fixture
def webhook_transport() -> RecordingTransport:
    """The in-process transport wired into the app for the duration of a test,
    so webhook signatures/payloads can be asserted."""
    return RecordingTransport()


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker, webhook_transport: RecordingTransport
) -> AsyncIterator[AsyncClient]:
    async def _override() -> AsyncIterator[object]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # Both auth (bypass) and tenant sessions map to the same test session on SQLite.
    app.dependency_overrides[get_auth_session] = _override
    app.dependency_overrides[get_tenant_session] = _override
    # Documents use a hermetic in-memory store during tests (no filesystem I/O).
    memory_storage = MemoryStorage()
    app.dependency_overrides[get_storage] = lambda: memory_storage
    # Webhook deliveries are recorded in-process (no real outbound HTTP).
    set_webhook_transport(webhook_transport)

    # API-key authentication resolves on a short bypass session; point it at the
    # test SQLite session (opened and closed per lookup, so it never overlaps the
    # endpoint's session).
    @asynccontextmanager
    async def _test_bypass() -> AsyncIterator[object]:
        async with session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    original_bypass = deps.bypass_session_scope
    deps.bypass_session_scope = lambda: _test_bypass()

    # Passkey ceremonies use a deterministic in-process verifier (no real crypto).
    set_webauthn_verifier(MockVerifier())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    set_webhook_transport(None)
    set_webauthn_verifier(None)
    deps.bypass_session_scope = original_bypass


@pytest.fixture
def strong_password() -> str:
    return "Str0ng!Pass#2026"


async def _count_roles(session_factory: async_sessionmaker) -> int:
    async with session_factory() as s:
        result = await s.execute(select(Role))
        return len(list(result.scalars().all()))
