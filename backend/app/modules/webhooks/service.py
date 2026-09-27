"""Webhook service: endpoint management + signed event delivery.

``emit_event`` is a module-level helper other modules call (within their own
transaction) to fan an event out to subscribed endpoints. Delivery is inline and
guarded so a failing receiver never breaks the emitting request; an async queue
with retries is the deferred hardening step.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.webhook_transport import WebhookTransport, get_webhook_transport
from app.modules.webhooks.catalog import EVENT_KEYS
from app.modules.webhooks.models import WebhookDelivery, WebhookEndpoint
from app.modules.webhooks.repository import WebhookRepository

logger = logging.getLogger("vidhisangh.webhooks")


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def _deliver(
    session: AsyncSession,
    endpoint: WebhookEndpoint,
    event_type: str,
    data: dict,
    transport: WebhookTransport,
) -> WebhookDelivery:
    body = json.dumps({"event": event_type, "data": data}, default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "X-VidhiSangh-Event": event_type,
        "X-VidhiSangh-Signature": _sign(endpoint.secret, body),
    }
    status, code, detail = "failed", None, None
    try:
        code, text = await transport.send(endpoint.url, headers, body)
        status = "success" if 200 <= code < 300 else "failed"
        detail = text
    except Exception as exc:  # a bad receiver must not break the emitting txn
        logger.warning("webhook delivery to %s failed: %s", endpoint.url, exc)
        detail = str(exc)[:500]
    delivery = WebhookDelivery(
        tenant_id=endpoint.tenant_id,
        endpoint_id=endpoint.id,
        event_type=event_type,
        status=status,
        status_code=code,
        detail=detail,
    )
    session.add(delivery)
    return delivery


async def emit_event(
    session: AsyncSession, *, tenant_id: uuid.UUID, event_type: str, data: dict
) -> None:
    """Deliver ``event_type`` to every active endpoint subscribed to it. No-op
    when the tenant has no matching endpoints (the common case)."""
    endpoints = await WebhookRepository(session).active_for_event(tenant_id, event_type)
    if not endpoints:
        return
    transport = get_webhook_transport()
    for endpoint in endpoints:
        await _deliver(session, endpoint, event_type, data, transport)


class WebhookService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.repo = WebhookRepository(session)

    @staticmethod
    def _validate_events(event_types: list[str]) -> None:
        unknown = [e for e in event_types if e not in EVENT_KEYS]
        if unknown:
            raise ValidationError(f"Unknown event type(s): {', '.join(unknown)}")

    async def create(self, url: str, description: str | None, event_types: list[str]) -> WebhookEndpoint:
        self._validate_events(event_types)
        endpoint = WebhookEndpoint(
            tenant_id=self.tenant_id,
            url=url,
            description=description,
            secret=f"whsec_{secrets.token_urlsafe(24)}",
            event_types=event_types,
            is_active=True,
            created_by=self.user_id,
        )
        self.repo.add(endpoint)
        await self.session.flush()
        return endpoint

    async def list(self) -> list[WebhookEndpoint]:
        return await self.repo.list(self.tenant_id)

    async def get(self, endpoint_id: uuid.UUID) -> WebhookEndpoint:
        endpoint = await self.repo.get(self.tenant_id, endpoint_id)
        if endpoint is None:
            raise NotFoundError("Webhook not found.")
        return endpoint

    async def update(
        self, endpoint_id: uuid.UUID, *, description, event_types, is_active
    ) -> WebhookEndpoint:
        endpoint = await self.get(endpoint_id)
        if event_types is not None:
            self._validate_events(event_types)
            endpoint.event_types = event_types
        if description is not None:
            endpoint.description = description
        if is_active is not None:
            endpoint.is_active = is_active
        return endpoint

    async def delete(self, endpoint_id: uuid.UUID) -> None:
        endpoint = await self.get(endpoint_id)
        await self.repo.delete(endpoint)

    async def send_test(self, endpoint_id: uuid.UUID) -> WebhookDelivery:
        endpoint = await self.get(endpoint_id)
        delivery = await _deliver(
            self.session, endpoint, "ping",
            {"message": "This is a test event from VidhiSangh."},
            get_webhook_transport(),
        )
        await self.session.flush()
        return delivery

    async def deliveries(self, endpoint_id: uuid.UUID, limit: int, offset: int) -> list[WebhookDelivery]:
        await self.get(endpoint_id)  # tenant ownership check
        return await self.repo.list_deliveries(self.tenant_id, endpoint_id, limit, offset)
