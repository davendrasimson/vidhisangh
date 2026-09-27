"""Professional network service — business logic.

Author display data is denormalised from the acting user's own tenant identity
(readable under their session) into a global ``NetworkIdentity`` and onto posts /
comments, so feeds render across tenants without cross-tenant RLS joins.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.modules.identity.repository import UserRepository
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
    ReactionType,
)
from app.modules.network.repository import (
    BookmarkRepository,
    CommentRepository,
    ConnectionRepository,
    FollowRepository,
    IdentityRepository,
    MentionRepository,
    PostRepository,
    ReactionRepository,
)
from app.modules.network.schemas import (
    CommentCreate,
    ConnectionRequestCreate,
    PostCreate,
    ReactionCreate,
    ShareCreate,
)
from app.modules.notifications.models import NotificationType
from app.modules.notifications.service import create_notification
from app.modules.profile.repository import ProfileRepository

# Posts plus the viewer's per-post annotations: reactions, bookmarks, mentions.
AnnotatedPosts = tuple[
    list[Post],
    dict[uuid.UUID, PostReaction],
    set[uuid.UUID],
    dict[uuid.UUID, list[PostMention]],
]


class NetworkService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.identities = IdentityRepository(session)
        self.connections = ConnectionRepository(session)
        self.follows = FollowRepository(session)
        self.posts = PostRepository(session)
        self.reactions = ReactionRepository(session)
        self.comments = CommentRepository(session)
        self.bookmarks = BookmarkRepository(session)
        self.mentions = MentionRepository(session)

    # ── Identity projection ─────────────────────────────────────────
    async def ensure_my_identity(self) -> NetworkIdentity:
        """Upsert the acting user's public directory identity from their own
        (tenant-readable) user + profile records."""
        user = await UserRepository(self.session).get_by_id(self.user_id)
        if user is None:
            raise NotFoundError("User not found.")
        profile = await ProfileRepository(self.session).get_by_user(self.user_id)

        identity = await self.identities.get(self.user_id)
        headline = profile.headline if profile else None
        city = profile.city if profile else None
        verified = bool(profile and profile.is_verified)
        if identity is None:
            identity = NetworkIdentity(
                user_id=self.user_id,
                tenant_id=self.tenant_id,
                display_name=user.display_name or user.full_name,
                headline=headline,
                avatar_url=user.avatar_url,
                city=city,
                is_verified=verified,
            )
            self.identities.add(identity)
            await self.session.flush()
        else:
            identity.display_name = user.display_name or user.full_name
            identity.headline = headline
            identity.avatar_url = user.avatar_url
            identity.city = city
            identity.is_verified = verified
        return identity

    async def network_ids(self) -> set[uuid.UUID]:
        ids = await self.connections.accepted_ids(self.user_id)
        ids |= await self.follows.following_ids(self.user_id)
        ids.add(self.user_id)
        return ids

    # ── Posts & feed ────────────────────────────────────────────────
    async def create_post(self, data: PostCreate) -> Post:
        me = await self.ensure_my_identity()
        post = Post(
            author_id=self.user_id,
            author_name=me.display_name,
            author_headline=me.headline,
            author_avatar_url=me.avatar_url,
            post_type=data.post_type,
            title=data.title,
            content=data.content,
            visibility=data.visibility,
            hashtags=data.hashtags,
            link_url=data.link_url,
            link_title=data.link_title,
            link_description=data.link_description,
            link_image=data.link_image,
            link_site_name=data.link_site_name,
        )
        self.posts.add(post)
        await self.session.flush()
        await self._attach_mentions(post.id, data.mention_ids)
        return post

    async def _attach_mentions(
        self, post_id: uuid.UUID, mention_ids: list[uuid.UUID]
    ) -> None:
        unique_ids = [uid for uid in dict.fromkeys(mention_ids) if uid != self.user_id]
        if not unique_ids:
            return
        identities = await self.identities.get_many([self.user_id, *unique_ids])
        me = identities.get(self.user_id)
        actor_name = me.display_name if me else "Someone"
        for uid in unique_ids:
            identity = identities.get(uid)
            if identity is not None:
                self.mentions.add(
                    PostMention(
                        post_id=post_id,
                        mentioned_user_id=uid,
                        mentioned_name=identity.display_name,
                    )
                )
                await create_notification(
                    self.session,
                    user_id=uid,
                    type=NotificationType.MENTION,
                    actor_id=self.user_id,
                    actor_name=actor_name,
                    message=f"{actor_name} mentioned you in a post",
                    link="/app/network",
                )
        await self.session.flush()

    async def get_post(self, post_id: uuid.UUID) -> Post:
        post = await self.posts.get(post_id)
        if post is None:
            raise NotFoundError("Post not found.")
        return post

    async def share(self, post_id: uuid.UUID, data: ShareCreate) -> Post:
        target = await self.get_post(post_id)
        me = await self.ensure_my_identity()
        # Dereference: sharing a repost quotes the ultimate original, not the repost.
        if target.shared_from_id is not None:
            origin_id = target.shared_from_id
            origin_name = target.shared_author_name
            origin_avatar = target.shared_author_avatar_url
            origin_content = target.shared_content
            origin_created = target.shared_created_at
        else:
            origin_id = target.id
            origin_name = target.author_name
            origin_avatar = target.author_avatar_url
            origin_content = target.content
            origin_created = target.created_at

        repost = Post(
            author_id=self.user_id,
            author_name=me.display_name,
            author_headline=me.headline,
            author_avatar_url=me.avatar_url,
            content=data.content,
            visibility=PostVisibility.PUBLIC,
            hashtags=[],
            shared_from_id=origin_id,
            shared_author_name=origin_name,
            shared_author_avatar_url=origin_avatar,
            shared_content=origin_content,
            shared_created_at=origin_created,
        )
        self.posts.add(repost)
        # Credit the share to the ultimate original if it still exists.
        root = await self.posts.get(origin_id)
        if root is not None:
            root.share_count += 1
        await self.session.flush()
        return repost

    async def delete_post(self, post_id: uuid.UUID) -> None:
        post = await self.get_post(post_id)
        if post.author_id != self.user_id:
            raise PermissionDeniedError("You can only delete your own posts.")
        post.deleted_at = datetime.now(UTC)

    async def feed(self, limit: int, offset: int) -> "AnnotatedPosts":
        posts = await self.posts.feed(await self.network_ids(), limit, offset)
        return await self._annotate(posts)

    async def author_posts(self, author_id: uuid.UUID, limit: int, offset: int) -> list[Post]:
        return await self.posts.by_author(author_id, limit, offset)

    async def _annotate(self, posts: list[Post]) -> "AnnotatedPosts":
        post_ids = [p.id for p in posts]
        my_reactions = await self.reactions.for_posts(self.user_id, post_ids)
        my_bookmarks = await self.bookmarks.for_posts(self.user_id, post_ids)
        mentions = await self.mentions.for_posts(post_ids)
        return posts, my_reactions, my_bookmarks, mentions

    # ── Bookmarks ───────────────────────────────────────────────────
    async def bookmark(self, post_id: uuid.UUID) -> None:
        await self.get_post(post_id)
        if await self.bookmarks.get(post_id, self.user_id) is None:
            self.bookmarks.add(PostBookmark(post_id=post_id, user_id=self.user_id))

    async def unbookmark(self, post_id: uuid.UUID) -> None:
        existing = await self.bookmarks.get(post_id, self.user_id)
        if existing is not None:
            await self.bookmarks.delete(existing)

    async def list_bookmarks(self, limit: int, offset: int) -> AnnotatedPosts:
        posts = await self.bookmarks.list_posts(self.user_id, limit, offset)
        return await self._annotate(posts)

    async def list_mentions(self, limit: int, offset: int) -> AnnotatedPosts:
        posts = await self.mentions.posts_mentioning(self.user_id, limit, offset)
        return await self._annotate(posts)

    async def mentions_of(self, post_id: uuid.UUID) -> list[PostMention]:
        grouped = await self.mentions.for_posts([post_id])
        return grouped.get(post_id, [])

    # ── Trending ────────────────────────────────────────────────────
    async def trending(self, limit: int, sample: int = 300) -> list[tuple[str, int]]:
        """Most-used hashtags across the most recent public posts."""
        rows = await self.posts.recent_public_hashtags(sample)
        counter: Counter[str] = Counter()
        for tags in rows:
            for tag in tags or []:
                if isinstance(tag, str) and tag.strip():
                    counter[tag.strip().lower()] += 1
        return counter.most_common(limit)

    # ── Reactions ───────────────────────────────────────────────────
    async def react(self, post_id: uuid.UUID, data: ReactionCreate) -> PostReaction:
        post = await self.get_post(post_id)
        existing = await self.reactions.get(post_id, self.user_id)
        if existing is not None:
            existing.reaction = data.reaction  # change reaction type, count unchanged
            return existing
        reaction = PostReaction(
            post_id=post_id, user_id=self.user_id, reaction=data.reaction
        )
        self.reactions.add(reaction)
        post.like_count += 1
        await self.session.flush()
        return reaction

    async def unreact(self, post_id: uuid.UUID) -> None:
        post = await self.get_post(post_id)
        existing = await self.reactions.get(post_id, self.user_id)
        if existing is None:
            return
        await self.reactions.delete(existing)
        post.like_count = max(0, post.like_count - 1)

    # ── Comments ────────────────────────────────────────────────────
    async def add_comment(self, post_id: uuid.UUID, data: CommentCreate) -> Comment:
        post = await self.get_post(post_id)
        me = await self.ensure_my_identity()
        comment = Comment(
            post_id=post_id,
            parent_id=data.parent_id,
            author_id=self.user_id,
            author_name=me.display_name,
            author_avatar_url=me.avatar_url,
            body=data.body,
        )
        self.comments.add(comment)
        post.comment_count += 1
        await self.session.flush()
        return comment

    async def list_comments(self, post_id: uuid.UUID) -> list[Comment]:
        await self.get_post(post_id)
        return await self.comments.list_for_post(post_id)

    async def delete_comment(self, comment_id: uuid.UUID) -> None:
        comment = await self.comments.get(comment_id)
        if comment is None:
            raise NotFoundError("Comment not found.")
        if comment.author_id != self.user_id:
            raise PermissionDeniedError("You can only delete your own comments.")
        comment.deleted_at = datetime.now(UTC)
        post = await self.posts.get(comment.post_id)
        if post is not None:
            post.comment_count = max(0, post.comment_count - 1)

    # ── Connections ─────────────────────────────────────────────────
    async def request_connection(
        self, target_id: uuid.UUID, data: ConnectionRequestCreate
    ) -> Connection:
        if target_id == self.user_id:
            raise ValidationError("You cannot connect with yourself.")
        me = await self.ensure_my_identity()
        existing = await self.connections.between(self.user_id, target_id)
        if existing is not None:
            if existing.status == ConnectionStatus.ACCEPTED:
                raise ConflictError("You are already connected.")
            raise ConflictError("A connection request already exists.")
        connection = Connection(
            requester_id=self.user_id,
            addressee_id=target_id,
            message=data.message,
            status=ConnectionStatus.PENDING,
        )
        self.connections.add(connection)
        await create_notification(
            self.session,
            user_id=target_id,
            type=NotificationType.CONNECTION_REQUEST,
            actor_id=self.user_id,
            actor_name=me.display_name,
            message=f"{me.display_name} sent you a connection request",
            link="/app/people",
        )
        await self.session.flush()
        return connection

    async def respond_connection(self, connection_id: uuid.UUID, accept: bool) -> Connection:
        connection = await self.connections.get(connection_id)
        if connection is None:
            raise NotFoundError("Connection request not found.")
        if connection.addressee_id != self.user_id:
            raise PermissionDeniedError("Only the recipient can respond to this request.")
        if connection.status != ConnectionStatus.PENDING:
            raise ConflictError("This request has already been answered.")
        connection.status = ConnectionStatus.ACCEPTED if accept else ConnectionStatus.DECLINED
        connection.responded_at = datetime.now(UTC)
        if accept:
            me = await self.ensure_my_identity()
            await create_notification(
                self.session,
                user_id=connection.requester_id,
                type=NotificationType.CONNECTION_ACCEPTED,
                actor_id=self.user_id,
                actor_name=me.display_name,
                message=f"{me.display_name} accepted your connection request",
                link=f"/app/people/{self.user_id}",
            )
        return connection

    async def list_connections(self, status: ConnectionStatus | None) -> list[Connection]:
        return await self.connections.list_for_user(self.user_id, status)

    async def incoming_requests(self) -> list[Connection]:
        return await self.connections.incoming_pending(self.user_id)

    # ── Follows ─────────────────────────────────────────────────────
    async def follow(self, target_id: uuid.UUID) -> None:
        if target_id == self.user_id:
            raise ValidationError("You cannot follow yourself.")
        await self.ensure_my_identity()
        if await self.follows.get(self.user_id, target_id) is None:
            self.follows.add(Follow(follower_id=self.user_id, followee_id=target_id))

    async def unfollow(self, target_id: uuid.UUID) -> None:
        existing = await self.follows.get(self.user_id, target_id)
        if existing is not None:
            await self.follows.delete(existing)

    # ── Directory & public profile ──────────────────────────────────
    async def public_profile(
        self, user_id: uuid.UUID
    ) -> tuple[NetworkIdentity, str | None, bool]:
        identity = await self.identities.get(user_id)
        if identity is None:
            raise NotFoundError("This person is not on the network.")
        following = user_id in await self.follows.following_ids(self.user_id)
        conn = await self.connections.between(self.user_id, user_id)
        status: str | None = None
        if conn is not None:
            if conn.status == ConnectionStatus.ACCEPTED:
                status = "connected"
            elif conn.status == ConnectionStatus.PENDING:
                status = "pending_out" if conn.requester_id == self.user_id else "pending_in"
        return identity, status, following

    async def directory(self, limit: int, offset: int) -> list[tuple[NetworkIdentity, str | None, bool]]:
        await self.ensure_my_identity()
        people = await self.identities.list_directory(self.user_id, limit, offset)
        following = await self.follows.following_ids(self.user_id)
        annotated: list[tuple[NetworkIdentity, str | None, bool]] = []
        for person in people:
            conn = await self.connections.between(self.user_id, person.user_id)
            status: str | None = None
            if conn is not None:
                if conn.status == ConnectionStatus.ACCEPTED:
                    status = "connected"
                elif conn.status == ConnectionStatus.PENDING:
                    status = "pending_out" if conn.requester_id == self.user_id else "pending_in"
            annotated.append((person, status, person.user_id in following))
        return annotated
