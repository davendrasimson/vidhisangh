"""Data-access layer for the professional network (global tables)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.network.models import (
    Comment,
    Connection,
    ConnectionStatus,
    Follow,
    NetworkIdentity,
    Post,
    PostBookmark,
    PostMention,
    PostReaction,
    PostVisibility,
)


class IdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID) -> NetworkIdentity | None:
        res = await self.session.execute(
            select(NetworkIdentity).where(NetworkIdentity.user_id == user_id)
        )
        return res.scalar_one_or_none()

    async def get_many(self, user_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, NetworkIdentity]:
        if not user_ids:
            return {}
        res = await self.session.execute(
            select(NetworkIdentity).where(NetworkIdentity.user_id.in_(user_ids))
        )
        return {i.user_id: i for i in res.scalars().all()}

    async def list_directory(
        self, exclude_user: uuid.UUID, limit: int, offset: int
    ) -> list[NetworkIdentity]:
        """Only people who opted in to the directory (``discoverable``)."""
        res = await self.session.execute(
            select(NetworkIdentity)
            .where(
                NetworkIdentity.user_id != exclude_user,
                NetworkIdentity.discoverable.is_(True),
            )
            .order_by(NetworkIdentity.display_name)
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())

    def add(self, identity: NetworkIdentity) -> None:
        self.session.add(identity)


class ConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def between(self, a: uuid.UUID, b: uuid.UUID) -> Connection | None:
        res = await self.session.execute(
            select(Connection).where(
                or_(
                    and_(Connection.requester_id == a, Connection.addressee_id == b),
                    and_(Connection.requester_id == b, Connection.addressee_id == a),
                )
            )
        )
        return res.scalar_one_or_none()

    async def get(self, connection_id: uuid.UUID) -> Connection | None:
        res = await self.session.execute(
            select(Connection).where(Connection.id == connection_id)
        )
        return res.scalar_one_or_none()

    async def accepted_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        res = await self.session.execute(
            select(Connection).where(
                Connection.status == ConnectionStatus.ACCEPTED,
                or_(
                    Connection.requester_id == user_id,
                    Connection.addressee_id == user_id,
                ),
            )
        )
        ids: set[uuid.UUID] = set()
        for c in res.scalars().all():
            ids.add(c.addressee_id if c.requester_id == user_id else c.requester_id)
        return ids

    async def list_for_user(
        self, user_id: uuid.UUID, status: ConnectionStatus | None
    ) -> list[Connection]:
        stmt = select(Connection).where(
            or_(Connection.requester_id == user_id, Connection.addressee_id == user_id)
        )
        if status is not None:
            stmt = stmt.where(Connection.status == status)
        res = await self.session.execute(stmt.order_by(Connection.created_at.desc()))
        return list(res.scalars().all())

    async def incoming_pending(self, user_id: uuid.UUID) -> list[Connection]:
        res = await self.session.execute(
            select(Connection).where(
                Connection.addressee_id == user_id,
                Connection.status == ConnectionStatus.PENDING,
            )
        )
        return list(res.scalars().all())

    def add(self, connection: Connection) -> None:
        self.session.add(connection)


class FollowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, follower: uuid.UUID, followee: uuid.UUID) -> Follow | None:
        res = await self.session.execute(
            select(Follow).where(
                Follow.follower_id == follower, Follow.followee_id == followee
            )
        )
        return res.scalar_one_or_none()

    async def following_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        res = await self.session.execute(
            select(Follow.followee_id).where(Follow.follower_id == user_id)
        )
        return set(res.scalars().all())

    def add(self, follow: Follow) -> None:
        self.session.add(follow)

    async def delete(self, follow: Follow) -> None:
        await self.session.delete(follow)


class PostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, post: Post) -> None:
        self.session.add(post)

    async def get(self, post_id: uuid.UUID) -> Post | None:
        res = await self.session.execute(
            select(Post).where(Post.id == post_id, Post.deleted_at.is_(None))
        )
        return res.scalar_one_or_none()

    async def feed(
        self, network_ids: set[uuid.UUID], limit: int, offset: int
    ) -> list[Post]:
        # Posts from the viewer's network, plus any public post.
        author_filter = Post.author_id.in_(network_ids) if network_ids else None
        visibility_filter = Post.visibility == PostVisibility.PUBLIC
        where = (
            or_(author_filter, visibility_filter)
            if author_filter is not None
            else visibility_filter
        )
        res = await self.session.execute(
            select(Post)
            .where(where, Post.deleted_at.is_(None))
            .order_by(Post.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())

    async def recent_public_hashtags(self, sample: int) -> list[list]:
        """The hashtag arrays of the most recent public posts (trending source)."""
        res = await self.session.execute(
            select(Post.hashtags)
            .where(Post.visibility == PostVisibility.PUBLIC, Post.deleted_at.is_(None))
            .order_by(Post.created_at.desc())
            .limit(sample)
        )
        return list(res.scalars().all())

    async def by_author(
        self, author_id: uuid.UUID, limit: int, offset: int, *, include_private: bool
    ) -> list[Post]:
        """An author's posts. ``include_private`` (viewer is the author or a
        connection) adds connections-only posts; otherwise public posts only."""
        conds = [Post.author_id == author_id, Post.deleted_at.is_(None)]
        if not include_private:
            conds.append(Post.visibility == PostVisibility.PUBLIC)
        res = await self.session.execute(
            select(Post)
            .where(*conds)
            .order_by(Post.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())


class ReactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, post_id: uuid.UUID, user_id: uuid.UUID) -> PostReaction | None:
        res = await self.session.execute(
            select(PostReaction).where(
                PostReaction.post_id == post_id, PostReaction.user_id == user_id
            )
        )
        return res.scalar_one_or_none()

    async def for_posts(
        self, user_id: uuid.UUID, post_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, PostReaction]:
        if not post_ids:
            return {}
        res = await self.session.execute(
            select(PostReaction).where(
                PostReaction.user_id == user_id, PostReaction.post_id.in_(post_ids)
            )
        )
        return {r.post_id: r for r in res.scalars().all()}

    def add(self, reaction: PostReaction) -> None:
        self.session.add(reaction)

    async def delete(self, reaction: PostReaction) -> None:
        await self.session.delete(reaction)


class MentionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, mention: PostMention) -> None:
        self.session.add(mention)

    async def for_posts(
        self, post_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[PostMention]]:
        if not post_ids:
            return {}
        res = await self.session.execute(
            select(PostMention).where(PostMention.post_id.in_(post_ids))
        )
        grouped: dict[uuid.UUID, list[PostMention]] = {}
        for mention in res.scalars().all():
            grouped.setdefault(mention.post_id, []).append(mention)
        return grouped

    async def posts_mentioning(
        self, user_id: uuid.UUID, limit: int, offset: int
    ) -> list[Post]:
        res = await self.session.execute(
            select(Post)
            .join(PostMention, PostMention.post_id == Post.id)
            .where(PostMention.mentioned_user_id == user_id, Post.deleted_at.is_(None))
            .order_by(Post.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())


class BookmarkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, bookmark: PostBookmark) -> None:
        self.session.add(bookmark)

    async def delete(self, bookmark: PostBookmark) -> None:
        await self.session.delete(bookmark)

    async def get(self, post_id: uuid.UUID, user_id: uuid.UUID) -> PostBookmark | None:
        res = await self.session.execute(
            select(PostBookmark).where(
                PostBookmark.post_id == post_id, PostBookmark.user_id == user_id
            )
        )
        return res.scalar_one_or_none()

    async def for_posts(
        self, user_id: uuid.UUID, post_ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not post_ids:
            return set()
        res = await self.session.execute(
            select(PostBookmark.post_id).where(
                PostBookmark.user_id == user_id, PostBookmark.post_id.in_(post_ids)
            )
        )
        return set(res.scalars().all())

    async def list_posts(self, user_id: uuid.UUID, limit: int, offset: int) -> list[Post]:
        res = await self.session.execute(
            select(Post)
            .join(PostBookmark, PostBookmark.post_id == Post.id)
            .where(PostBookmark.user_id == user_id, Post.deleted_at.is_(None))
            .order_by(PostBookmark.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())


class CommentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, comment: Comment) -> None:
        self.session.add(comment)

    async def get(self, comment_id: uuid.UUID) -> Comment | None:
        res = await self.session.execute(
            select(Comment).where(Comment.id == comment_id, Comment.deleted_at.is_(None))
        )
        return res.scalar_one_or_none()

    async def delete_for_post(self, post_id: uuid.UUID) -> None:  # pragma: no cover - admin tooling
        for c in await self.list_for_post(post_id):
            c.deleted_at = datetime.now(UTC)

    async def list_for_post(self, post_id: uuid.UUID) -> list[Comment]:
        res = await self.session.execute(
            select(Comment)
            .where(Comment.post_id == post_id, Comment.deleted_at.is_(None))
            .order_by(Comment.created_at.asc())
        )
        return list(res.scalars().all())
