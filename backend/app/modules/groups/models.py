"""Groups / communities / firm-page domain models (Phase 2).

Like the professional network, these tables are a **global platform layer**:
groups span tenants, so they carry no ``tenant_id`` isolation and no RLS. A
firm-page group records its owning ``tenant_id`` for reference only. Member and
author display fields are denormalised snapshots so listings render without
cross-tenant identity joins.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import AuditedBase
from app.modules.network.models import PostImage  # noqa: F401  (relationship target)


class GroupType(StrEnum):
    COMMUNITY = "community"
    FIRM = "firm"


class GroupVisibility(StrEnum):
    PUBLIC = "public"      # anyone may join instantly
    PRIVATE = "private"    # joining requires admin approval


class MemberRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class MemberStatus(StrEnum):
    ACTIVE = "active"      # a full member
    PENDING = "pending"    # user requested to join a private group; awaiting approval
    INVITED = "invited"    # a manager invited this user; awaiting their acceptance


class Group(AuditedBase):
    __tablename__ = "groups"
    __table_args__ = (
        UniqueConstraint("slug", name="groups_slug"),
        UniqueConstraint("invite_code", name="uq_groups_invite_code"),
    )

    slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_type: Mapped[GroupType] = mapped_column(
        String(20), default=GroupType.COMMUNITY, nullable=False, index=True
    )
    visibility: Mapped[GroupVisibility] = mapped_column(
        String(20), default=GroupVisibility.PUBLIC, nullable=False
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    # Owning tenant for a firm page (informational only — no isolation applied).
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Invite link vidhisangh.com/join/<invite_code> (bar associations, law
    # colleges): anyone with it joins at once; an admin can reset it.
    invite_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    member_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    post_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    memberships: Mapped[list["GroupMembership"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    posts: Mapped[list["GroupPost"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class GroupMembership(AuditedBase):
    __tablename__ = "group_memberships"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="group_membership_unique"),
    )

    group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    # Denormalised member snapshot for cross-tenant member lists.
    member_name: Mapped[str] = mapped_column(String(200), nullable=False)
    member_headline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    member_avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role: Mapped[MemberRole] = mapped_column(
        String(20), default=MemberRole.MEMBER, nullable=False
    )
    status: Mapped[MemberStatus] = mapped_column(
        String(20), default=MemberStatus.ACTIVE, nullable=False, index=True
    )

    group: Mapped[Group] = relationship(back_populates="memberships")


class GroupPost(AuditedBase):
    __tablename__ = "group_posts"

    group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    author_name: Mapped[str] = mapped_column(String(200), nullable=False)
    author_avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Formatted body (server-cleaned HTML, as feed posts; migration 0075).
    content_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    group: Mapped[Group] = relationship(back_populates="posts")
    images: Mapped[list["PostImage"]] = relationship(
        "PostImage", lazy="selectin", order_by="PostImage.position",
        primaryjoin="GroupPost.id == foreign(PostImage.group_post_id)", viewonly=True,
    )
    likes: Mapped[list["GroupPostLike"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )
    comments: Mapped[list["GroupPostComment"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )


class GroupPostLike(AuditedBase):
    __tablename__ = "group_post_likes"
    __table_args__ = (
        UniqueConstraint("group_post_id", "user_id", name="group_post_like_unique"),
    )

    group_post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("group_posts.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)

    post: Mapped[GroupPost] = relationship(back_populates="likes")


class GroupPostComment(AuditedBase):
    __tablename__ = "group_post_comments"

    group_post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("group_posts.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    author_name: Mapped[str] = mapped_column(String(200), nullable=False)
    author_avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    post: Mapped[GroupPost] = relationship(back_populates="comments")
