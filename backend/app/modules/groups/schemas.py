"""Pydantic schemas for the groups / communities / firm-pages module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.network.schemas import PostImageRead
from app.modules.groups.models import (
    GroupType,
    GroupVisibility,
    MemberRole,
    MemberStatus,
)


# ─── Groups ─────────────────────────────────────────────────────────
class GroupCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    group_type: GroupType = GroupType.COMMUNITY
    visibility: GroupVisibility = GroupVisibility.PUBLIC
    slug: str | None = Field(
        default=None, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    avatar_url: str | None = Field(default=None, max_length=500)
    cover_url: str | None = Field(default=None, max_length=500)


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    visibility: GroupVisibility | None = None
    avatar_url: str | None = Field(default=None, max_length=500)
    cover_url: str | None = Field(default=None, max_length=500)


class GroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    group_type: GroupType
    visibility: GroupVisibility
    avatar_url: str | None
    cover_url: str | None
    owner_id: uuid.UUID
    tenant_id: uuid.UUID | None
    is_verified: bool
    member_count: int
    post_count: int
    created_at: datetime

    # Viewer's relationship to the group (annotated by the service).
    my_role: MemberRole | None = None
    my_status: MemberStatus | None = None


class GroupPreview(BaseModel):
    """Reduced projection of a *private* group for non-members (audit A-17):
    enough to decide whether to request to join, nothing else."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    slug: str
    name: str
    group_type: GroupType
    visibility: GroupVisibility
    is_verified: bool
    member_count: int
    my_status: MemberStatus | None = None


# ─── Members ────────────────────────────────────────────────────────
class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    group_id: uuid.UUID
    user_id: uuid.UUID
    member_name: str
    member_headline: str | None
    member_avatar_url: str | None
    role: MemberRole
    status: MemberStatus
    created_at: datetime


class MemberRoleUpdate(BaseModel):
    role: MemberRole = Field(description="Target role — admin or member (not owner).")


class InvitationRead(BaseModel):
    """An invitation the current user has received, with its group summary."""

    group_id: uuid.UUID
    group_name: str
    group_slug: str
    group_type: GroupType
    visibility: GroupVisibility
    member_count: int
    invited_at: datetime


# ─── Group posts ────────────────────────────────────────────────────
class GroupPostCreate(BaseModel):
    # Plain text, or formatted HTML (cleaned on the server; the text is derived
    # from it), with up to 4 photos uploaded first via POST /network/post-images.
    content: str = Field(default="", max_length=8000)
    content_html: str | None = Field(default=None, max_length=60000)
    image_ids: list[uuid.UUID] = Field(default_factory=list, max_length=4)


class GroupPostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    group_id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    author_avatar_url: str | None
    content: str
    content_html: str | None = None
    images: list[PostImageRead] = Field(default_factory=list)
    like_count: int
    comment_count: int
    created_at: datetime

    # Whether the viewer has liked this post (annotated by the service).
    liked: bool = False


# ─── Group post comments ────────────────────────────────────────────
class GroupCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=3000)


class GroupCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    group_post_id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    author_avatar_url: str | None
    body: str
    created_at: datetime
