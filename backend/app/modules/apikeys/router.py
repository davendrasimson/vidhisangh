"""API-key HTTP endpoints (RBAC-guarded, tenant-scoped)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.modules.apikeys.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyRead
from app.modules.apikeys.service import ApiKeyService
from app.modules.audit.service import record_audit

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> ApiKeyService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return ApiKeyService(session, current)


@router.get(
    "/scopes",
    response_model=list[str],
    summary="Permission scopes you can grant to a key",
    dependencies=[require_permission("apikey:manage")],
)
async def grantable_scopes(current: CurrentUserDep, session: TenantSessionDep) -> list[str]:
    return _svc(current, session).available_scopes()


@router.post(
    "",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create an API key (plaintext returned once)",
    dependencies=[require_permission("apikey:manage")],
)
async def create_key(
    payload: ApiKeyCreate, current: CurrentUserDep, session: TenantSessionDep
) -> ApiKeyCreated:
    key, raw = await _svc(current, session).create(
        name=payload.name, scopes=payload.scopes, expires_at=payload.expires_at
    )
    record_audit(
        session,
        tenant_id=current.tenant_id,
        actor_id=current.id,
        actor_label=current.email,
        action="apikey.created",
        summary=f"Created API key '{key.name}'",
        entity_type="apikey",
        entity_id=str(key.id),
        meta={"scopes": key.scopes},
    )
    return ApiKeyCreated(**ApiKeyRead.model_validate(key).model_dump(), key=raw)


@router.get(
    "",
    response_model=list[ApiKeyRead],
    summary="List API keys",
    dependencies=[require_permission("apikey:manage")],
)
async def list_keys(current: CurrentUserDep, session: TenantSessionDep) -> list[ApiKeyRead]:
    return [ApiKeyRead.model_validate(k) for k in await _svc(current, session).list()]


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
    dependencies=[require_permission("apikey:manage")],
)
async def revoke_key(
    key_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    key = await _svc(current, session).revoke(key_id)
    record_audit(
        session,
        tenant_id=current.tenant_id,
        actor_id=current.id,
        actor_label=current.email,
        action="apikey.revoked",
        summary=f"Revoked API key '{key.name}'",
        entity_type="apikey",
        entity_id=str(key.id),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
