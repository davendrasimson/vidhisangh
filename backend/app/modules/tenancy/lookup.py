"""Small helpers other modules use to validate foreign keys against the tenant.

Mirrors ``app.modules.clients.lookup.require_client`` (audit A-32): an id a
caller supplies must belong to *this* tenant, otherwise 404 — never a row of
another tenant, and never a dangling reference.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError


async def require_tenant_user(session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID):  # noqa: ANN201
    """The active user, or 404 — never a user of another tenant."""
    from app.modules.identity.models import User

    res = await session.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id, User.deleted_at.is_(None))
    )
    user = res.scalar_one_or_none()
    if user is None or not user.is_active:
        raise NotFoundError("That person is not a member of this organisation.")
    return user


async def require_tenant_matter(session: AsyncSession, tenant_id: uuid.UUID, matter_id: uuid.UUID):  # noqa: ANN201
    """The matter, or 404 — never a matter of another tenant."""
    from app.modules.matters.repository import MatterRepository

    matter = await MatterRepository(session).get(tenant_id, matter_id)
    if matter is None:
        raise NotFoundError("Matter not found.")
    return matter
