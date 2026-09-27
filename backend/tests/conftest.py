"""Pytest fixtures: an isolated in-memory database + seeded RBAC + HTTP client.

Tests run against SQLite (aiosqlite) so they need no external services. RLS is a
PostgreSQL feature and is exercised in integration tests against a real
Postgres; here we verify application-level tenant scoping and the full auth
flow. The app's session dependencies are overridden to use the test engine.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# ── Test environment (must precede any `app.*` import: Settings is built on import) ──
# SECRET_KEY has no default any more (audit A-7); the rest keeps the suite
# hermetic: limiters off (their behaviour is unit-tested with them on), the
# mock IdP opted in, and the OAuth redirect origin the SSO tests use allowed.
os.environ.setdefault("VS_SECRET_KEY", "test-only-secret-key-not-for-production-0123456789")
os.environ.setdefault("VS_RATE_LIMITING_ENABLED", "false")
os.environ.setdefault("VS_OAUTH_MOCK_ENABLED", "true")
os.environ.setdefault("VS_OAUTH_ALLOWED_REDIRECT_ORIGINS", "https://app.test")
# Invites return the temporary password in tests (production default: off);
# test_auth_hardening covers the default and the invitation-link flow.
os.environ.setdefault("VS_INVITES_RETURN_TEMP_PASSWORD", "true")
os.environ.setdefault("VS_ENVIRONMENT", "local")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.core.deps as deps  # noqa: E402
import app.core.redis as redis_module  # noqa: E402
from app.core.deps import get_auth_session, get_tenant_session  # noqa: E402
from tests.fake_redis import FakeRedis  # noqa: E402
from app.core.link_preview import set_dns_resolver
from app.core.storage import MemoryStorage, get_storage
from app.core.webauthn import MockVerifier, set_webauthn_verifier
from app.core.webhook_transport import RecordingTransport, set_webhook_transport
from app.modules.webhooks.service import dispatcher as webhook_dispatcher
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


# Deterministic DNS for the outbound-URL (SSRF) guard: named hosts resolve to the
# address class their name says; anything else is a public address.
FAKE_DNS: dict[str, list[str]] = {
    "private.test": ["10.0.0.5"],
    "loopback.test": ["127.0.0.1"],
    "linklocal.test": ["169.254.1.1"],
    "metadata.test": ["169.254.169.254"],
    "v6loopback.test": ["::1"],
    "mixed.test": ["93.184.216.34", "10.1.1.1"],  # one bad address poisons the set
    "unresolvable.test": [],
}
PUBLIC_IP = "93.184.216.34"


async def fake_resolve(host: str) -> list[str]:
    return FAKE_DNS.get(host, [PUBLIC_IP])


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
    # Outbound URL guard resolves names without DNS.
    set_dns_resolver(fake_resolve)

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
    # Webhook deliveries are parked until a test calls ``webhook_dispatcher.drain()``
    # (never concurrent with a request on the shared SQLite connection).
    webhook_dispatcher.configure(session_opener=lambda _tid: _test_bypass(), auto=False, backoff_base=0)

    # Passkey ceremonies use a deterministic in-process verifier (no real crypto).
    set_webauthn_verifier(MockVerifier())
    # Redis (revocation denylist, WebSocket tickets, rate limiter) is an
    # in-memory fake, fresh per test.
    fake_redis = FakeRedis()
    original_redis = redis_module._client
    redis_module._client = fake_redis
    app.state.fake_redis = fake_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    redis_module._client = original_redis
    app.dependency_overrides.clear()
    set_webhook_transport(None)
    set_dns_resolver(None)
    webhook_dispatcher.reset()
    set_webauthn_verifier(None)
    deps.bypass_session_scope = original_bypass


@pytest.fixture
def strong_password() -> str:
    return "Str0ng!Pass#2026"


async def _count_roles(session_factory: async_sessionmaker) -> int:
    async with session_factory() as s:
        result = await s.execute(select(Role))
        return len(list(result.scalars().all()))
