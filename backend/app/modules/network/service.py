"""Professional network service — business logic.

Author display data is denormalised from the acting user's own tenant identity
(readable under their session) into a global ``NetworkIdentity`` and onto posts /
comments, so feeds render across tenants without cross-tenant RLS joins.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.core.storage import Storage
from app.modules.identity.rbac import is_judicial
from app.modules.identity.repository import UserRepository
from app.modules.network.models import (
    Audience,
    Comment,
    Connection,
    ConnectionStatus,
    Follow,
    NetworkIdentity,
    Post,
    PostBookmark,
    PostImage,
    PostMention,
    PostReaction,
    PostVisibility,
    ReactionType,
    UserBlock,
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
from app.modules.network import blocks
from app.modules.notifications.models import NotificationType
from app.modules.notifications.service import create_notification
from app.modules.profile.models import ProfileVisibility
from app.modules.profile.repository import ProfileRepository

# Posts plus the viewer's per-post annotations: reactions, bookmarks, mentions,
# and the photos of reposted originals.
AnnotatedPosts = tuple[
    list[Post],
    dict[uuid.UUID, PostReaction],
    set[uuid.UUID],
    dict[uuid.UUID, list[PostMention]],
    dict[uuid.UUID, list[PostImage]],
]


RESERVED_HANDLES = frozenset({"app", "api", "admin", "vidhisangh", "official", "support", "help", "about", "acts", "tools", "judgments", "in"})


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
        if user.network_profile_removed_at is not None:
            raise PermissionDeniedError(
                "Your network profile has been removed. Contact the Grievance Cell for review."
            )
        profile = await ProfileRepository(self.session).get_by_user(self.user_id)

        identity = await self.identities.get(self.user_id)
        headline = profile.headline if profile else None
        city = profile.city if profile else None
        judicial = bool(profile and is_judicial(profile.professional_role))
        state = (profile.judicial_state if judicial and profile.judicial_state else profile.state) if profile else None
        verified = bool(profile and profile.is_verified)
        if identity is None:
            # Listed by default (owner, 1 Nov 2026); a judicial officer is hidden until they choose an audience.
            identity = NetworkIdentity(
                user_id=self.user_id,
                tenant_id=self.tenant_id,
                display_name=user.display_name or user.full_name,
                headline=headline,
                avatar_url=user.avatar_url,
                city=city,
                state=state,
                is_verified=verified,
                is_judicial=judicial,
                discoverable=not judicial,
                audience=Audience.NONE if judicial else Audience.EVERYONE,
            )
            self.identities.add(identity)
            await self.session.flush()
        else:
            identity.display_name = user.display_name or user.full_name
            identity.headline = headline
            identity.avatar_url = user.avatar_url
            identity.city = city
            identity.state = state
            identity.is_verified = verified
            if judicial and not identity.is_judicial:
                # Became (or was found to be) a judicial officer: hide until they choose.
                identity.is_judicial, identity.discoverable, identity.audience = True, False, Audience.NONE
            elif not judicial and identity.is_judicial:
                identity.is_judicial = False
        # A profile the user made non-public always overrides the directory
        # opt-in (ProfessionalProfile.visibility is tenant-scoped, so it is
        # enforced here — at sync time — rather than in the cross-tenant query).
        if profile is not None and profile.visibility != ProfileVisibility.PUBLIC and identity.discoverable:
            identity.discoverable = False
        if profile is not None and profile.visibility != ProfileVisibility.PUBLIC and identity.public_page:
            identity.public_page = False
        return identity

    async def set_public_page(self, enabled: bool, handle: str | None = None) -> NetworkIdentity:
        """The public profile page at /in/<handle>/ (open web, search engines).

        A separate consent from the in-app directory, recorded with its time.
        Needs a public professional profile. The handle is kept when the page
        is turned off, so turning it back on gives the same address."""
        identity = await self.ensure_my_identity()
        if enabled:
            profile = await ProfileRepository(self.session).get_by_user(self.user_id)
            if profile is not None and profile.visibility != ProfileVisibility.PUBLIC:
                raise ValidationError("Set your professional profile to public before publishing a public page.")
            if handle and handle != identity.public_handle:
                if handle in RESERVED_HANDLES or await self._handle_taken(handle):
                    raise ConflictError("That address is taken. Try another.")
                identity.public_handle = handle
            elif not identity.public_handle:
                identity.public_handle = await self._free_handle(identity.display_name)
            identity.public_page_consented_at = datetime.now(UTC)
        identity.public_page = enabled
        await self.session.flush()
        return identity

    async def _handle_taken(self, handle: str) -> bool:
        return await self.session.scalar(
            select(NetworkIdentity.id).where(NetworkIdentity.public_handle == handle, NetworkIdentity.user_id != self.user_id)
        ) is not None

    async def _free_handle(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:34].strip("-") or "member"
        base = re.sub(r"^(adv|advocate|dr|mr|mrs|ms)-", "", base) or base
        if len(base) < 3:
            base = f"{base}-adv"
        candidate, n = base, 1
        while candidate in RESERVED_HANDLES or await self._handle_taken(candidate):
            n += 1
            candidate = f"{base}-{n}"
        return candidate

    async def set_discoverable(self, discoverable: bool | None, audience: str | None = None) -> NetworkIdentity:
        """Directory opt-in / opt-out (audit P-10) and the audience who may see a listed member.
        Opting in requires a public professional profile (or none). A judicial officer is listed by
        choosing an audience; choosing `none` hides them again."""
        identity = await self.ensure_my_identity()
        if audience is not None:
            identity.audience = Audience(audience)
            if identity.is_judicial:
                discoverable = audience != Audience.NONE
            elif audience == Audience.NONE:
                discoverable = False
        if discoverable is None:
            discoverable = identity.discoverable
        if discoverable:
            profile = await ProfileRepository(self.session).get_by_user(self.user_id)
            if profile is not None and profile.visibility != ProfileVisibility.PUBLIC:
                raise ValidationError(
                    "Set your professional profile to public before joining the directory."
                )
            if identity.is_judicial and identity.audience == Audience.NONE:
                raise ValidationError("Choose who may see you: your connections, your groups, your bar or everyone.")
            if not identity.is_judicial and identity.audience == Audience.NONE:
                identity.audience = Audience.EVERYONE
        identity.discoverable = discoverable
        return identity

    # ── Visibility (audit A-17) ─────────────────────────────────────
    async def _is_connected(self, other_id: uuid.UUID) -> bool:
        conn = await self.connections.between(self.user_id, other_id)
        return conn is not None and conn.status == ConnectionStatus.ACCEPTED

    async def _can_view_author(self, author_id: uuid.UUID) -> bool:
        return author_id == self.user_id or await self._is_connected(author_id)

    async def _require_post_visible(self, post: Post) -> Post:
        """Public posts are visible to everyone; connections-only posts to the
        author and their accepted connections. Others get 404 (no existence leak)."""
        if post.visibility == PostVisibility.PUBLIC:
            return post
        if await self._can_view_author(post.author_id):
            return post
        raise NotFoundError("Post not found.")

    async def network_ids(self) -> set[uuid.UUID]:
        ids = await self.connections.accepted_ids(self.user_id)
        ids |= await self.follows.following_ids(self.user_id)
        ids.add(self.user_id)
        return ids

    # ── Posts & feed ────────────────────────────────────────────────
    async def _ensure_posting_allowed(self) -> None:
        user = await UserRepository(self.session).get_by_id(self.user_id)
        if user is None:
            raise NotFoundError("User not found.")
        until = user.posting_restricted_until
        until_utc = until if until is None or until.tzinfo else until.replace(tzinfo=UTC)
        if until_utc is not None and until_utc > datetime.now(UTC):
            raise PermissionDeniedError(
                f"Posting is restricted until {until_utc:%d %b %Y, %I:%M %p UTC}."
            )
        if until is not None:
            user.posting_restricted_until = None

    async def create_post(self, data: PostCreate) -> Post:
        await self._ensure_posting_allowed()
        me = await self.ensure_my_identity()
        content, content_html = data.content.strip(), None
        if data.content_html and data.content_html.strip():
            from app.core.html_clean import clean_html, html_to_text

            content_html = clean_html(data.content_html) or None
            content = html_to_text(content_html) if content_html else ""
        if len(content) > 8000:
            raise ValidationError("This post is too long: keep it under 8,000 characters.")
        images = await self._claim_images(data.image_ids)
        if not content and not images:
            raise ValidationError("Write something or add a photo.")
        post = Post(
            author_id=self.user_id,
            author_name=me.display_name,
            author_headline=me.headline,
            author_avatar_url=me.avatar_url,
            post_type=data.post_type,
            title=data.title,
            content=content,
            content_html=content_html,
            visibility=data.visibility,
            hashtags=data.hashtags,
            link_url=data.link_url,
            link_title=data.link_title,
            link_description=data.link_description,
            link_image=data.link_image,
            link_site_name=data.link_site_name,
        )
        # Set before the first flush: appending to a flushed relationship
        # raises MissingGreenlet under async.
        post.images = images
        self.posts.add(post)
        await self.session.flush()
        await self._attach_mentions(post.id, data.mention_ids)
        return post

    async def _claim_images(self, image_ids: list[uuid.UUID]) -> list[PostImage]:
        """The caller's own unattached uploads, in the order given."""
        from sqlalchemy import select

        ids = list(dict.fromkeys(image_ids))
        if not ids:
            return []
        rows = {
            img.id: img
            for img in await self.session.scalars(
                select(PostImage).where(
                    PostImage.id.in_(ids), PostImage.uploader_id == self.user_id,
                    PostImage.post_id.is_(None), PostImage.group_post_id.is_(None), PostImage.deleted_at.is_(None),
                )
            )
        }
        if len(rows) != len(ids):
            raise ValidationError("One of the photos is no longer available. Remove it and add it again.")
        for position, image_id in enumerate(ids):
            rows[image_id].position = position
        return [rows[i] for i in ids]

    async def upload_image(self, data: bytes, storage: Storage) -> PostImage:
        from app.core.malware import scan_upload
        from app.core.ratelimit import RateLimiter
        from app.modules.network.media import prepare_post_image

        await self._ensure_posting_allowed()
        await RateLimiter(times=40, window_seconds=3600, scope="post-image").check(str(self.user_id))
        cleaned, kind, width, height = prepare_post_image(data)
        await scan_upload(cleaned)
        image_id = uuid.uuid4()
        key = f"network/post-images/{image_id}.{'png' if kind == 'image/png' else 'jpg'}"
        await storage.put(key, cleaned, kind)
        image = PostImage(id=image_id, uploader_id=self.user_id, storage_key=key, content_type=kind,
                          size_bytes=len(cleaned), width=width, height=height)
        self.session.add(image)
        await self.session.flush()
        return image

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
        return await self._require_post_visible(post)

    async def share(self, post_id: uuid.UUID, data: ShareCreate) -> Post:
        await self._ensure_posting_allowed()
        target = await self.get_post(post_id)
        # A repost is always public, so only public content may be quoted —
        # otherwise a connection could launder a connections-only post.
        if target.visibility != PostVisibility.PUBLIC:
            raise PermissionDeniedError("Only public posts can be reposted.")
        if target.shared_from_id is not None:
            origin = await self.posts.get(target.shared_from_id)
            if origin is not None and origin.visibility != PostVisibility.PUBLIC:
                raise PermissionDeniedError("Only public posts can be reposted.")
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
            images=[],  # set before flush (async relationship)
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
        hidden = await blocks.hidden_user_ids(self.session, self.user_id)
        posts = await self.posts.feed(await self.network_ids(), limit, offset, exclude_authors=hidden)
        return await self._annotate(posts)

    async def author_posts(self, author_id: uuid.UUID, limit: int, offset: int) -> list[Post]:
        include_private = await self._can_view_author(author_id)
        return await self.posts.by_author(author_id, limit, offset, include_private=include_private)

    async def _annotate(self, posts: list[Post]) -> "AnnotatedPosts":
        post_ids = [p.id for p in posts]
        my_reactions = await self.reactions.for_posts(self.user_id, post_ids)
        my_bookmarks = await self.bookmarks.for_posts(self.user_id, post_ids)
        mentions = await self.mentions.for_posts(post_ids)
        origin_ids = {p.shared_from_id for p in posts if p.shared_from_id}
        shared_images: dict[uuid.UUID, list[PostImage]] = {}
        if origin_ids:
            live = select(Post.id).where(Post.id.in_(origin_ids), Post.deleted_at.is_(None))
            for image in await self.session.scalars(
                select(PostImage).where(PostImage.post_id.in_(live)).order_by(PostImage.position)
            ):
                shared_images.setdefault(image.post_id, []).append(image)
        return posts, my_reactions, my_bookmarks, mentions, shared_images

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
        if data.parent_id is not None:
            parent = await self.comments.get(data.parent_id)
            if parent is None or parent.post_id != post_id:
                raise ValidationError("The parent comment does not belong to this post.")
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
        await blocks.require_not_blocked(self.session, self.user_id, target_id)
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
        # Someone who blocked me is not reachable; someone I blocked still is (so I can unblock).
        if user_id != self.user_id and await self.session.scalar(select(UserBlock.id).where(
                UserBlock.blocker_id == user_id, UserBlock.blocked_id == self.user_id, UserBlock.deleted_at.is_(None))):
            raise NotFoundError("This person is not on the network.")
        following = user_id in await self.follows.following_ids(self.user_id)
        conn = await self.connections.between(self.user_id, user_id)
        # Someone who opted out of the directory is only reachable by people
        # already in a relationship with them (self, connections incl. pending).
        if not identity.discoverable and user_id != self.user_id and conn is None:
            raise NotFoundError("This person is not on the network.")
        # A listed member's audience (a judicial officer's choice) applies to the profile page too,
        # unless a relationship already exists.
        if user_id != self.user_id and conn is None:
            me = await self.ensure_my_identity()
            if not await self.visible_to(me, identity):
                raise NotFoundError("This person is not on the network.")
        status: str | None = None
        if conn is not None:
            if conn.status == ConnectionStatus.ACCEPTED:
                status = "connected"
            elif conn.status == ConnectionStatus.PENDING:
                status = "pending_out" if conn.requester_id == self.user_id else "pending_in"
        return identity, status, following

    async def directory(self, limit: int, offset: int) -> list[tuple[NetworkIdentity, str | None, bool]]:
        me = await self.ensure_my_identity()
        people = await self.identities.list_directory(self.user_id, limit, offset)
        return await self._with_relationship(await self._visible(me, people))

    async def _visible(self, me: NetworkIdentity, people: list[NetworkIdentity]) -> list[NetworkIdentity]:
        """Drop the members whose audience does not include me (a judicial officer's choice), and
        members blocked either way."""
        hidden = await blocks.hidden_user_ids(self.session, self.user_id)
        out = []
        for person in people:
            if person.user_id in hidden:
                continue
            if await self.visible_to(me, person):
                out.append(person)
        return out

    async def visible_to(self, viewer: NetworkIdentity, target: NetworkIdentity) -> bool:
        """May `viewer` see `target` in the directory and on their profile page?
        everyone: yes; connections: an accepted connection; groups: an active membership of a shared
        group; bar: both in the same State; none: no."""
        if viewer.user_id == target.user_id:
            return True
        audience = target.audience or Audience.EVERYONE
        if audience == Audience.EVERYONE:
            return True
        if audience == Audience.NONE:
            return False
        if audience == Audience.CONNECTIONS:
            conn = await self.connections.between(viewer.user_id, target.user_id)
            return conn is not None and conn.status == ConnectionStatus.ACCEPTED
        if audience == Audience.BAR:
            return bool(viewer.state and target.state and viewer.state.strip().lower() == target.state.strip().lower())
        if audience == Audience.GROUPS:
            from app.modules.groups.models import GroupMembership, MemberStatus

            mine = select(GroupMembership.group_id).where(
                GroupMembership.user_id == viewer.user_id, GroupMembership.status == MemberStatus.ACTIVE)
            shared = await self.session.scalar(
                select(GroupMembership.id).where(
                    GroupMembership.user_id == target.user_id, GroupMembership.status == MemberStatus.ACTIVE,
                    GroupMembership.group_id.in_(mine)).limit(1)
            )
            return shared is not None
        return False

    async def _with_relationship(self, people: list[NetworkIdentity]) -> list[tuple[NetworkIdentity, str | None, bool]]:
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

    async def home(self, limit: int = 5) -> dict:
        """The people-first home card: fraternity numbers, colleagues in my city and the newest members
        (people I am already connected with, or have asked, are left out of the suggestions)."""
        me = await self.ensure_my_identity()
        counts = await self.identities.counts(me.city, datetime.now(UTC) - timedelta(days=7))
        nearby = await self._visible(me, await self.identities.nearby(self.user_id, me.city, limit * 2)) if me.city else []
        nearby = nearby[:limit]
        recent = await self._visible(me, await self.identities.recent(self.user_id, limit * 2, exclude_ids={p.user_id for p in nearby}))
        recent = recent[:limit]
        def fresh(rows: list[tuple[NetworkIdentity, str | None, bool]]):
            return [(p, s, f) for p, s, f in rows if s is None]
        return {
            **counts, "city": me.city, "discoverable": me.discoverable,
            "nearby": fresh(await self._with_relationship(nearby)), "recent": fresh(await self._with_relationship(recent)),
        }

    # ── Blocking (22 Nov 2026) ──────────────────────────────────────
    async def block(self, target_id: uuid.UUID) -> None:
        if await self.identities.get(target_id) is None:
            raise NotFoundError("This person is not on the network.")
        await blocks.block(self.session, self.user_id, target_id)
        # A block ends any connection or follow between the two.
        existing = await self.connections.between(self.user_id, target_id)
        if existing is not None:
            await self.session.delete(existing)
        for a, b in ((self.user_id, target_id), (target_id, self.user_id)):
            follow = await self.session.scalar(select(Follow).where(Follow.follower_id == a, Follow.followee_id == b))
            if follow is not None:
                await self.session.delete(follow)
        await self.session.flush()

    async def unblock(self, target_id: uuid.UUID) -> bool:
        return await blocks.unblock(self.session, self.user_id, target_id)

    async def blocked_people(self) -> list[NetworkIdentity]:
        ids = await blocks.blocked_ids(self.session, self.user_id)
        if not ids:
            return []
        return list(await self.session.scalars(select(NetworkIdentity).where(NetworkIdentity.user_id.in_(ids)).order_by(NetworkIdentity.display_name)))

    async def is_blocked(self, target_id: uuid.UUID) -> bool:
        return target_id in await blocks.blocked_ids(self.session, self.user_id)
