"""Groups / communities / firm-pages service — business logic.

Author and member display data is denormalised from the acting user's own
(tenant-readable) user + profile records onto the global group tables, so
cross-tenant member lists and community feeds render without RLS joins.
"""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.network.blocks import hidden_user_ids
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.modules.groups.models import (
    Group,
    GroupMembership,
    GroupPost,
    GroupPostComment,
    GroupPostLike,
    GroupType,
    GroupVisibility,
    MemberRole,
    MemberStatus,
)
from app.modules.groups.repository import (
    GroupPostCommentRepository,
    GroupPostLikeRepository,
    GroupPostRepository,
    GroupRepository,
    MembershipRepository,
)
from app.modules.groups.schemas import (
    GroupCommentCreate,
    GroupCreate,
    GroupPostCreate,
    GroupUpdate,
)
from app.modules.identity.repository import UserRepository
from app.modules.network.repository import IdentityRepository
from app.modules.notifications.models import NotificationType
from app.modules.notifications.service import create_notification
from app.modules.profile.repository import ProfileRepository

_MANAGER_ROLES = (MemberRole.OWNER, MemberRole.ADMIN)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "group"


class GroupService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.groups = GroupRepository(session)
        self.members = MembershipRepository(session)
        self.posts = GroupPostRepository(session)
        self.likes = GroupPostLikeRepository(session)
        self.comments = GroupPostCommentRepository(session)

    # ── Snapshot helper ─────────────────────────────────────────────
    async def _my_snapshot(self) -> tuple[str, str | None, str | None]:
        """The acting user's (name, headline, avatar) for denormalised rows."""
        user = await UserRepository(self.session).get_by_id(self.user_id)
        if user is None:
            raise NotFoundError("User not found.")
        profile = await ProfileRepository(self.session).get_by_user(self.user_id)
        name = user.display_name or user.full_name
        headline = profile.headline if profile else None
        return name, headline, user.avatar_url

    # ── Authorisation helpers ───────────────────────────────────────
    async def _get_group(self, group_id: uuid.UUID) -> Group:
        group = await self.groups.get(group_id)
        if group is None:
            raise NotFoundError("Group not found.")
        return group

    async def _require_active_member(self, group_id: uuid.UUID) -> GroupMembership:
        membership = await self.members.get(group_id, self.user_id)
        if membership is None or membership.status != MemberStatus.ACTIVE:
            raise PermissionDeniedError("You must be a member of this group.")
        return membership

    async def _require_manager(self, group_id: uuid.UUID) -> GroupMembership:
        membership = await self._require_active_member(group_id)
        if membership.role not in _MANAGER_ROLES:
            raise PermissionDeniedError("This action requires group admin rights.")
        return membership

    # ── Groups ──────────────────────────────────────────────────────
    async def create_group(self, data: GroupCreate) -> Group:
        base_slug = data.slug or _slugify(data.name)
        slug = base_slug
        if await self.groups.get_by_slug(slug) is not None:
            if data.slug is not None:
                raise ConflictError("That group URL is already taken.")
            slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"

        name, headline, avatar = await self._my_snapshot()
        group = Group(
            slug=slug,
            name=data.name,
            description=data.description,
            group_type=data.group_type,
            visibility=data.visibility,
            avatar_url=data.avatar_url,
            cover_url=data.cover_url,
            owner_id=self.user_id,
            # A firm page records its owning tenant; communities are tenant-agnostic.
            tenant_id=self.tenant_id if data.group_type == GroupType.FIRM else None,
            member_count=1,
        )
        self.groups.add(group)
        await self.session.flush()

        self.members.add(
            GroupMembership(
                group_id=group.id,
                user_id=self.user_id,
                member_name=name,
                member_headline=headline,
                member_avatar_url=avatar,
                role=MemberRole.OWNER,
                status=MemberStatus.ACTIVE,
            )
        )
        await self.session.flush()
        return group

    async def discover(
        self, limit: int, offset: int, group_type: GroupType | None = None
    ) -> list[tuple[Group, GroupMembership | None]]:
        groups = await self.groups.discover(limit, offset, group_type)
        mine = await self.members.for_user_in_groups(self.user_id, [g.id for g in groups])
        return [(g, mine.get(g.id)) for g in groups]

    async def my_groups(self) -> list[tuple[Group, GroupMembership | None]]:
        memberships = await self.members.for_user(self.user_id, MemberStatus.ACTIVE)
        by_group = {m.group_id: m for m in memberships}
        groups = await self.groups.for_member(list(by_group.keys()))
        return [(g, by_group.get(g.id)) for g in groups]

    async def get_group(self, group_id: uuid.UUID) -> tuple[Group, GroupMembership | None]:
        group = await self._get_group(group_id)
        membership = await self.members.get(group_id, self.user_id)
        return group, membership

    async def view_group(self, group_id: uuid.UUID) -> tuple[Group, GroupMembership | None, bool]:
        """``(group, membership, full)`` — ``full`` is False when the viewer is
        not an active member of a private group, in which case the router
        returns only the reduced :class:`GroupPreview` projection."""
        group, membership = await self.get_group(group_id)
        full = group.visibility == GroupVisibility.PUBLIC or (
            membership is not None and membership.status == MemberStatus.ACTIVE
        )
        return group, membership, full

    async def update_group(self, group_id: uuid.UUID, data: GroupUpdate) -> Group:
        group = await self._get_group(group_id)
        await self._require_manager(group_id)
        fields = data.model_dump(exclude_unset=True)
        for key, value in fields.items():
            setattr(group, key, value)
        return group

    async def delete_group(self, group_id: uuid.UUID) -> None:
        group = await self._get_group(group_id)
        if group.owner_id != self.user_id:
            raise PermissionDeniedError("Only the group owner can delete it.")
        group.deleted_at = datetime.now(UTC)

    # ── Membership ──────────────────────────────────────────────────
    async def join(self, group_id: uuid.UUID) -> GroupMembership:
        group = await self._get_group(group_id)
        existing = await self.members.get(group_id, self.user_id)
        if existing is not None:
            if existing.status == MemberStatus.ACTIVE:
                raise ConflictError("You are already a member.")
            if existing.status == MemberStatus.INVITED:
                raise ConflictError(
                    "You have a pending invitation to this group — accept it instead."
                )
            raise ConflictError("Your join request is pending approval.")

        name, headline, avatar = await self._my_snapshot()
        status = (
            MemberStatus.ACTIVE
            if group.visibility == GroupVisibility.PUBLIC
            else MemberStatus.PENDING
        )
        membership = GroupMembership(
            group_id=group_id,
            user_id=self.user_id,
            member_name=name,
            member_headline=headline,
            member_avatar_url=avatar,
            role=MemberRole.MEMBER,
            status=status,
        )
        self.members.add(membership)
        if status == MemberStatus.ACTIVE:
            group.member_count += 1
        await self.session.flush()
        return membership

    async def leave(self, group_id: uuid.UUID) -> None:
        group = await self._get_group(group_id)
        membership = await self.members.get(group_id, self.user_id)
        if membership is None:
            return
        if membership.role == MemberRole.OWNER:
            raise ValidationError(
                "The owner cannot leave the group. Transfer ownership or delete it."
            )
        if membership.status == MemberStatus.ACTIVE:
            group.member_count = max(0, group.member_count - 1)
        await self.members.delete(membership)

    async def list_members(self, group_id: uuid.UUID) -> list[GroupMembership]:
        await self._require_active_member(group_id)
        return await self.members.list_for_group(group_id, MemberStatus.ACTIVE)

    async def pending_requests(self, group_id: uuid.UUID) -> list[GroupMembership]:
        await self._require_manager(group_id)
        return await self.members.list_for_group(group_id, MemberStatus.PENDING)

    async def approve(self, group_id: uuid.UUID, user_id: uuid.UUID) -> GroupMembership:
        group = await self._get_group(group_id)
        await self._require_manager(group_id)
        membership = await self.members.get(group_id, user_id)
        if membership is None or membership.status != MemberStatus.PENDING:
            raise NotFoundError("No pending request from this user.")
        membership.status = MemberStatus.ACTIVE
        group.member_count += 1
        return membership

    async def reject(self, group_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self._require_manager(group_id)
        membership = await self.members.get(group_id, user_id)
        if membership is None or membership.status != MemberStatus.PENDING:
            raise NotFoundError("No pending request from this user.")
        await self.members.delete(membership)

    async def set_role(
        self, group_id: uuid.UUID, user_id: uuid.UUID, role: MemberRole
    ) -> GroupMembership:
        group = await self._get_group(group_id)
        if group.owner_id != self.user_id:
            raise PermissionDeniedError("Only the owner can change member roles.")
        if role == MemberRole.OWNER:
            raise ValidationError("Ownership cannot be assigned via role change.")
        if user_id == self.user_id:
            raise ValidationError("You cannot change your own role.")
        membership = await self.members.get(group_id, user_id)
        if membership is None or membership.status != MemberStatus.ACTIVE:
            raise NotFoundError("Active member not found.")
        membership.role = role
        return membership

    async def remove_member(self, group_id: uuid.UUID, user_id: uuid.UUID) -> None:
        group = await self._get_group(group_id)
        manager = await self._require_manager(group_id)
        membership = await self.members.get(group_id, user_id)
        if membership is None:
            raise NotFoundError("Member not found.")
        if membership.role == MemberRole.OWNER:
            raise ValidationError("The owner cannot be removed.")
        # Admins may remove members, but only the owner may remove another admin.
        if membership.role == MemberRole.ADMIN and manager.role != MemberRole.OWNER:
            raise PermissionDeniedError("Only the owner can remove an admin.")
        if membership.status == MemberStatus.ACTIVE:
            group.member_count = max(0, group.member_count - 1)
        await self.members.delete(membership)

    # ── Invitations ─────────────────────────────────────────────────
    async def invite(self, group_id: uuid.UUID, target_user_id: uuid.UUID) -> GroupMembership:
        group = await self._get_group(group_id)
        await self._require_manager(group_id)
        if target_user_id == self.user_id:
            raise ValidationError("You are already a member of this group.")
        if await self.members.get(group_id, target_user_id) is not None:
            raise ConflictError("That person already has a membership or invitation.")
        # Snapshot the invitee from the global directory (cross-tenant safe).
        identities = IdentityRepository(self.session)
        identity = await identities.get(target_user_id)
        if identity is None:
            raise NotFoundError("That user is not discoverable on the network.")
        membership = GroupMembership(
            group_id=group_id,
            user_id=target_user_id,
            member_name=identity.display_name,
            member_headline=identity.headline,
            member_avatar_url=identity.avatar_url,
            role=MemberRole.MEMBER,
            status=MemberStatus.INVITED,
        )
        self.members.add(membership)
        me = await identities.get(self.user_id)
        actor_name = me.display_name if me else "A group admin"
        await create_notification(
            self.session,
            user_id=target_user_id,
            type=NotificationType.GROUP_INVITE,
            actor_id=self.user_id,
            actor_name=actor_name,
            message=f"{actor_name} invited you to {group.name}",
            link="/app/groups",
        )
        await self.session.flush()
        return membership

    async def my_invitations(self) -> list[tuple[GroupMembership, Group]]:
        invites = await self.members.for_user(self.user_id, MemberStatus.INVITED)
        groups = await self.groups.for_member([m.group_id for m in invites])
        by_id = {g.id: g for g in groups}
        return [(m, by_id[m.group_id]) for m in invites if m.group_id in by_id]

    # ── Invite links (vidhisangh.com/join/<code>) ──────────────────
    async def invite_link(self, group_id: uuid.UUID, *, reset: bool = False) -> Group:
        """The group's invite code, created on first use; ``reset`` replaces it
        (the old link stops working). Group admins only."""
        group = await self._get_group(group_id)
        await self._require_manager(group_id)
        if reset or not group.invite_code:
            group.invite_code = secrets.token_urlsafe(8).replace("-", "x").replace("_", "y")
            await self.session.flush()
        return group

    async def join_by_code(self, code: str) -> tuple[Group, GroupMembership]:
        """Join through an invite link: at once, even for a private group (an
        admin shared the link). Idempotent for members."""
        group = await self.groups.get_by_invite_code(code)
        if group is None:
            raise NotFoundError("This invite link is not valid any more.")
        membership = await self.members.get(group.id, self.user_id)
        if membership is not None:
            if membership.status != MemberStatus.ACTIVE:
                membership.status = MemberStatus.ACTIVE
                group.member_count += 1
                await self.session.flush()
            return group, membership
        name, headline, avatar = await self._my_snapshot()
        membership = GroupMembership(group_id=group.id, user_id=self.user_id, member_name=name,
                                     member_headline=headline, member_avatar_url=avatar,
                                     role=MemberRole.MEMBER, status=MemberStatus.ACTIVE)
        self.members.add(membership)
        group.member_count += 1
        await self.session.flush()
        return group, membership

    async def accept_invite(self, group_id: uuid.UUID) -> GroupMembership:
        group = await self._get_group(group_id)
        membership = await self.members.get(group_id, self.user_id)
        if membership is None or membership.status != MemberStatus.INVITED:
            raise NotFoundError("No pending invitation for this group.")
        membership.status = MemberStatus.ACTIVE
        group.member_count += 1
        return membership

    async def decline_invite(self, group_id: uuid.UUID) -> None:
        membership = await self.members.get(group_id, self.user_id)
        if membership is None or membership.status != MemberStatus.INVITED:
            return
        await self.members.delete(membership)

    # ── Group posts ─────────────────────────────────────────────────
    async def create_post(self, group_id: uuid.UUID, data: GroupPostCreate) -> GroupPost:
        group = await self._get_group(group_id)
        await self._require_active_member(group_id)
        name, _headline, avatar = await self._my_snapshot()
        content, content_html = data.content.strip(), None
        if data.content_html:
            from app.core.html_clean import clean_html, html_to_text
            content_html = clean_html(data.content_html)
            content = html_to_text(content_html)
        if len(content) > 8000:
            raise ValidationError("A post can be at most 8,000 characters.")
        images = await self._claim_images(data.image_ids)
        if not content and not images:
            raise ValidationError("Write something or add a photo.")
        post = GroupPost(
            group_id=group_id,
            author_id=self.user_id,
            author_name=name,
            author_avatar_url=avatar,
            content=content,
            content_html=content_html,
        )
        self.posts.add(post)
        group.post_count += 1
        await self.session.flush()
        for image in images:
            image.group_post_id = post.id
        await self.session.flush()
        await self.session.refresh(post, ["images"])
        return post

    async def _claim_images(self, image_ids: list[uuid.UUID]) -> list:
        """The caller's own photos not yet attached to any post, in the order given."""
        from app.modules.network.models import PostImage

        ids = list(dict.fromkeys(image_ids))
        if not ids:
            return []
        rows = {img.id: img for img in await self.session.scalars(select(PostImage).where(
            PostImage.id.in_(ids), PostImage.uploader_id == self.user_id, PostImage.post_id.is_(None),
            PostImage.group_post_id.is_(None), PostImage.deleted_at.is_(None),
        ))}
        if len(rows) != len(ids):
            raise ValidationError("One of the photos is no longer available. Remove it and add it again.")
        for position, image_id in enumerate(ids):
            rows[image_id].position = position
        return [rows[i] for i in ids]

    async def list_posts(
        self, group_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[GroupPost], set[uuid.UUID]]:
        await self._require_active_member(group_id)
        hidden = await hidden_user_ids(self.session, self.user_id)
        posts = [p for p in await self.posts.list_for_group(group_id, limit, offset) if p.author_id not in hidden]
        liked = await self.likes.liked_post_ids(self.user_id, [p.id for p in posts])
        return posts, liked

    async def latest_in_my_groups(self, limit: int) -> tuple[list[tuple[GroupPost, Group]], set[uuid.UUID]]:
        """The newest posts across the groups the member is active in, with their groups."""
        groups = {g.id: g for g, _ in await self.my_groups()}
        posts = await self.posts.latest_in_groups(list(groups.keys()), limit)
        liked = await self.likes.liked_post_ids(self.user_id, [p.id for p in posts])
        return [(p, groups[p.group_id]) for p in posts], liked

    async def delete_post(self, post_id: uuid.UUID) -> None:
        post = await self.posts.get(post_id)
        if post is None:
            raise NotFoundError("Post not found.")
        if post.author_id != self.user_id:
            # Non-authors need manage rights on the post's group.
            await self._require_manager(post.group_id)
        post.deleted_at = datetime.now(UTC)
        group = await self.groups.get(post.group_id)
        if group is not None:
            group.post_count = max(0, group.post_count - 1)

    async def like_post(self, post_id: uuid.UUID) -> None:
        post = await self.posts.get(post_id)
        if post is None:
            raise NotFoundError("Post not found.")
        await self._require_active_member(post.group_id)
        if await self.likes.get(post_id, self.user_id) is not None:
            return
        self.likes.add(GroupPostLike(group_post_id=post_id, user_id=self.user_id))
        post.like_count += 1

    async def unlike_post(self, post_id: uuid.UUID) -> None:
        post = await self.posts.get(post_id)
        if post is None:
            raise NotFoundError("Post not found.")
        await self._require_active_member(post.group_id)
        existing = await self.likes.get(post_id, self.user_id)
        if existing is None:
            return
        await self.likes.delete(existing)
        post.like_count = max(0, post.like_count - 1)

    # ── Comments ────────────────────────────────────────────────────
    async def add_comment(
        self, post_id: uuid.UUID, data: GroupCommentCreate
    ) -> GroupPostComment:
        post = await self.posts.get(post_id)
        if post is None:
            raise NotFoundError("Post not found.")
        await self._require_active_member(post.group_id)
        name, _headline, avatar = await self._my_snapshot()
        comment = GroupPostComment(
            group_post_id=post_id,
            author_id=self.user_id,
            author_name=name,
            author_avatar_url=avatar,
            body=data.body,
        )
        self.comments.add(comment)
        post.comment_count += 1
        await self.session.flush()
        return comment

    async def list_comments(self, post_id: uuid.UUID) -> list[GroupPostComment]:
        post = await self.posts.get(post_id)
        if post is None:
            raise NotFoundError("Post not found.")
        await self._require_active_member(post.group_id)
        hidden = await hidden_user_ids(self.session, self.user_id)
        return [c for c in await self.comments.list_for_post(post_id) if c.author_id not in hidden]

    async def delete_comment(self, comment_id: uuid.UUID) -> None:
        comment = await self.comments.get(comment_id)
        if comment is None:
            raise NotFoundError("Comment not found.")
        post = await self.posts.get(comment.group_post_id)
        if comment.author_id != self.user_id:
            # Non-authors need manage rights on the post's group.
            if post is None:
                raise PermissionDeniedError("You can only delete your own comments.")
            await self._require_manager(post.group_id)
        comment.deleted_at = datetime.now(UTC)
        if post is not None:
            post.comment_count = max(0, post.comment_count - 1)

    async def post_for_report(self, post_id: uuid.UUID) -> GroupPost:
        post = await self.posts.get(post_id)
        if post is None:
            raise NotFoundError("Post not found.")
        await self._require_active_member(post.group_id)
        if post.author_id == self.user_id:
            raise ValidationError("You cannot report your own post.")
        return post
