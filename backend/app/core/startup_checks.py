"""Start-up assertions that need a live connection (audit A-14).

``assert_database_role_safe`` refuses to boot in production when the database
role the app connects as is ``SUPERUSER`` or ``BYPASSRLS`` — either attribute
makes PostgreSQL skip every row-level-security policy, silently turning the
tenant isolation off. Outside production it logs loudly instead. Skipped on
non-PostgreSQL engines (the SQLite test suite).
"""

from __future__ import annotations

import structlog
from sqlalchemy import text

from app.core.config import settings
from app.core.database import get_engine

log = structlog.get_logger("app.startup")

_ROLE_SQL = text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")


async def assert_database_role_safe() -> None:
    if not settings.DB_ROLE_CHECK:
        log.warning("db_role_check_disabled")
        return
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        return
    try:
        async with engine.connect() as conn:
            row = (await conn.execute(_ROLE_SQL)).one_or_none()
    except Exception as exc:  # noqa: BLE001 - connectivity, not privilege
        log.warning("db_role_check_skipped", error=str(exc))
        return
    if row is None:
        return
    is_super, bypass = bool(row[0]), bool(row[1])
    if not (is_super or bypass):
        log.info("db_role_check_ok")
        return
    problem = (
        "The database role is "
        + " and ".join(a for a, on in (("SUPERUSER", is_super), ("BYPASSRLS", bypass)) if on)
        + " — row-level security would be bypassed for every tenant."
    )
    if settings.is_production:
        raise RuntimeError(f"Refusing to start: {problem}")
    log.warning("db_role_privileged", detail=problem)
