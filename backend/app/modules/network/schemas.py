"""Pydantic schemas for the professional network module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class MyIdentityRead(IdentityRead):
    """The caller's own identity, including the directory opt-in flag."""

    discoverable: bool = False


class VisibilityUpdate(BaseModel):
    """Directory opt-in/out (audit P-10)."""

    discoverable: bool


class PublicPageUpdate(BaseModel):
    """Public profile page on the open web (opt-in). ``handle``: 3-40 of a-z, 0-9 and hyphens."""

    enabled: bool
    handle: str | None = Field(default=None, min_length=3, max_length=40, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class PublicPageRead(BaseModel):
    enabled: bool
    handle: str | None
    url: str | None


class DirectoryPerson(IdentityRead):
    """A person in the directory with the viewer's relationship to them."""

    connection_status: str | None = None  # none | pending_out | pending_in | connected
    is_following: bool = False


class PublicProfile(DirectoryPerson):
    """A person's public profile (cross-tenant), with the viewer's relationship."""

    is_self: bool = False


class HomeNetworkRead(BaseModel):
    """The home screen's people card: fraternity numbers and colleagues to connect with."""

    members: int
    in_city: int
    joined_7d: int
    city: str | None
    discoverable: bool
    nearby: list[DirectoryPerson]
    recent: list[DirectoryPerson]


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


class IncomingRequestRead(ConnectionRead):
    """A pending request with who sent it (home screen, People page)."""

    requester: IdentityRead | None = None


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
    # Plain text. With `content_html` the server derives it from the HTML instead.
    content: str = Field(default="", max_length=8000)
    # Formatted body from the rich composer; cleaned to an allow-list on the server.
    content_html: str | None = Field(default=None, max_length=60000)
    # Photos uploaded first via POST /network/post-images (at most 4).
    image_ids: list[uuid.UUID] = Field(default_factory=list, max_length=4)
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

    @model_validator(mode="after")
    def _something_to_post(self) -> PostCreate:
        if not (self.content.strip() or (self.content_html or "").strip() or self.image_ids):
            raise ValueError("Write something or add a photo.")
        return self


class PostImageRead(BaseModel):
    """The image is served at GET /network/post-images/{id}."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    width: int
    height: int


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
    content_html: str | None = None
    images: list[PostImageRead] = Field(default_factory=list)
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
    # A repost shows the original's photos (while the original exists).
    shared_images: list[PostImageRead] = Field(default_factory=list)


# ─── Trending ───────────────────────────────────────────────────────
class TrendingTag(BaseModel):
    tag: str
    count: int


# ─── Reactions ──────────────────────────────────────────────────────
class ReactionCreate(BaseModel):
    reaction: ReactionType = ReactionType.LIKE


class PostReportCreate(BaseModel):
    category: str = Field(
        pattern="^(spam|harassment|hate_or_abuse|misinformation|privacy|impersonation|other)$"
    )
    reason: str = Field(min_length=10, max_length=2000)


class PostReportRead(BaseModel):
    ticket_number: str
    status: str


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


class DailyCard(BaseModel):
    """One official daily post, as a card (home screen)."""

    kind: str  # section | judgment | news
    ref: str   # "bns:318", a judgment id, or a news item id
    post_id: uuid.UUID
    title: str
    description: str | None = None
    url: str | None = None
    site: str | None = None
    posted_at: datetime


class DailyRead(BaseModel):
    section: DailyCard | None = None
    judgment: DailyCard | None = None
    news: list[DailyCard] = []

