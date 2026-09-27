"""Professional network domain models (Phase 2).

Unlike practice-management data (which is tenant-isolated by RLS), the
professional network is a **global platform layer** — advocates connect and
share across firms, exactly like LinkedIn. To render feeds and connection lists
without cross-tenant RLS joins, each user has a ``NetworkIdentity`` (a public
projection of their display identity), and content carries a denormalised author
snapshot. These tables are global (no ``tenant_id``, no RLS).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
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


class ConnectionStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class PostVisibility(StrEnum):
    PUBLIC = "public"
    CONNECTIONS = "connections"


class ReactionType(StrEnum):
    LIKE = "like"
    INSIGHTFUL = "insightful"
    CELEBRATE = "celebrate"
    SUPPORT = "support"
    CURIOUS = "curious"


class PostType(StrEnum):
    TEXT = "text"
    ARTICLE = "article"
    ANNOUNCEMENT = "announcement"


class NetworkIdentity(AuditedBase):
    """Public directory projection of a user — the cross-tenant identity used
    for discovery, feeds and connections. Upserted when a user registers or
    edits their profile."""

    __tablename__ = "network_identities"
    __table_args__ = (UniqueConstraint("user_id", name="network_identities_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    # Home tenant (informational only — no isolation applied to this layer).
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    headline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Connection(AuditedBase):
    """A mutual professional connection (request → accept)."""

    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint("requester_id", "addressee_id", name="connection_pair"),
    )

    requester_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    addressee_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    status: Mapped[ConnectionStatus] = mapped_column(
        String(20), default=ConnectionStatus.PENDING, nullable=False, index=True
    )
    message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Follow(AuditedBase):
    """A one-directional follow (no acceptance required)."""

    __tablename__ = "follows"
    __table_args__ = (
        UniqueConstraint("follower_id", "followee_id", name="follow_pair"),
    )

    follower_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    followee_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)


class Post(AuditedBase):
    __tablename__ = "posts"

    author_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    # Denormalised author snapshot (avoids cross-tenant identity joins).
    author_name: Mapped[str] = mapped_column(String(200), nullable=False)
    author_headline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    author_avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    post_type: Mapped[PostType] = mapped_column(
        String(20), default=PostType.TEXT, nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[PostVisibility] = mapped_column(
        String(20), default=PostVisibility.PUBLIC, nullable=False, index=True
    )
    hashtags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Link preview (Open Graph unfurl) — a snapshot captured when the post was
    # composed, so feeds render the card without re-fetching the URL.
    link_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    link_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    link_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_image: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    link_site_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    share_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Repost: a frozen snapshot of the original at share time (denormalised, so
    # feeds render reposts without joins — consistent with author snapshots).
    shared_from_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    shared_author_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    shared_author_avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    shared_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    shared_created_at: Mapped[datetime | None] = mapped_column(nullable=True)

    reactions: Mapped[list["PostReaction"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )


class PostReaction(AuditedBase):
    __tablename__ = "post_reactions"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="reaction_unique"),
    )

    post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    reaction: Mapped[ReactionType] = mapped_column(
        String(20), default=ReactionType.LIKE, nullable=False
    )

    post: Mapped[Post] = relationship(back_populates="reactions")


class PostMention(AuditedBase):
    """A user tagged (@mentioned) in a post. Carries a denormalised name so the
    post renders the mention without an identity join."""

    __tablename__ = "post_mentions"
    __table_args__ = (
        UniqueConstraint("post_id", "mentioned_user_id", name="mention_unique"),
    )

    post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    mentioned_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), index=True
    )
    mentioned_name: Mapped[str] = mapped_column(String(200), nullable=False)


class PostBookmark(AuditedBase):
    """A user's saved post (private to the user)."""

    __tablename__ = "post_bookmarks"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="bookmark_unique"),
    )

    post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)


class Comment(AuditedBase):
    __tablename__ = "post_comments"

    post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("post_comments.id", ondelete="CASCADE"), nullable=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    author_name: Mapped[str] = mapped_column(String(200), nullable=False)
    author_avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    post: Mapped[Post] = relationship(back_populates="comments")
