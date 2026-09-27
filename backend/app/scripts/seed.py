"""Idempotent seeder for the RBAC catalog (permissions + system roles).

Run with:  ``python -m app.scripts.seed``

Safe to run repeatedly — it upserts the permission catalog and the system-role
→ permission mappings defined in ``app.modules.identity.rbac``. System roles are
tenant-agnostic (``tenant_id IS NULL``) and shared by every tenant.
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select

import app.db.base  # noqa: F401 — register all models so FK targets resolve
from app.core.database import session_scope
from app.modules.identity.models import Permission, Role
from app.modules.identity.rbac import (
    ALL_PERMISSION_CODES,
    PERMISSIONS,
    SYSTEM_ROLES,
    WILDCARD,
)

log = structlog.get_logger("app.seed")


async def seed() -> None:
    # Bypass RLS: seeding writes global catalog rows outside any tenant.
    async with session_scope(bypass_rls=True) as session:
        # ── Permissions ─────────────────────────────────────────────
        existing_perms = {
            p.code: p
            for p in (await session.execute(select(Permission))).scalars().all()
        }
        for pdef in PERMISSIONS:
            perm = existing_perms.get(pdef.code)
            if perm is None:
                perm = Permission(
                    code=pdef.code,
                    name=pdef.name,
                    module=pdef.module,
                    description=pdef.description,
                )
                session.add(perm)
                existing_perms[pdef.code] = perm
            else:
                perm.name, perm.module, perm.description = (
                    pdef.name,
                    pdef.module,
                    pdef.description,
                )
        await session.flush()

        # ── System roles ────────────────────────────────────────────
        existing_roles = {
            r.code: r
            for r in (
                await session.execute(select(Role).where(Role.tenant_id.is_(None)))
            )
            .scalars()
            .all()
        }
        for rdef in SYSTEM_ROLES:
            role = existing_roles.get(rdef.code)
            if role is None:
                role = Role(
                    code=rdef.code,
                    name=rdef.name,
                    description=rdef.description,
                    is_system=True,
                    tenant_id=None,
                )
                session.add(role)
            else:
                role.name, role.description, role.is_system = (
                    rdef.name,
                    rdef.description,
                    True,
                )
            codes = (
                ALL_PERMISSION_CODES
                if rdef.permissions == [WILDCARD]
                else rdef.permissions
            )
            role.permissions = [existing_perms[c] for c in codes if c in existing_perms]

        log.info(
            "seed_complete",
            permissions=len(PERMISSIONS),
            roles=len(SYSTEM_ROLES),
        )


if __name__ == "__main__":
    asyncio.run(seed())
