"""Pydantic schemas for the professional network module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.network.models import (
    ConnectionStatus,
    PostType,
    PostVisibility,
    ReactionType,
)


# ─── Directory / identity ───────────────────────────────────────────
class IdentityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: uuid.UUID
    display_name: str
    headline: str | None
    avatar_url: str | None
    city: str | None
    is_verified: bool


class DirectoryPerson(IdentityRead):
    """A person in the directory with the viewer's relationship to them."""

    connection_status: str | None = None  # none | pending_out | pending_in | connected
    is_following: bool = False


class PublicProfile(DirectoryPerson):
    """A person's public profile (cross-tenant), with the viewer's relationship."""

    is_self: bool = False


# ─── Connections ────────────────────────────────────────────────────
class ConnectionRequestCreate(BaseModel):
    message: str | None = Field(default=None, max_length=300)


class ConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    requester_id: uuid.UUID
    addressee_id: uuid.UUID
    status: ConnectionStatus
    message: str | None
    created_at: datetime


class ConnectionWithPerson(BaseModel):
    connection: ConnectionRead
    person: IdentityRead | None = None


# ─── Posts / feed ───────────────────────────────────────────────────
class MentionRead(BaseModel):
    user_id: uuid.UUID
    name: str


class LinkPreviewRead(BaseModel):
    """Open Graph preview metadata resolved for a URL (feed 'unfurl')."""

    url: str
    title: str | None = None
    description: str | None = None
    image: str | None = None
    site_name: str | None = None


class PostCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    title: str | None = Field(default=None, max_length=300)
    post_type: PostType = PostType.TEXT
    visibility: PostVisibility = PostVisibility.PUBLIC
    hashtags: list[str] = Field(default_factory=list, max_length=15)
    mention_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)

    # Link preview the client resolved via GET /network/link-preview (optional).
    link_url: str | None = Field(default=None, max_length=1000)
    link_title: str | None = Field(default=None, max_length=500)
    link_description: str | None = None
    link_image: str | None = Field(default=None, max_length=1000)
    link_site_name: str | None = Field(default=None, max_length=200)


class ShareCreate(BaseModel):
    content: str = Field(default="", max_length=8000)


class PostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    author_headline: str | None
    author_avatar_url: str | None
    post_type: PostType
    title: str | None
    content: str
    visibility: PostVisibility
    hashtags: list[str]
    like_count: int
    comment_count: int
    share_count: int
    created_at: datetime

    # Link preview snapshot (present when the post carries an unfurled URL).
    link_url: str | None = None
    link_title: str | None = None
    link_description: str | None = None
    link_image: str | None = None
    link_site_name: str | None = None

    # Repost snapshot of the original (present when this post is a share).
    shared_from_id: uuid.UUID | None = None
    shared_author_name: str | None = None
    shared_author_avatar_url: str | None = None
    shared_content: str | None = None
    shared_created_at: datetime | None = None

    # People tagged in this post.
    mentions: list[MentionRead] = Field(default_factory=list)


class FeedItem(PostRead):
    """A feed post annotated with the viewer's own reaction and bookmark state."""

    my_reaction: ReactionType | None = None
    bookmarked: bool = False


# ─── Trending ───────────────────────────────────────────────────────
class TrendingTag(BaseModel):
    tag: str
    count: int


# ─── Reactions ──────────────────────────────────────────────────────
class ReactionCreate(BaseModel):
    reaction: ReactionType = ReactionType.LIKE


# ─── Comments ───────────────────────────────────────────────────────
class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=3000)
    parent_id: uuid.UUID | None = None


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    post_id: uuid.UUID
    parent_id: uuid.UUID | None
    author_id: uuid.UUID
    author_name: str
    author_avatar_url: str | None
    body: str
    created_at: datetime
