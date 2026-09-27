"""Tenant (organisation) HTTP endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.core.pagination import PageParams, page_params
from app.modules.audit.service import record_audit
from app.modules.identity.admin_service import UserAdminService
from app.modules.identity.repository import UserRepository
from app.modules.identity.schemas import (
    AdminUserCreate,
    RoleAssignment,
    RoleRead,
    UserCreatedRead,
    UserRead,
)
from app.modules.tenancy.schemas import TenantRead, TenantUpdate
from app.modules.tenancy.service import TenantService

router = APIRouter(prefix="/tenants", tags=["Tenancy"])

Pagination = Annotated[PageParams, Depends(page_params)]


@router.get("/current", response_model=TenantRead, summary="Current organisation")
async def get_current_tenant(
    current: CurrentUserDep, session: TenantSessionDep
) -> TenantRead:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    tenant = await TenantService(session).get(current.tenant_id)
    return TenantRead.model_validate(tenant)


@router.patch(
    "/current",
    response_model=TenantRead,
    summary="Update current organisation settings",
    dependencies=[require_permission("tenant:manage")],
)
async def update_current_tenant(
    data: TenantUpdate, current: CurrentUserDep, session: TenantSessionDep
) -> TenantRead:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    tenant = await TenantService(session).update(current.tenant_id, data)
    return TenantRead.model_validate(tenant)


@router.get(
    "/users",
    response_model=list[UserRead],
    summary="List users in the organisation",
    dependencies=[require_permission("user:read")],
)
async def list_users(
    page: Pagination, current: CurrentUserDep, session: TenantSessionDep
) -> list[UserRead]:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    users = await UserRepository(session).list_for_tenant(
        current.tenant_id, page.limit, page.offset
    )
    return [UserRead.model_validate(u) for u in users]


@router.post(
    "/users",
    response_model=UserCreatedRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a user to the organisation",
    dependencies=[require_permission("user:create")],
)
async def create_user(
    payload: AdminUserCreate, current: CurrentUserDep, session: TenantSessionDep
) -> UserCreatedRead:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    svc = UserAdminService(session, current.tenant_id, current.id)
    user, temp_password = await svc.create_user(
        email=payload.email, full_name=payload.full_name, role_codes=payload.role_codes
    )
    record_audit(
        session,
        tenant_id=current.tenant_id,
        actor_id=current.id,
        actor_label=current.email,
        action="user.created",
        summary=f"Added user {user.email} ({', '.join(payload.role_codes)})",
        entity_type="user",
        entity_id=str(user.id),
    )
    return UserCreatedRead(user=UserRead.model_validate(user), temporary_password=temp_password)


@router.get(
    "/roles",
    response_model=list[RoleRead],
    summary="Roles assignable within the organisation",
    dependencies=[require_permission("role:read")],
)
async def list_roles(current: CurrentUserDep, session: TenantSessionDep) -> list[RoleRead]:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    roles = await UserAdminService(session, current.tenant_id, current.id).list_roles()
    return [RoleRead.model_validate(r) for r in roles]


@router.put(
    "/users/{user_id}/roles",
    response_model=UserRead,
    summary="Set a user's roles",
    dependencies=[require_permission("role:manage")],
)
async def set_user_roles(
    user_id: uuid.UUID,
    payload: RoleAssignment,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> UserRead:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    svc = UserAdminService(session, current.tenant_id, current.id)
    user = await svc.set_roles(user_id, payload.role_codes)
    record_audit(
        session,
        tenant_id=current.tenant_id,
        actor_id=current.id,
        actor_label=current.email,
        action="user.roles_updated",
        summary=f"Roles for {user.email} set to {', '.join(payload.role_codes)}",
        entity_type="user",
        entity_id=str(user_id),
        meta={"roles": payload.role_codes},
    )
    return UserRead.model_validate(user)


@router.post(
    "/users/{user_id}/deactivate",
    response_model=UserRead,
    summary="Deactivate a user (blocks sign-in, revokes their sessions)",
    dependencies=[require_permission("user:update")],
)
async def deactivate_user(
    user_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> UserRead:
    return await _set_user_active(user_id, False, current, session)


@router.post(
    "/users/{user_id}/activate",
    response_model=UserRead,
    summary="Reactivate a user",
    dependencies=[require_permission("user:update")],
)
async def activate_user(
    user_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> UserRead:
    return await _set_user_active(user_id, True, current, session)


async def _set_user_active(
    user_id: uuid.UUID, active: bool, current: CurrentUserDep, session: TenantSessionDep
) -> UserRead:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    svc = UserAdminService(session, current.tenant_id, current.id)
    user = await svc.set_active(user_id, active)
    record_audit(
        session,
        tenant_id=current.tenant_id,
        actor_id=current.id,
        actor_label=current.email,
        action="user.activated" if active else "user.deactivated",
        summary=f"{'Reactivated' if active else 'Deactivated'} user {user.email}",
        entity_type="user",
        entity_id=str(user_id),
    )
    return UserRead.model_validate(user)
