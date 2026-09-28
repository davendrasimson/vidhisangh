"""User support desk and superuser-only platform administration APIs."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.core.deps import AuthSessionDep, CurrentUserDep, TenantSessionDep
from app.core.exceptions import NotFoundError, TenantError
from app.core.pagination import PageParams, page_params
from app.modules.identity.models import User
from app.modules.support.schemas import (
    AccountStatusRequest,
    AdminActionRead,
    ModerationRequest,
    PlatformOverview,
    PlatformPostRead,
    PlatformTenantRead,
    PlatformUserDetail,
    PlatformUserRead,
    TenantStatusRequest,
    TicketAdminUpdate,
    TicketCreate,
    TicketMessageCreate,
    TicketRead,
)
from app.modules.support.service import PlatformAdminService, SupportService, require_platform_admin

router = APIRouter(tags=["Support"])
Pagination = Annotated[PageParams, Depends(page_params)]


def _admin(current: CurrentUserDep, session: AuthSessionDep) -> PlatformAdminService:
    require_platform_admin(current.is_superuser)
    return PlatformAdminService(session, current.id, current.email)


async def _requester(current: CurrentUserDep, session: TenantSessionDep) -> User:
    user = await session.scalar(
        select(User).where(
            User.id == current.id, User.tenant_id == current.tenant_id, User.deleted_at.is_(None)
        )
    )
    if user is None:
        raise NotFoundError("Account not found.")
    return user


@router.post("/support/tickets", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    data: TicketCreate, current: CurrentUserDep, session: TenantSessionDep
) -> TicketRead:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    user = await _requester(current, session)
    ticket = await SupportService(session, current.id, current.tenant_id).create(
        data, name=user.full_name, email=user.email
    )
    return TicketRead.model_validate(ticket)


@router.get("/support/tickets", response_model=list[TicketRead])
async def my_tickets(current: CurrentUserDep, session: TenantSessionDep) -> list[TicketRead]:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return [
        TicketRead.model_validate(row)
        for row in await SupportService(session, current.id, current.tenant_id).list_mine()
    ]


@router.post("/support/tickets/{ticket_id}/messages", response_model=TicketRead)
async def add_ticket_message(
    ticket_id: uuid.UUID,
    data: TicketMessageCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> TicketRead:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    user = await _requester(current, session)
    ticket = await SupportService(session, current.id, current.tenant_id).add_message(
        ticket_id, data.body, name=user.full_name
    )
    return TicketRead.model_validate(ticket)


@router.get("/platform-admin/me")
async def platform_admin_me(current: CurrentUserDep) -> dict:
    require_platform_admin(current.is_superuser)
    return {"allowed": True, "email": current.email}


@router.get("/platform-admin/overview", response_model=PlatformOverview)
async def platform_overview(current: CurrentUserDep, session: AuthSessionDep) -> PlatformOverview:
    return await _admin(current, session).overview()


@router.get("/platform-admin/users", response_model=list[PlatformUserRead])
async def platform_users(
    page: Pagination,
    current: CurrentUserDep,
    session: AuthSessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    status_filter: Annotated[
        str | None, Query(alias="status", pattern="^(active|blocked)$")
    ] = None,
) -> list[PlatformUserRead]:
    return await _admin(current, session).users(q, status_filter, page.limit, page.offset)


@router.get("/platform-admin/users/{user_id}", response_model=PlatformUserDetail)
async def platform_user_detail(
    user_id: uuid.UUID, current: CurrentUserDep, session: AuthSessionDep
) -> PlatformUserDetail:
    return await _admin(current, session).user_detail(user_id)


@router.patch("/platform-admin/users/{user_id}/status", response_model=PlatformUserDetail)
async def platform_user_status(
    user_id: uuid.UUID,
    data: AccountStatusRequest,
    current: CurrentUserDep,
    session: AuthSessionDep,
) -> PlatformUserDetail:
    return await _admin(current, session).set_user_status(user_id, data)


@router.get("/platform-admin/tenants", response_model=list[PlatformTenantRead])
async def platform_tenants(
    page: Pagination,
    current: CurrentUserDep,
    session: AuthSessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> list[PlatformTenantRead]:
    return await _admin(current, session).tenants(q, page.limit, page.offset)


@router.patch("/platform-admin/tenants/{tenant_id}/status", response_model=PlatformTenantRead)
async def platform_tenant_status(
    tenant_id: uuid.UUID,
    data: TenantStatusRequest,
    current: CurrentUserDep,
    session: AuthSessionDep,
) -> PlatformTenantRead:
    return await _admin(current, session).set_tenant_status(tenant_id, data)


@router.get("/platform-admin/posts", response_model=list[PlatformPostRead])
async def platform_posts(
    page: Pagination,
    current: CurrentUserDep,
    session: AuthSessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    include_removed: bool = False,
) -> list[PlatformPostRead]:
    return await _admin(current, session).posts(q, include_removed, page.limit, page.offset)


@router.post("/platform-admin/posts/{post_id}/remove", response_model=PlatformPostRead)
async def remove_platform_post(
    post_id: uuid.UUID,
    data: ModerationRequest,
    current: CurrentUserDep,
    session: AuthSessionDep,
) -> PlatformPostRead:
    return await _admin(current, session).moderate_post(post_id, restore=False, reason=data.reason)


@router.post("/platform-admin/posts/{post_id}/restore", response_model=PlatformPostRead)
async def restore_platform_post(
    post_id: uuid.UUID,
    data: ModerationRequest,
    current: CurrentUserDep,
    session: AuthSessionDep,
) -> PlatformPostRead:
    return await _admin(current, session).moderate_post(post_id, restore=True, reason=data.reason)


@router.get("/platform-admin/tickets", response_model=list[TicketRead])
async def platform_tickets(
    page: Pagination,
    current: CurrentUserDep,
    session: AuthSessionDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[TicketRead]:
    return [
        TicketRead.model_validate(row)
        for row in await _admin(current, session).tickets(status_filter, page.limit, page.offset)
    ]


@router.patch("/platform-admin/tickets/{ticket_id}", response_model=TicketRead)
async def update_platform_ticket(
    ticket_id: uuid.UUID,
    data: TicketAdminUpdate,
    current: CurrentUserDep,
    session: AuthSessionDep,
) -> TicketRead:
    ticket = await _admin(current, session).update_ticket(ticket_id, data, actor_name=current.email)
    if ticket is None:
        raise NotFoundError("Support ticket not found.")
    return TicketRead.model_validate(ticket)


@router.get("/platform-admin/actions", response_model=list[AdminActionRead])
async def platform_actions(
    page: Pagination, current: CurrentUserDep, session: AuthSessionDep
) -> list[AdminActionRead]:
    return [
        AdminActionRead.model_validate(row)
        for row in await _admin(current, session).actions(page.limit, page.offset)
    ]
