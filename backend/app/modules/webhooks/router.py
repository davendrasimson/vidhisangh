"""Webhook HTTP endpoints (RBAC-guarded, tenant-scoped)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.core.pagination import PageParams, page_params
from app.modules.audit.service import record_audit
from app.modules.webhooks.catalog import EVENT_CATALOG
from app.modules.webhooks.schemas import (
    DeliveryRead,
    EventTypeRead,
    WebhookCreate,
    WebhookCreated,
    WebhookRead,
    WebhookUpdate,
)
from app.modules.webhooks.service import WebhookService

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

Pagination = Annotated[PageParams, Depends(page_params)]


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> WebhookService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return WebhookService(session, current.id, current.tenant_id)


@router.get("/events", response_model=list[EventTypeRead], summary="Subscribable event types")
async def list_events(current: CurrentUserDep, session: TenantSessionDep) -> list[EventTypeRead]:
    return [EventTypeRead(key=e.key, description=e.description) for e in EVENT_CATALOG]


@router.post(
    "",
    response_model=WebhookCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Register a webhook endpoint",
    dependencies=[require_permission("webhook:manage")],
)
async def create_webhook(
    payload: WebhookCreate, current: CurrentUserDep, session: TenantSessionDep
) -> WebhookCreated:
    endpoint = await _svc(current, session).create(
        str(payload.url), payload.description, payload.event_types
    )
    record_audit(
        session,
        tenant_id=current.tenant_id,
        actor_id=current.id,
        actor_label=current.email,
        action="webhook.created",
        summary=f"Registered webhook {endpoint.url}",
        entity_type="webhook",
        entity_id=str(endpoint.id),
    )
    return WebhookCreated.model_validate(endpoint)


@router.get(
    "",
    response_model=list[WebhookRead],
    summary="List webhook endpoints",
    dependencies=[require_permission("webhook:manage")],
)
async def list_webhooks(current: CurrentUserDep, session: TenantSessionDep) -> list[WebhookRead]:
    return [WebhookRead.model_validate(e) for e in await _svc(current, session).list()]


@router.patch(
    "/{endpoint_id}",
    response_model=WebhookRead,
    summary="Update a webhook endpoint",
    dependencies=[require_permission("webhook:manage")],
)
async def update_webhook(
    endpoint_id: uuid.UUID,
    payload: WebhookUpdate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> WebhookRead:
    endpoint = await _svc(current, session).update(
        endpoint_id,
        description=payload.description,
        event_types=payload.event_types,
        is_active=payload.is_active,
    )
    return WebhookRead.model_validate(endpoint)


@router.delete(
    "/{endpoint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a webhook endpoint",
    dependencies=[require_permission("webhook:manage")],
)
async def delete_webhook(
    endpoint_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).delete(endpoint_id)
    record_audit(
        session,
        tenant_id=current.tenant_id,
        actor_id=current.id,
        actor_label=current.email,
        action="webhook.deleted",
        summary="Deleted a webhook endpoint",
        entity_type="webhook",
        entity_id=str(endpoint_id),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{endpoint_id}/test",
    response_model=DeliveryRead,
    summary="Send a test event",
    dependencies=[require_permission("webhook:manage")],
)
async def test_webhook(
    endpoint_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> DeliveryRead:
    delivery = await _svc(current, session).send_test(endpoint_id)
    return DeliveryRead.model_validate(delivery)


@router.get(
    "/{endpoint_id}/deliveries",
    response_model=list[DeliveryRead],
    summary="Recent deliveries for an endpoint",
    dependencies=[require_permission("webhook:manage")],
)
async def list_deliveries(
    endpoint_id: uuid.UUID,
    page: Pagination,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> list[DeliveryRead]:
    items = await _svc(current, session).deliveries(endpoint_id, page.limit, page.offset)
    return [DeliveryRead.model_validate(d) for d in items]
