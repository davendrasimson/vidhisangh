"""Data-access layer for groups, memberships and group posts (global tables)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.groups.models import (
    Group,
    GroupMembership,
    GroupPost,
    GroupPostComment,
    GroupPostLike,
    GroupType,
    GroupVisibility,
    MemberStatus,
)


class GroupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, group: Group) -> None:
        self.session.add(group)

    async def get(self, group_id: uuid.UUID) -> Group | None:
        res = await self.session.execute(
            select(Group).where(Group.id == group_id, Group.deleted_at.is_(None))
        )
        return res.scalar_one_or_none()

    async def get_by_invite_code(self, code: str) -> Group | None:
        return await self.session.scalar(
            select(Group).where(Group.invite_code == code, Group.deleted_at.is_(None))
        )

    async def get_by_slug(self, slug: str) -> Group | None:
        res = await self.session.execute(
            select(Group).where(Group.slug == slug, Group.deleted_at.is_(None))
        )
        return res.scalar_one_or_none()

    async def discover(
        self, limit: int, offset: int, group_type: GroupType | None = None
    ) -> list[Group]:
        """Public groups, most-populous first (the discovery directory)."""
        stmt = select(Group).where(
            Group.deleted_at.is_(None),
            Group.visibility == GroupVisibility.PUBLIC,
        )
        if group_type is not None:
            stmt = stmt.where(Group.group_type == group_type)
        res = await self.session.execute(
            stmt.order_by(Group.member_count.desc(), Group.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())

    async def for_member(self, group_ids: Sequence[uuid.UUID]) -> list[Group]:
        if not group_ids:
            return []
        res = await self.session.execute(
            select(Group)
            .where(Group.id.in_(group_ids), Group.deleted_at.is_(None))
            .order_by(Group.name)
        )
        return list(res.scalars().all())


class MembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, membership: GroupMembership) -> None:
        self.session.add(membership)

    async def delete(self, membership: GroupMembership) -> None:
        await self.session.delete(membership)

    async def get(self, group_id: uuid.UUID, user_id: uuid.UUID) -> GroupMembership | None:
        res = await self.session.execute(
            select(GroupMembership).where(
                GroupMembership.group_id == group_id,
                GroupMembership.user_id == user_id,
            )
        )
        return res.scalar_one_or_none()

    async def for_user(
        self, user_id: uuid.UUID, status: MemberStatus | None = None
    ) -> list[GroupMembership]:
        stmt = select(GroupMembership).where(GroupMembership.user_id == user_id)
        if status is not None:
            stmt = stmt.where(GroupMembership.status == status)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def for_user_in_groups(
        self, user_id: uuid.UUID, group_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, GroupMembership]:
        if not group_ids:
            return {}
        res = await self.session.execute(
            select(GroupMembership).where(
                GroupMembership.user_id == user_id,
                GroupMembership.group_id.in_(group_ids),
            )
        )
        return {m.group_id: m for m in res.scalars().all()}

    async def list_for_group(
        self, group_id: uuid.UUID, status: MemberStatus
    ) -> list[GroupMembership]:
        res = await self.session.execute(
            select(GroupMembership)
            .where(
                GroupMembership.group_id == group_id,
                GroupMembership.status == status,
            )
            .order_by(GroupMembership.role, GroupMembership.member_name)
        )
        return list(res.scalars().all())

    async def count_active(self, group_id: uuid.UUID) -> int:
        res = await self.session.execute(
            select(func.count())
            .select_from(GroupMembership)
            .where(
                GroupMembership.group_id == group_id,
                GroupMembership.status == MemberStatus.ACTIVE,
            )
        )
        return int(res.scalar_one())


class GroupPostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, post: GroupPost) -> None:
        self.session.add(post)

    async def get(self, post_id: uuid.UUID) -> GroupPost | None:
        res = await self.session.execute(
            select(GroupPost).where(
                GroupPost.id == post_id, GroupPost.deleted_at.is_(None)
            )
        )
        return res.scalar_one_or_none()

    async def list_for_group(
        self, group_id: uuid.UUID, limit: int, offset: int
    ) -> list[GroupPost]:
        res = await self.session.execute(
            select(GroupPost)
            .where(GroupPost.group_id == group_id, GroupPost.deleted_at.is_(None))
            .order_by(GroupPost.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())

    async def latest_in_groups(self, group_ids: Sequence[uuid.UUID], limit: int) -> list[GroupPost]:
        """The newest posts across several groups (the member's home-screen card)."""
        if not group_ids:
            return []
        res = await self.session.execute(
            select(GroupPost)
            .where(GroupPost.group_id.in_(group_ids), GroupPost.deleted_at.is_(None))
            .order_by(GroupPost.created_at.desc())
            .limit(limit)
        )
        return list(res.scalars().all())


class GroupPostCommentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, comment: GroupPostComment) -> None:
        self.session.add(comment)

    async def delete(self, comment: GroupPostComment) -> None:
        await self.session.delete(comment)

    async def get(self, comment_id: uuid.UUID) -> GroupPostComment | None:
        res = await self.session.execute(
            select(GroupPostComment).where(
                GroupPostComment.id == comment_id,
                GroupPostComment.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def list_for_post(self, post_id: uuid.UUID) -> list[GroupPostComment]:
        res = await self.session.execute(
            select(GroupPostComment)
            .where(
                GroupPostComment.group_post_id == post_id,
                GroupPostComment.deleted_at.is_(None),
            )
            .order_by(GroupPostComment.created_at.asc())
        )
        return list(res.scalars().all())


class GroupPostLikeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, like: GroupPostLike) -> None:
        self.session.add(like)

    async def delete(self, like: GroupPostLike) -> None:
        await self.session.delete(like)

    async def get(self, post_id: uuid.UUID, user_id: uuid.UUID) -> GroupPostLike | None:
        res = await self.session.execute(
            select(GroupPostLike).where(
                GroupPostLike.group_post_id == post_id,
                GroupPostLike.user_id == user_id,
            )
        )
        return res.scalar_one_or_none()

    async def liked_post_ids(
        self, user_id: uuid.UUID, post_ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not post_ids:
            return set()
        res = await self.session.execute(
            select(GroupPostLike.group_post_id).where(
                GroupPostLike.user_id == user_id,
                GroupPostLike.group_post_id.in_(post_ids),
            )
        )
        return set(res.scalars().all())
