"""PostgreSQL Row-Level-Security integration test (real DB).

The main suite runs on SQLite and can only verify *application-level* tenant
scoping. This test connects to a real Postgres and proves the RLS policies from
migration ``0001`` actually enforce tenant isolation at the database level.

Because the app connects as a superuser in local dev (and superusers bypass RLS),
enforcement is verified under a **temporary non-superuser role**. Everything runs
inside a single transaction that is always rolled back — no data is committed
(``CREATE ROLE`` is transactional in Postgres). The whole module is skipped when
Postgres is unreachable, so the SQLite-only CI path is unaffected.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

pytestmark = pytest.mark.asyncio

_PROBE_ROLE = "vs_rls_probe"


async def _engine():
    engine = create_async_engine(settings.async_database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - env dependent
        await engine.dispose()
        pytest.skip(f"Postgres not reachable for RLS integration test: {exc!r}")
    return engine


async def test_rls_enforces_tenant_isolation() -> None:
    engine = await _engine()
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                # Seed two tenants + a user each, bypassing RLS (as superuser).
                await conn.execute(text("SELECT set_config('app.bypass_rls','on',true)"))
                for tid, slug in ((t1, f"rls-a-{t1.hex[:8]}"), (t2, f"rls-b-{t2.hex[:8]}")):
                    await conn.execute(
                        text("INSERT INTO tenants (id, name, slug) VALUES (:id, :n, :s)"),
                        {"id": tid, "n": "RLS Test", "s": slug},
                    )
                for uid, tid in ((u1, t1), (u2, t2)):
                    await conn.execute(
                        text(
                            "INSERT INTO users (id, tenant_id, email, full_name) "
                            "VALUES (:id, :t, :e, :f)"
                        ),
                        {"id": uid, "t": tid, "e": f"{uid.hex}@rls.test", "f": "RLS User"},
                    )

                # Enforce RLS by switching to a throwaway non-superuser role.
                await conn.execute(text(f"DROP ROLE IF EXISTS {_PROBE_ROLE}"))
                await conn.execute(text(f"CREATE ROLE {_PROBE_ROLE} NOSUPERUSER NOLOGIN"))
                await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {_PROBE_ROLE}"))
                await conn.execute(text(f"GRANT SELECT ON users TO {_PROBE_ROLE}"))
                await conn.execute(text(f"SET ROLE {_PROBE_ROLE}"))
                await conn.execute(text("SELECT set_config('app.bypass_rls','off',true)"))

                async def visible(tenant: uuid.UUID) -> set[uuid.UUID]:
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"),
                        {"t": str(tenant)},
                    )
                    rows = await conn.execute(
                        text("SELECT id FROM users WHERE id IN (:a, :b)"),
                        {"a": u1, "b": u2},
                    )
                    return {r[0] for r in rows}

                # Under tenant T1's context, only T1's user is visible.
                assert await visible(t1) == {u1}
                # Under tenant T2's context, only T2's user is visible.
                assert await visible(t2) == {u2}

                # Re-enabling bypass exposes both rows again.
                await conn.execute(text("SELECT set_config('app.bypass_rls','on',true)"))
                both = await conn.execute(
                    text("SELECT id FROM users WHERE id IN (:a, :b)"), {"a": u1, "b": u2}
                )
                assert {r[0] for r in both} == {u1, u2}

                await conn.execute(text("RESET ROLE"))
            finally:
                await trans.rollback()  # discard tenants, users AND the probe role
    finally:
        await engine.dispose()
