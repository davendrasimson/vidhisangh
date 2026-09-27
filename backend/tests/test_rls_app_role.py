"""Least-privilege application-role RLS test (real Postgres).

``test_rls_postgres`` proves the policies *can* isolate tenants under a minimal
probe role. This test goes one step further and proves the **actual application
role** — provisioned with the exact grants from
``app.scripts.provision_db_role`` — both:

* has tenant isolation **enforced by the database** (it is NOSUPERUSER +
  NOBYPASSRLS, so Postgres does not skip RLS the way it does for the ``postgres``
  superuser used in local dev), and
* can still perform normal DML **within** its tenant context, while being blocked
  from cross-tenant reads/writes and from any DDL.

Mechanics mirror ``test_rls_postgres``: a throwaway role entered via ``SET ROLE``
inside a single always-rolled-back transaction (``CREATE ROLE`` and ``GRANT`` are
transactional), so nothing is committed. Skipped when Postgres is unreachable, so
the SQLite-only CI path is unaffected.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.scripts.provision_db_role import grant_statements

pytestmark = pytest.mark.asyncio

# NOLOGIN throwaway that receives the real app-role grants and is entered via
# SET ROLE. NOLOGIN because we never open a second connection — the whole test
# runs on one connection inside one rolled-back transaction.
_APP_ROLE = "vs_app_probe"


async def _engine():
    engine = create_async_engine(settings.async_database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - env dependent
        await engine.dispose()
        pytest.skip(f"Postgres not reachable for app-role RLS test: {exc!r}")
    return engine


async def test_app_role_enforces_rls_and_allows_tenant_dml() -> None:
    engine = await _engine()
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                # ── Seed two tenants + a user each (as superuser, bypassing RLS).
                await conn.execute(text("SELECT set_config('app.bypass_rls','on',true)"))
                for tid, slug in ((t1, f"app-a-{t1.hex[:8]}"), (t2, f"app-b-{t2.hex[:8]}")):
                    await conn.execute(
                        text("INSERT INTO tenants (id, name, slug) VALUES (:id, :n, :s)"),
                        {"id": tid, "n": "App RLS", "s": slug},
                    )
                for uid, tid in ((u1, t1), (u2, t2)):
                    await conn.execute(
                        text(
                            "INSERT INTO users (id, tenant_id, email, full_name) "
                            "VALUES (:id, :t, :e, :f)"
                        ),
                        {"id": uid, "t": tid, "e": f"{uid.hex}@app.test", "f": "App User"},
                    )

                # ── Provision the application role with the PRODUCTION grants.
                await conn.execute(text(f"DROP ROLE IF EXISTS {_APP_ROLE}"))
                await conn.execute(
                    text(
                        f"CREATE ROLE {_APP_ROLE} "
                        "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOLOGIN"
                    )
                )
                for stmt in grant_statements(_APP_ROLE, settings.POSTGRES_DB):
                    await conn.execute(text(stmt))

                # Enter the least-privilege role and drop the bypass.
                await conn.execute(text(f"SET ROLE {_APP_ROLE}"))
                await conn.execute(text("SELECT set_config('app.bypass_rls','off',true)"))

                # The role must genuinely lack the RLS-skipping attributes.
                attrs = (
                    await conn.execute(
                        text(
                            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :r"
                        ),
                        {"r": _APP_ROLE},
                    )
                ).one()
                assert attrs == (False, False)

                async def set_tenant(tenant: uuid.UUID | str) -> None:
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"),
                        {"t": str(tenant)},
                    )

                async def visible() -> set[uuid.UUID]:
                    rows = await conn.execute(
                        text("SELECT id FROM users WHERE id IN (:a, :b)"),
                        {"a": u1, "b": u2},
                    )
                    return {r[0] for r in rows}

                # ── Read isolation: each tenant sees only its own row.
                await set_tenant(t1)
                assert await visible() == {u1}
                await set_tenant(t2)
                assert await visible() == {u2}

                # ── Default-deny: with no tenant context, nothing is visible.
                await set_tenant("")
                assert await visible() == set()

                # ── DML works inside the tenant; RLS silently scopes it.
                await set_tenant(t1)
                res = await conn.execute(
                    text("UPDATE users SET full_name = 'Renamed' WHERE id = :i"), {"i": u1}
                )
                assert res.rowcount == 1  # own row updated
                res = await conn.execute(
                    text("UPDATE users SET full_name = 'Nope' WHERE id = :i"), {"i": u2}
                )
                assert res.rowcount == 0  # other tenant's row is invisible → untouched

                # ── WITH CHECK blocks writing a row into another tenant (savepoint
                #    so the expected error doesn't abort the outer transaction).
                sp = await conn.begin_nested()
                with pytest.raises(Exception):
                    await conn.execute(
                        text(
                            "INSERT INTO users (id, tenant_id, email, full_name) "
                            "VALUES (:id, :t, :e, :f)"
                        ),
                        {"id": uuid.uuid4(), "t": t2, "e": "x@app.test", "f": "x"},
                    )
                await sp.rollback()

                # ── Least privilege: no DDL rights.
                sp = await conn.begin_nested()
                with pytest.raises(Exception):
                    await conn.execute(text("CREATE TABLE rls_should_fail (id int)"))
                await sp.rollback()

                await conn.execute(text("RESET ROLE"))
            finally:
                await trans.rollback()  # discard tenants, users AND the probe role
    finally:
        await engine.dispose()
