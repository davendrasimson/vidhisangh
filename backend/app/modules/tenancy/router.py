"""Tenant (organisation) HTTP endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

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
from app.modules.tenancy.schemas import (
    TenantDeleteRequest,
    TenantDeleteResult,
    TenantNotificationSettings,
    TenantNotificationSettingsRead,
    TenantPrivacySettings,
    TenantPrivacySettingsRead,
    TenantRead,
    TenantUpdate,
)
from app.modules.tenancy.service import TenantService

router = APIRouter(prefix="/tenants", tags=["Tenancy"])

Pagination = Annotated[PageParams, Depends(page_params)]


@router.get(
    "/current",
    response_model=TenantRead,
    summary="Current organisation",
    dependencies=[require_permission("tenant:read")],
)
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
    "/current/notifications",
    response_model=TenantNotificationSettingsRead,
    summary="Organisation notification settings (per-tenant Slack webhook)",
    dependencies=[require_permission("tenant:manage")],
)
async def get_notification_settings(
    current: CurrentUserDep, session: TenantSessionDep
) -> TenantNotificationSettingsRead:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return await TenantService(session).notification_settings(current.tenant_id)


@router.patch(
    "/current/notifications",
    response_model=TenantNotificationSettingsRead,
    summary="Set the organisation's own Slack incoming-webhook URL (audit P-11)",
    dependencies=[require_permission("tenant:manage")],
)
async def update_notification_settings(
    data: TenantNotificationSettings, current: CurrentUserDep, session: TenantSessionDep
) -> TenantNotificationSettingsRead:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    result = await TenantService(session).set_notification_settings(current.tenant_id, data)
    record_audit(
        session,
        tenant_id=current.tenant_id,
        actor_id=current.id,
        actor_label=current.email,
        action="tenant.notifications_updated",
        summary="Slack webhook " + ("configured" if result.slack_webhook_configured else "removed"),
        entity_type="tenant",
        entity_id=str(current.tenant_id),
    )
    return result


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


# ═══ Privacy & offboarding (privacy agent) ══════════════════════════
@router.get(
    "/current/privacy",
    response_model=TenantPrivacySettingsRead,
    summary="Organisation privacy settings: data-protection contact, retention period, DPA facts",
    dependencies=[require_permission("tenant:manage")],
)
async def get_privacy_settings(current: CurrentUserDep, session: TenantSessionDep) -> TenantPrivacySettingsRead:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return await TenantService(session).privacy_settings(current.tenant_id)


@router.patch(
    "/current/privacy",
    response_model=TenantPrivacySettingsRead,
    summary="Update the organisation's privacy settings",
    dependencies=[require_permission("tenant:manage")],
)
async def update_privacy_settings(
    data: TenantPrivacySettings, current: CurrentUserDep, session: TenantSessionDep
) -> TenantPrivacySettingsRead:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    result = await TenantService(session).set_privacy_settings(current.tenant_id, data)
    record_audit(
        session, tenant_id=current.tenant_id, actor_id=current.id, actor_label=current.email,
        action="tenant.privacy_updated", summary="Privacy settings updated",
        entity_type="tenant", entity_id=str(current.tenant_id),
    )
    return result


@router.post(
    "/current/export",
    summary="Export the whole organisation as a zip of per-table JSON files (offboarding, DPDP s.11)",
    dependencies=[require_permission("tenant:manage")],
    response_class=StreamingResponse,
)
async def export_current_tenant(current: CurrentUserDep, session: TenantSessionDep) -> StreamingResponse:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    from app.modules.privacy.service import export_tenant_zip

    payload = await export_tenant_zip(session, current.tenant_id)
    record_audit(
        session, tenant_id=current.tenant_id, actor_id=current.id, actor_label=current.email,
        action="tenant.exported", summary=f"Organisation export generated ({len(payload)} bytes)",
        entity_type="tenant", entity_id=str(current.tenant_id),
    )
    tenant = await TenantService(session).get(current.tenant_id)

    def _chunks(data: bytes, size: int = 64 * 1024):  # noqa: ANN202
        for i in range(0, len(data), size):
            yield data[i:i + size]

    return StreamingResponse(
        _chunks(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{tenant.slug}-export.zip"'},
    )


@router.delete(
    "/current",
    response_model=TenantDeleteResult,
    summary="Cancel the organisation: disable every user now, erase everything after the grace period",
    dependencies=[require_permission("tenant:manage")],
)
async def delete_current_tenant(
    data: TenantDeleteRequest, current: CurrentUserDep, session: TenantSessionDep
) -> TenantDeleteResult:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return await TenantService(session).cancel(
        current.tenant_id, actor_id=current.id, actor_label=current.email,
        confirm_slug=data.confirm_slug, password=data.password,
    )
