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
    DateTime,
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
    __table_args__ = (
        UniqueConstraint("user_id", name="network_identities_user"),
        UniqueConstraint("public_handle", name="uq_network_identities_public_handle"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    # Home tenant (informational only — no isolation applied to this layer).
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    headline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Directory opt-in (audit P-10). New identities start hidden; the user opts in
    # via PATCH /network/me/visibility. Existing rows were grandfathered to true
    # by migration 0048. Connections, mentions and posts work regardless.
    discoverable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    # Public profile page at vidhisangh.com/in/<public_handle>/, open to search
    # engines: a separate, explicit opt-in (migration 0071), off by default and
    # only while the professional profile is public. Shows only the groups the
    # member set to "everyone"; never contact details.
    public_page: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    public_handle: Mapped[str | None] = mapped_column(String(60), nullable=True)
    public_page_consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    # Formatted body (allow-listed HTML, app/core/html_clean.py). `content`
    # always holds its plain text, for search, notifications and older apps.
    content_html: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    # Original posts use the audited base's UTC timestamptz. Keep the frozen
    # snapshot timezone-aware too; asyncpg rejects an aware source datetime
    # when the ORM bind is incorrectly declared as TIMESTAMP WITHOUT TIME ZONE.
    shared_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    reactions: Mapped[list["PostReaction"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )
    images: Mapped[list["PostImage"]] = relationship(
        back_populates="post", lazy="selectin", order_by="PostImage.position"
    )


class PostImage(AuditedBase):
    """A photo uploaded for a post (app/modules/network/media.py). Unattached
    until the post is published; served only once attached to a live post."""

    __tablename__ = "post_images"

    uploader_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    post_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Or attached to a group post (migration 0075); never both.
    group_post_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("group_posts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    post: Mapped["Post | None"] = relationship(back_populates="images")


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


class OfficialPost(AuditedBase):
    """What the official VidhiSangh account has posted, so nothing repeats.

    ``kind`` is section / judgment / news; ``ref`` the section ("bns:318"),
    judgment id or news item id.
    """

    __tablename__ = "official_posts"
    __table_args__ = (UniqueConstraint("kind", "ref", name="uq_official_posts_kind_ref"),)

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    ref: Mapped[str] = mapped_column(String(100), nullable=False)
    post_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
