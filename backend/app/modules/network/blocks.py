"""Member blocking helpers shared by the network, messaging and groups services."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationError
from app.modules.network.models import UserBlock


async def hidden_user_ids(session: AsyncSession, me: uuid.UUID) -> set[uuid.UUID]:
    """Members I blocked and members who blocked me: neither side sees the other."""
    rows = await session.execute(
        select(UserBlock.blocker_id, UserBlock.blocked_id).where(
            or_(UserBlock.blocker_id == me, UserBlock.blocked_id == me), UserBlock.deleted_at.is_(None))
    )
    out: set[uuid.UUID] = set()
    for blocker, blocked in rows:
        out.add(blocked if blocker == me else blocker)
    return out


async def blocked_ids(session: AsyncSession, me: uuid.UUID) -> set[uuid.UUID]:
    """Members I blocked (the list I can unblock)."""
    return set(await session.scalars(select(UserBlock.blocked_id).where(UserBlock.blocker_id == me, UserBlock.deleted_at.is_(None))))


async def is_blocked_either_way(session: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> bool:
    return bool(await session.scalar(select(UserBlock.id).where(
        or_((UserBlock.blocker_id == a) & (UserBlock.blocked_id == b), (UserBlock.blocker_id == b) & (UserBlock.blocked_id == a)),
        UserBlock.deleted_at.is_(None)).limit(1)))


async def require_not_blocked(session: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> None:
    if await is_blocked_either_way(session, a, b):
        raise ConflictError("This member is not available.")


async def block(session: AsyncSession, me: uuid.UUID, target: uuid.UUID) -> UserBlock:
    if me == target:
        raise ValidationError("You cannot block yourself.")
    existing = await session.scalar(select(UserBlock).where(UserBlock.blocker_id == me, UserBlock.blocked_id == target, UserBlock.deleted_at.is_(None)))
    if existing is not None:
        return existing
    row = UserBlock(blocker_id=me, blocked_id=target)
    session.add(row)
    await session.flush()
    return row


async def unblock(session: AsyncSession, me: uuid.UUID, target: uuid.UUID) -> bool:
    existing = await session.scalar(select(UserBlock).where(UserBlock.blocker_id == me, UserBlock.blocked_id == target, UserBlock.deleted_at.is_(None)))
    if existing is None:
        return False
    await session.delete(existing)
    await session.flush()
    return True
