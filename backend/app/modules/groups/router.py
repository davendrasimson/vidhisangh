"""Groups / communities / firm-pages HTTP endpoints: discovery, membership,
moderation and community posts."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel

from app.core.deps import AuthSessionDep, CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.core.pagination import PageParams, page_params
from app.modules.groups.models import (
    Group,
    GroupMembership,
    GroupType,
    MemberRole,
    MemberStatus,
)
from app.modules.groups.schemas import (
    GroupCommentCreate,
    GroupCommentRead,
    GroupCreate,
    GroupPostCreate,
    GroupFeedItem,
    GroupPostRead,
    GroupPreview,
    GroupRead,
    GroupUpdate,
    InvitationRead,
    MemberRead,
    MemberRoleUpdate,
)
from app.modules.groups.service import GroupService

router = APIRouter(prefix="/groups", tags=["Groups & Communities"])

Pagination = Annotated[PageParams, Depends(page_params)]


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> GroupService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return GroupService(session, current.id, current.tenant_id)


def _to_read(group: Group, membership: GroupMembership | None) -> GroupRead:
    read = GroupRead.model_validate(group)
    if membership is not None:
        # ORM stores these as plain strings; coerce to the enum so serialization
        # matches the declared field type.
        read.my_role = MemberRole(membership.role)
        read.my_status = MemberStatus(membership.status)
    return read


# Guard convention (audit A-16): ``group:read`` to browse, ``group:create`` to
# found a group, ``group:update`` for moderation (the service additionally
# checks the caller's admin/owner membership), ``post:create``/``post:delete``
# to take part (join, post, like, comment). Guests hold only the read codes.


# ─── Discovery & lifecycle ──────────────────────────────────────────
@router.post(
    "",
    dependencies=[require_permission("group:create")],
    response_model=GroupRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a group or firm page",
)
async def create_group(
    data: GroupCreate, current: CurrentUserDep, session: TenantSessionDep
) -> GroupRead:
    group = await _svc(current, session).create_group(data)
    # The creator is the owner-member, so re-read to include their membership.
    return await _read_with_membership(current, session, group.id)


@router.get("", dependencies=[require_permission("group:read")], response_model=list[GroupRead], summary="Discover groups")
async def discover(
    page: Pagination,
    current: CurrentUserDep,
    session: TenantSessionDep,
    type_filter: Annotated[GroupType | None, Query(alias="type")] = None,
) -> list[GroupRead]:
    rows = await _svc(current, session).discover(page.limit, page.offset, type_filter)
    return [_to_read(g, m) for g, m in rows]


@router.get("/mine", dependencies=[require_permission("group:read")], response_model=list[GroupRead], summary="Groups I belong to")
async def my_groups(current: CurrentUserDep, session: TenantSessionDep) -> list[GroupRead]:
    rows = await _svc(current, session).my_groups()
    return [_to_read(g, m) for g, m in rows]


@router.get(
    "/mine/posts",
    dependencies=[require_permission("group:read")],
    response_model=list[GroupFeedItem],
    summary="The newest posts across the groups I belong to (home screen)",
)
async def latest_in_my_groups(
    current: CurrentUserDep,
    session: TenantSessionDep,
    limit: Annotated[int, Query(ge=1, le=20)] = 3,
) -> list[GroupFeedItem]:
    rows, liked = await _svc(current, session).latest_in_my_groups(limit)
    items: list[GroupFeedItem] = []
    for post, group in rows:
        base = GroupPostRead.model_validate(post)
        items.append(GroupFeedItem(**{**base.model_dump(), "liked": post.id in liked}, group_name=group.name, group_slug=group.slug))
    return items


@router.get(
    "/invitations",
    dependencies=[require_permission("group:read")],
    response_model=list[InvitationRead],
    summary="Group invitations I have received",
)
async def my_invitations(
    current: CurrentUserDep, session: TenantSessionDep
) -> list[InvitationRead]:
    rows = await _svc(current, session).my_invitations()
    return [
        InvitationRead(
            group_id=g.id,
            group_name=g.name,
            group_slug=g.slug,
            group_type=g.group_type,
            visibility=g.visibility,
            member_count=g.member_count,
            invited_at=m.created_at,
        )
        for m, g in rows
    ]


@router.get(
    "/{group_id}",
    dependencies=[require_permission("group:read")],
    response_model=GroupRead | GroupPreview,
    summary="Get a group (private groups show a reduced preview to non-members)",
)
async def get_group(
    group_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> GroupRead | GroupPreview:
    group, membership, full = await _svc(current, session).view_group(group_id)
    if not full:
        preview = GroupPreview.model_validate(group)
        if membership is not None:
            preview.my_status = MemberStatus(membership.status)
        return preview
    return _to_read(group, membership)


@router.patch("/{group_id}", dependencies=[require_permission("group:update")], response_model=GroupRead, summary="Update a group (admin)")
async def update_group(
    group_id: uuid.UUID,
    data: GroupUpdate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> GroupRead:
    await _svc(current, session).update_group(group_id, data)
    return await _read_with_membership(current, session, group_id)


@router.delete(
    "/{group_id}",
    dependencies=[require_permission("group:update")], status_code=status.HTTP_204_NO_CONTENT, summary="Delete a group (owner)"
)
async def delete_group(
    group_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).delete_group(group_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Membership ─────────────────────────────────────────────────────
@router.post("/{group_id}/join", dependencies=[require_permission("post:create")], response_model=MemberRead, summary="Join / request to join")
async def join_group(
    group_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> MemberRead:
    membership = await _svc(current, session).join(group_id)
    return MemberRead.model_validate(membership)


@router.post(
    "/{group_id}/leave",
    dependencies=[require_permission("post:create")], status_code=status.HTTP_204_NO_CONTENT, summary="Leave a group"
)
async def leave_group(
    group_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).leave(group_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{group_id}/members",
    dependencies=[require_permission("group:read")], response_model=list[MemberRead], summary="List active members"
)
async def list_members(
    group_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> list[MemberRead]:
    members = await _svc(current, session).list_members(group_id)
    return [MemberRead.model_validate(m) for m in members]


@router.get(
    "/{group_id}/requests",
    dependencies=[require_permission("group:update")],
    response_model=list[MemberRead],
    summary="Pending join requests (admin)",
)
async def pending_requests(
    group_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> list[MemberRead]:
    requests = await _svc(current, session).pending_requests(group_id)
    return [MemberRead.model_validate(m) for m in requests]


@router.post(
    "/{group_id}/members/{user_id}/approve",
    dependencies=[require_permission("group:update")],
    response_model=MemberRead,
    summary="Approve a join request (admin)",
)
async def approve_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> MemberRead:
    membership = await _svc(current, session).approve(group_id, user_id)
    return MemberRead.model_validate(membership)


@router.post(
    "/{group_id}/members/{user_id}/reject",
    dependencies=[require_permission("group:update")],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reject a join request (admin)",
)
async def reject_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> Response:
    await _svc(current, session).reject(group_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{group_id}/members/{user_id}/role",
    dependencies=[require_permission("group:update")],
    response_model=MemberRead,
    summary="Change a member's role (owner)",
)
async def set_member_role(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    data: MemberRoleUpdate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> MemberRead:
    membership = await _svc(current, session).set_role(group_id, user_id, data.role)
    return MemberRead.model_validate(membership)


@router.delete(
    "/{group_id}/members/{user_id}",
    dependencies=[require_permission("group:update")],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member (admin)",
)
async def remove_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> Response:
    await _svc(current, session).remove_member(group_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Invitations ────────────────────────────────────────────────────
@router.post(
    "/{group_id}/invite/{user_id}",
    dependencies=[require_permission("group:update")],
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a user to the group (admin)",
)
async def invite_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> MemberRead:
    membership = await _svc(current, session).invite(group_id, user_id)
    return MemberRead.model_validate(membership)


@router.post(
    "/{group_id}/invitation/accept",
    dependencies=[require_permission("post:create")],
    response_model=GroupRead,
    summary="Accept an invitation to a group",
)
async def accept_invitation(
    group_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> GroupRead:
    await _svc(current, session).accept_invite(group_id)
    return await _read_with_membership(current, session, group_id)


@router.post(
    "/{group_id}/invitation/decline",
    dependencies=[require_permission("post:create")],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Decline an invitation to a group",
)
async def decline_invitation(
    group_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).decline_invite(group_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Group posts ────────────────────────────────────────────────────
@router.get(
    "/{group_id}/posts",
    dependencies=[require_permission("group:read")],
    response_model=list[GroupPostRead],
    summary="The group's community feed (members)",
)
async def list_posts(
    group_id: uuid.UUID,
    page: Pagination,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> list[GroupPostRead]:
    posts, liked = await _svc(current, session).list_posts(group_id, page.limit, page.offset)
    items: list[GroupPostRead] = []
    for post in posts:
        item = GroupPostRead.model_validate(post)
        item.liked = post.id in liked
        items.append(item)
    return items


@router.post(
    "/{group_id}/posts",
    dependencies=[require_permission("post:create")],
    response_model=GroupPostRead,
    status_code=status.HTTP_201_CREATED,
    summary="Post to a group (members)",
)
async def create_post(
    group_id: uuid.UUID,
    data: GroupPostCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> GroupPostRead:
    post = await _svc(current, session).create_post(group_id, data)
    return GroupPostRead.model_validate(post)


@router.delete(
    "/posts/{post_id}",
    dependencies=[require_permission("post:delete")],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a group post (author or admin)",
)
async def delete_post(
    post_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).delete_post(post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/posts/{post_id}/like",
    dependencies=[require_permission("post:create")], status_code=status.HTTP_204_NO_CONTENT, summary="Like a post"
)
async def like_post(
    post_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).like_post(post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/posts/{post_id}/like",
    dependencies=[require_permission("post:create")],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove your like",
)
async def unlike_post(
    post_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).unlike_post(post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Group post comments ────────────────────────────────────────────
@router.post(
    "/posts/{post_id}/comments",
    dependencies=[require_permission("post:create")],
    response_model=GroupCommentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Comment on a group post (members)",
)
async def add_comment(
    post_id: uuid.UUID,
    data: GroupCommentCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> GroupCommentRead:
    comment = await _svc(current, session).add_comment(post_id, data)
    return GroupCommentRead.model_validate(comment)


@router.get(
    "/posts/{post_id}/comments",
    dependencies=[require_permission("group:read")],
    response_model=list[GroupCommentRead],
    summary="List comments on a group post (members)",
)
async def list_comments(
    post_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> list[GroupCommentRead]:
    comments = await _svc(current, session).list_comments(post_id)
    return [GroupCommentRead.model_validate(c) for c in comments]


@router.delete(
    "/comments/{comment_id}",
    dependencies=[require_permission("post:delete")],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment (author or admin)",
)
async def delete_comment(
    comment_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).delete_comment(comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _read_with_membership(
    current: CurrentUserDep, session: TenantSessionDep, group_id: uuid.UUID
) -> GroupRead:
    group, membership = await _svc(current, session).get_group(group_id)
    return _to_read(group, membership)


# ─── Invite links (vidhisangh.com/join/<code>) ──────────────────────
class InviteLink(BaseModel):
    code: str
    url: str


class InvitePreview(BaseModel):
    group_id: uuid.UUID
    name: str
    description: str | None
    member_count: int
    is_verified: bool


def _invite(group) -> InviteLink:  # noqa: ANN001
    return InviteLink(code=group.invite_code, url=f"https://vidhisangh.com/join/{group.invite_code}")


@router.post("/{group_id}/invite-link", response_model=InviteLink, summary="The group's invite link (admins)")
async def get_invite_link(group_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep,
                          reset: bool = False) -> InviteLink:
    return _invite(await _svc(current, session).invite_link(group_id, reset=reset))


@router.get("/invite/{code}", response_model=InvitePreview, summary="What an invite link leads to (no sign-in)")
async def preview_invite(code: str, session: AuthSessionDep) -> InvitePreview:
    from sqlalchemy import select

    from app.core.exceptions import NotFoundError
    from app.modules.groups.models import Group

    group = await session.scalar(select(Group).where(Group.invite_code == code, Group.deleted_at.is_(None)))
    if group is None:
        raise NotFoundError("This invite link is not valid any more.")
    return InvitePreview(group_id=group.id, name=group.name, description=group.description,
                         member_count=group.member_count, is_verified=group.is_verified)


@router.post("/invite/{code}/join", dependencies=[require_permission("post:create")], response_model=InvitePreview,
             summary="Join through an invite link")
async def join_by_invite(code: str, current: CurrentUserDep, session: TenantSessionDep) -> InvitePreview:
    group, _ = await _svc(current, session).join_by_code(code)
    return InvitePreview(group_id=group.id, name=group.name, description=group.description,
                         member_count=group.member_count, is_verified=group.is_verified)
