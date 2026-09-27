"""Professional network HTTP endpoints: feed, posts, reactions, comments,
connections, follows and the people directory."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.core.link_preview import fetch_link_preview
from app.core.pagination import PageParams, page_params
from app.modules.network.models import ConnectionStatus, ReactionType
from app.modules.network.schemas import (
    CommentCreate,
    CommentRead,
    ConnectionRead,
    ConnectionRequestCreate,
    DirectoryPerson,
    FeedItem,
    IdentityRead,
    LinkPreviewRead,
    MentionRead,
    MyIdentityRead,
    PostCreate,
    PostRead,
    PublicProfile,
    ReactionCreate,
    ShareCreate,
    TrendingTag,
    VisibilityUpdate,
)
from app.modules.network.service import NetworkService

router = APIRouter(prefix="/network", tags=["Professional Network"])

Pagination = Annotated[PageParams, Depends(page_params)]


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> NetworkService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return NetworkService(session, current.id, current.tenant_id)


def _mention_reads(mentions) -> list[MentionRead]:  # noqa: ANN001
    return [
        MentionRead(user_id=m.mentioned_user_id, name=m.mentioned_name) for m in mentions
    ]


def _feed_items(posts, my_reactions, my_bookmarks, mentions_map) -> list[FeedItem]:  # noqa: ANN001
    items: list[FeedItem] = []
    for post in posts:
        item = FeedItem.model_validate(post)
        reaction = my_reactions.get(post.id)
        item.my_reaction = ReactionType(reaction.reaction) if reaction else None
        item.bookmarked = post.id in my_bookmarks
        item.mentions = _mention_reads(mentions_map.get(post.id, []))
        items.append(item)
    return items


# ─── Link preview (unfurl) ──────────────────────────────────────────
try:  # per-user bucket published by core.ratelimit (audit A-4)
    from app.core.ratelimit import link_preview_rate_limit as _link_preview_rate_limit
except ImportError:  # pragma: no cover - only if the limiter is renamed
    async def _link_preview_rate_limit() -> None:  # type: ignore[misc]
        return None

@router.get(
    "/link-preview",
    dependencies=[require_permission("post:create")],
    response_model=LinkPreviewRead,
    summary="Resolve a URL's Open Graph preview",
)
async def link_preview(
    current: CurrentUserDep,
    url: Annotated[str, Query(min_length=7, max_length=1000)],
    _: Annotated[None, Depends(_link_preview_rate_limit)],
) -> LinkPreviewRead:
    # Requires post:create (only composers need unfurls) so the endpoint is not a
    # general-purpose fetch proxy; the fetcher pins IPs and re-checks each redirect.
    preview = await fetch_link_preview(url)
    if preview is None or preview.is_empty():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No preview available for this URL."
        )
    return LinkPreviewRead(
        url=preview.url,
        title=preview.title,
        description=preview.description,
        image=preview.image,
        site_name=preview.site_name,
    )


# ─── Feed & posts ───────────────────────────────────────────────────
@router.get("/feed", dependencies=[require_permission("post:read")], response_model=list[FeedItem], summary="Personalised feed")
async def get_feed(
    page: Pagination, current: CurrentUserDep, session: TenantSessionDep
) -> list[FeedItem]:
    return _feed_items(*await _svc(current, session).feed(page.limit, page.offset))


@router.get(
    "/bookmarks",
    dependencies=[require_permission("post:read")], response_model=list[FeedItem], summary="Posts you have saved"
)
async def get_bookmarks(
    page: Pagination, current: CurrentUserDep, session: TenantSessionDep
) -> list[FeedItem]:
    return _feed_items(*await _svc(current, session).list_bookmarks(page.limit, page.offset))


@router.get(
    "/mentions",
    dependencies=[require_permission("post:read")], response_model=list[FeedItem], summary="Posts that mention you"
)
async def get_mentions(
    page: Pagination, current: CurrentUserDep, session: TenantSessionDep
) -> list[FeedItem]:
    return _feed_items(*await _svc(current, session).list_mentions(page.limit, page.offset))


@router.get(
    "/trending",
    dependencies=[require_permission("post:read")], response_model=list[TrendingTag], summary="Trending hashtags"
)
async def trending(
    current: CurrentUserDep,
    session: TenantSessionDep,
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> list[TrendingTag]:
    pairs = await _svc(current, session).trending(limit)
    return [TrendingTag(tag=tag, count=count) for tag, count in pairs]


@router.post(
    "/posts",
    dependencies=[require_permission("post:create")],
    response_model=PostRead,
    status_code=status.HTTP_201_CREATED,
    summary="Publish a post",
)
async def create_post(
    data: PostCreate, current: CurrentUserDep, session: TenantSessionDep
) -> PostRead:
    svc = _svc(current, session)
    post = await svc.create_post(data)
    read = PostRead.model_validate(post)
    read.mentions = _mention_reads(await svc.mentions_of(post.id))
    return read


@router.get("/posts/{post_id}", dependencies=[require_permission("post:read")], response_model=PostRead, summary="Get a post")
async def get_post(
    post_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> PostRead:
    svc = _svc(current, session)
    post = await svc.get_post(post_id)
    read = PostRead.model_validate(post)
    read.mentions = _mention_reads(await svc.mentions_of(post.id))
    return read


@router.post(
    "/posts/{post_id}/share",
    dependencies=[require_permission("post:create")],
    response_model=FeedItem,
    status_code=status.HTTP_201_CREATED,
    summary="Repost a post to your feed",
)
async def share_post(
    post_id: uuid.UUID,
    data: ShareCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> FeedItem:
    post = await _svc(current, session).share(post_id, data)
    return FeedItem.model_validate(post)


@router.delete(
    "/posts/{post_id}",
    dependencies=[require_permission("post:delete")],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your post",
)
async def delete_post(
    post_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).delete_post(post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/users/{user_id}/posts",
    dependencies=[require_permission("post:read")],
    response_model=list[PostRead],
    summary="Posts by a user",
)
async def user_posts(
    user_id: uuid.UUID, page: Pagination, current: CurrentUserDep, session: TenantSessionDep
) -> list[PostRead]:
    posts = await _svc(current, session).author_posts(user_id, page.limit, page.offset)
    return [PostRead.model_validate(p) for p in posts]


# ─── Reactions ──────────────────────────────────────────────────────
@router.put("/posts/{post_id}/reaction", dependencies=[require_permission("post:create")], status_code=204, summary="React to a post")
async def react(
    post_id: uuid.UUID,
    data: ReactionCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> Response:
    await _svc(current, session).react(post_id, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/posts/{post_id}/reaction", dependencies=[require_permission("post:create")], status_code=204, summary="Remove your reaction")
async def unreact(
    post_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).unreact(post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Bookmarks ──────────────────────────────────────────────────────
@router.put("/posts/{post_id}/bookmark", dependencies=[require_permission("post:read")], status_code=204, summary="Save a post")
async def bookmark(
    post_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).bookmark(post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/posts/{post_id}/bookmark", dependencies=[require_permission("post:read")], status_code=204, summary="Unsave a post")
async def unbookmark(
    post_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).unbookmark(post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Comments ───────────────────────────────────────────────────────
@router.post(
    "/posts/{post_id}/comments",
    dependencies=[require_permission("post:create")],
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Comment on a post",
)
async def add_comment(
    post_id: uuid.UUID,
    data: CommentCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> CommentRead:
    comment = await _svc(current, session).add_comment(post_id, data)
    return CommentRead.model_validate(comment)


@router.get(
    "/posts/{post_id}/comments",
    dependencies=[require_permission("post:read")],
    response_model=list[CommentRead],
    summary="List comments on a post",
)
async def list_comments(
    post_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> list[CommentRead]:
    comments = await _svc(current, session).list_comments(post_id)
    return [CommentRead.model_validate(c) for c in comments]


@router.delete("/comments/{comment_id}", dependencies=[require_permission("post:delete")], status_code=204, summary="Delete your comment")
async def delete_comment(
    comment_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).delete_comment(comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Connections ────────────────────────────────────────────────────
@router.post(
    "/connections/{user_id}",
    dependencies=[require_permission("connection:create")],
    response_model=ConnectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Send a connection request",
)
async def request_connection(
    user_id: uuid.UUID,
    data: ConnectionRequestCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> ConnectionRead:
    connection = await _svc(current, session).request_connection(user_id, data)
    return ConnectionRead.model_validate(connection)


@router.post(
    "/connections/{connection_id}/accept",
    dependencies=[require_permission("connection:create")],
    response_model=ConnectionRead,
    summary="Accept a connection request",
)
async def accept_connection(
    connection_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> ConnectionRead:
    connection = await _svc(current, session).respond_connection(connection_id, accept=True)
    return ConnectionRead.model_validate(connection)


@router.post(
    "/connections/{connection_id}/decline",
    dependencies=[require_permission("connection:create")],
    response_model=ConnectionRead,
    summary="Decline a connection request",
)
async def decline_connection(
    connection_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> ConnectionRead:
    connection = await _svc(current, session).respond_connection(connection_id, accept=False)
    return ConnectionRead.model_validate(connection)


@router.get(
    "/connections",
    dependencies=[require_permission("connection:read")],
    response_model=list[ConnectionRead],
    summary="List my connections (optionally by status)",
)
async def list_connections(
    current: CurrentUserDep,
    session: TenantSessionDep,
    status_filter: Annotated[ConnectionStatus | None, Query(alias="status")] = None,
) -> list[ConnectionRead]:
    connections = await _svc(current, session).list_connections(status_filter)
    return [ConnectionRead.model_validate(c) for c in connections]


@router.get(
    "/connections/requests",
    dependencies=[require_permission("connection:read")],
    response_model=list[ConnectionRead],
    summary="Incoming pending connection requests",
)
async def incoming_requests(
    current: CurrentUserDep, session: TenantSessionDep
) -> list[ConnectionRead]:
    connections = await _svc(current, session).incoming_requests()
    return [ConnectionRead.model_validate(c) for c in connections]


# ─── Follows ────────────────────────────────────────────────────────
@router.put("/follow/{user_id}", dependencies=[require_permission("connection:create")], status_code=204, summary="Follow a user")
async def follow(
    user_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).follow(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/follow/{user_id}", dependencies=[require_permission("connection:create")], status_code=204, summary="Unfollow a user")
async def unfollow(
    user_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).unfollow(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Directory ──────────────────────────────────────────────────────
@router.get(
    "/directory",
    dependencies=[require_permission("profile:read")],
    response_model=list[DirectoryPerson],
    summary="Discover people to connect with",
)
async def directory(
    page: Pagination, current: CurrentUserDep, session: TenantSessionDep
) -> list[DirectoryPerson]:
    people = await _svc(current, session).directory(page.limit, page.offset)
    result: list[DirectoryPerson] = []
    for identity, conn_status, following in people:
        person = DirectoryPerson.model_validate(identity)
        person.connection_status = conn_status
        person.is_following = following
        result.append(person)
    return result


@router.get(
    "/people/{user_id}",
    dependencies=[require_permission("profile:read")],
    response_model=PublicProfile,
    summary="A person's public profile (cross-tenant)",
)
async def person(
    user_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> PublicProfile:
    identity, conn_status, following = await _svc(current, session).public_profile(user_id)
    profile = PublicProfile.model_validate(identity)
    profile.connection_status = conn_status
    profile.is_following = following
    profile.is_self = user_id == current.id
    return profile


@router.get(
    "/me/identity",
    dependencies=[require_permission("profile:read")],
    response_model=MyIdentityRead,
    summary="Sync & get my directory identity",
)
async def my_identity(
    current: CurrentUserDep, session: TenantSessionDep
) -> MyIdentityRead:
    identity = await _svc(current, session).ensure_my_identity()
    return MyIdentityRead.model_validate(identity)


# ─── Directory opt-in / opt-out (audit P-10) ────────────────────────
# Deliberately unguarded beyond authentication: every user may always control
# whether they appear in the directory, whatever their role.
@router.patch(
    "/me/visibility",
    response_model=MyIdentityRead,
    summary="Opt in to / out of the people directory",
)
async def set_visibility(
    data: VisibilityUpdate, current: CurrentUserDep, session: TenantSessionDep
) -> MyIdentityRead:
    identity = await _svc(current, session).set_discoverable(data.discoverable)
    return MyIdentityRead.model_validate(identity)


@router.delete(
    "/me/directory",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove me from the people directory",
)
async def leave_directory(current: CurrentUserDep, session: TenantSessionDep) -> Response:
    await _svc(current, session).set_discoverable(False)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
