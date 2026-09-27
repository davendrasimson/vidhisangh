"""Webhook service: endpoint management + signed, queued event delivery.

``emit_event`` is a module-level helper other modules call (within their own
transaction). It **enqueues** one delivery job per subscribed endpoint on an
in-process asyncio queue; a background worker delivers with retries (3 attempts,
exponential back-off, 10 s timeout per attempt) in its own DB session, so a slow
or dead receiver never holds up the emitting request (audit A-25). Celery is not
wired, so the queue is process-local; ``drain()`` flushes it (tests, shutdown).

Signatures (audit A-25)
-----------------------
Each request carries::

    X-VidhiSangh-Event:            <event key>
    X-VidhiSangh-Timestamp:        <unix seconds>
    X-VidhiSangh-Signature:        t=<unix seconds>,v1=<hex hmac-sha256>
    X-VidhiSangh-Signature-Legacy: <hex hmac-sha256 over the body only>

``v1`` is ``HMAC_SHA256(secret, f"{t}.{body}")``. Receivers must recompute it
over the raw body, compare in constant time and **reject requests whose ``t`` is
more than 5 minutes from their clock** (``SIGNATURE_TOLERANCE_SECONDS``) to stop
replays. The ``-Legacy`` header is kept for one release for receivers that still
verify the body-only scheme and will be removed.

Circuit breaker
---------------
After ``AUTO_DISABLE_AFTER_FAILURES`` consecutive failed attempts the endpoint
is switched off (``is_active=False``, ``auto_disabled_at`` set), an audit event
and a ``webhook.auto_disabled`` event are recorded. Re-enabling via PATCH resets
the counter.

Security events (audit A-20)
----------------------------
``emit_security_event`` records an audit row, fans a ``security.*`` webhook out
to the tenant's endpoints and pings the operator Slack channel (``VS_SLACK_WEBHOOK``
via the channels seam) when it is configured.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.link_preview import assert_public_http_url
from app.core.webhook_transport import WebhookTransport, get_webhook_transport
from app.modules.webhooks.catalog import EVENT_KEYS, SECURITY_EVENT_KEYS
from app.modules.webhooks.models import (
    AUTO_DISABLE_AFTER_FAILURES,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.modules.webhooks.repository import WebhookRepository

logger = logging.getLogger("vidhisangh.webhooks")

SIGNATURE_TOLERANCE_SECONDS = 300  # receivers should reject |now - t| > 5 min
MAX_DELIVERY_ATTEMPTS = 3


# ─── Signing ─────────────────────────────────────────────────────────
def sign_payload(secret: str, timestamp: int, body: bytes) -> str:
    """``v1`` signature: HMAC-SHA256 over ``f"{timestamp}.{body}"``."""
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def sign_payload_legacy(secret: str, body: bytes) -> str:
    """Body-only HMAC (previous scheme, kept for one release)."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(
    secret: str, header: str, body: bytes, *, now: int | None = None,
    tolerance: int = SIGNATURE_TOLERANCE_SECONDS,
) -> bool:
    """Reference verifier for receivers (and our tests): parses
    ``t=...,v1=...``, checks the timestamp window and the HMAC in constant time."""
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    try:
        ts = int(parts["t"])
        given = parts["v1"]
    except (KeyError, ValueError):
        return False
    if abs((now if now is not None else int(time.time())) - ts) > tolerance:
        return False
    return hmac.compare_digest(sign_payload(secret, ts, body), given)


def _headers(endpoint: WebhookEndpoint, event_type: str, body: bytes) -> dict[str, str]:
    ts = int(time.time())
    return {
        "Content-Type": "application/json",
        "User-Agent": "VidhiSangh-Webhooks/2.0",
        "X-VidhiSangh-Event": event_type,
        "X-VidhiSangh-Timestamp": str(ts),
        "X-VidhiSangh-Signature": f"t={ts},v1={sign_payload(endpoint.secret, ts, body)}",
        "X-VidhiSangh-Signature-Legacy": sign_payload_legacy(endpoint.secret, body),
    }


# ─── One delivery attempt ────────────────────────────────────────────
async def deliver_once(
    session: AsyncSession,
    endpoint: WebhookEndpoint,
    event_type: str,
    data: dict,
    transport: WebhookTransport,
    *,
    attempt: int | None = None,
) -> WebhookDelivery:
    """POST one event to one endpoint, record the outcome and update the circuit
    breaker. Stores only the status code and a fixed reason — never the body."""
    body = json.dumps({"event": event_type, "data": data}, default=str).encode()
    status, code, detail = "failed", None, None
    try:
        await assert_public_http_url(endpoint.url)  # the URL may have been re-pointed since creation
        code, _ = await transport.send(endpoint.url, _headers(endpoint, event_type, body), body)
        if 200 <= code < 300:
            status, detail = "success", "delivered"
        else:
            detail = "failed: non-2xx response"
    except Exception as exc:  # a bad receiver must not break the caller
        logger.warning("webhook delivery to endpoint %s failed: %s", endpoint.id, type(exc).__name__)
        detail = f"failed: {type(exc).__name__}"
    if attempt is not None:
        detail = f"{detail} (attempt {attempt}/{MAX_DELIVERY_ATTEMPTS})"
    delivery = WebhookDelivery(
        tenant_id=endpoint.tenant_id,
        endpoint_id=endpoint.id,
        event_type=event_type,
        status=status,
        status_code=code,
        detail=detail,
    )
    session.add(delivery)
    await _update_breaker(session, endpoint, success=(status == "success"))
    return delivery


async def _update_breaker(session: AsyncSession, endpoint: WebhookEndpoint, *, success: bool) -> None:
    if success:
        endpoint.consecutive_failures = 0
        return
    endpoint.consecutive_failures = (endpoint.consecutive_failures or 0) + 1
    if endpoint.consecutive_failures < AUTO_DISABLE_AFTER_FAILURES or not endpoint.is_active:
        return
    endpoint.is_active = False
    endpoint.auto_disabled_at = datetime.now(UTC)
    from app.modules.audit.service import record_audit  # local import: audit imports nothing from here

    record_audit(
        session,
        tenant_id=endpoint.tenant_id,
        action="webhook.auto_disabled",
        summary=f"Webhook endpoint disabled after {endpoint.consecutive_failures} consecutive failures",
        entity_type="webhook",
        entity_id=str(endpoint.id),
        meta={"url": endpoint.url},
    )
    logger.warning("webhook endpoint %s auto-disabled (circuit breaker)", endpoint.id)
    # Tell the tenant's *other* endpoints (never the broken one).
    await emit_event(
        session,
        tenant_id=endpoint.tenant_id,
        event_type="webhook.auto_disabled",
        data={"endpoint_id": str(endpoint.id), "url": endpoint.url},
        exclude_endpoint_id=endpoint.id,
    )


# ─── Background dispatcher ───────────────────────────────────────────
SessionOpener = Callable[[uuid.UUID], AbstractAsyncContextManager[AsyncSession]]


def _default_session_opener(tenant_id: uuid.UUID) -> AbstractAsyncContextManager[AsyncSession]:
    from app.core.database import session_scope

    return session_scope(tenant_id=str(tenant_id))


@dataclass(slots=True)
class DeliveryJob:
    tenant_id: uuid.UUID
    endpoint_id: uuid.UUID
    event_type: str
    data: dict
    attempts: int = field(default=0)


class WebhookDispatcher:
    """Process-local queue + worker. ``auto=False`` (tests) parks jobs until
    :meth:`drain` is called, so deliveries never race the request's DB session."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[DeliveryJob] | None = None
        self._worker: asyncio.Task | None = None
        self.auto = True
        self.backoff_base = 1.0  # seconds; attempt n waits base * 2**(n-1)
        self.session_opener: SessionOpener = _default_session_opener

    # -- configuration (tests / startup) --------------------------------
    def configure(
        self,
        *,
        session_opener: SessionOpener | None = None,
        auto: bool | None = None,
        backoff_base: float | None = None,
    ) -> None:
        if session_opener is not None:
            self.session_opener = session_opener
        if auto is not None:
            self.auto = auto
        if backoff_base is not None:
            self.backoff_base = backoff_base

    def reset(self) -> None:
        """Drop any parked jobs and restore defaults (tests)."""
        if self._worker is not None:
            self._worker.cancel()
        self._worker = None
        self._queue = None
        self.auto = True
        self.backoff_base = 1.0
        self.session_opener = _default_session_opener

    # -- producer -------------------------------------------------------
    def _ensure_queue(self) -> asyncio.Queue[DeliveryJob]:
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

    def enqueue(self, job: DeliveryJob) -> None:
        self._ensure_queue().put_nowait(job)
        if self.auto and (self._worker is None or self._worker.done()):
            self._worker = asyncio.get_running_loop().create_task(self._run(), name="webhook-dispatcher")

    @property
    def pending(self) -> int:
        return self._queue.qsize() if self._queue else 0

    # -- consumer -------------------------------------------------------
    async def _run(self) -> None:
        queue = self._ensure_queue()
        while True:
            job = await queue.get()
            try:
                await self._process(job)
            except Exception:  # noqa: BLE001 - the worker must survive anything
                logger.exception("webhook job crashed (endpoint %s)", job.endpoint_id)
            finally:
                queue.task_done()

    async def drain(self) -> None:
        """Deliver every parked job now (tests / graceful shutdown)."""
        queue = self._ensure_queue()
        while not queue.empty():
            job = queue.get_nowait()
            try:
                await self._process(job)
            except Exception:  # noqa: BLE001
                logger.exception("webhook job crashed (endpoint %s)", job.endpoint_id)
            finally:
                queue.task_done()

    async def _process(self, job: DeliveryJob) -> None:
        transport = get_webhook_transport()
        for attempt in range(1, MAX_DELIVERY_ATTEMPTS + 1):
            job.attempts = attempt
            async with self.session_opener(job.tenant_id) as session:
                endpoint = await WebhookRepository(session).get(job.tenant_id, job.endpoint_id)
                if endpoint is None or not endpoint.is_active:
                    return  # deleted or (auto-)disabled meanwhile — stop retrying
                delivery = await deliver_once(
                    session, endpoint, job.event_type, job.data, transport, attempt=attempt
                )
                done = delivery.status == "success" or not endpoint.is_active
            if done or attempt == MAX_DELIVERY_ATTEMPTS:
                return
            if self.backoff_base > 0:
                await asyncio.sleep(self.backoff_base * (2 ** (attempt - 1)))


dispatcher = WebhookDispatcher()


async def emit_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    event_type: str,
    data: dict,
    exclude_endpoint_id: uuid.UUID | None = None,
) -> None:
    """Queue ``event_type`` for every active endpoint subscribed to it. No-op
    when the tenant has no matching endpoints (the common case). Delivery
    happens off the request path — see :class:`WebhookDispatcher`."""
    endpoints = await WebhookRepository(session).active_for_event(tenant_id, event_type)
    for endpoint in endpoints:
        if exclude_endpoint_id is not None and endpoint.id == exclude_endpoint_id:
            continue
        dispatcher.enqueue(
            DeliveryJob(tenant_id=tenant_id, endpoint_id=endpoint.id, event_type=event_type, data=data)
        )


async def emit_security_event(
    session: AsyncSession,
    *,
    event_type: str,
    summary: str,
    tenant_id: uuid.UUID | None,
    actor_id: uuid.UUID | None = None,
    actor_label: str | None = None,
    data: dict | None = None,
) -> None:
    """Record a security signal: audit row + tenant ``security.*`` webhook +
    operator alert. Safe to call from the auth service; never raises."""
    if event_type not in SECURITY_EVENT_KEYS:
        raise ValueError(f"not a security event: {event_type}")
    payload = dict(data or {})
    if tenant_id is not None:
        from app.modules.audit.service import record_audit

        record_audit(
            session,
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_label=actor_label,
            action=event_type,
            summary=summary,
            entity_type="security",
            entity_id=str(actor_id) if actor_id else None,
            meta=payload or None,
        )
        try:
            await emit_event(session, tenant_id=tenant_id, event_type=event_type, data=payload)
        except Exception:  # noqa: BLE001 - a webhook problem must never block auth
            logger.exception("security webhook fan-out failed")
    await _operator_alert(event_type, summary)


async def _operator_alert(event_type: str, summary: str) -> None:
    """Ping the operator's ops channel (Slack via ``VS_SLACK_WEBHOOK``) when it is
    configured; the log provider otherwise. Failures are logged, not raised."""
    try:
        from app.core.channels import ChannelMessage, get_channels
        from app.modules.notifications.models import NotificationChannel

        provider = get_channels().provider_for(NotificationChannel.SLACK)
        if provider is None:
            return
        await provider.send(
            ChannelMessage(to_email=None, to_name="ops", subject=f"[security] {event_type}", body=summary)
        )
    except Exception:  # noqa: BLE001
        logger.exception("operator alert failed for %s", event_type)


# ─── Endpoint management ─────────────────────────────────────────────
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
        await assert_public_http_url(url)
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
        self, endpoint_id: uuid.UUID, *, url=None, description=None, event_types=None, is_active=None
    ) -> WebhookEndpoint:
        endpoint = await self.get(endpoint_id)
        if url is not None:
            await assert_public_http_url(url)
            endpoint.url = url
            endpoint.consecutive_failures = 0
        if event_types is not None:
            self._validate_events(event_types)
            endpoint.event_types = event_types
        if description is not None:
            endpoint.description = description
        if is_active is not None:
            endpoint.is_active = is_active
            if is_active:  # manual re-enable closes the breaker
                endpoint.consecutive_failures = 0
                endpoint.auto_disabled_at = None
        return endpoint

    async def delete(self, endpoint_id: uuid.UUID) -> None:
        endpoint = await self.get(endpoint_id)
        await self.repo.delete(endpoint)

    async def send_test(self, endpoint_id: uuid.UUID) -> WebhookDelivery:
        """Synchronous ping so the settings screen gets an immediate answer."""
        endpoint = await self.get(endpoint_id)
        delivery = await deliver_once(
            self.session, endpoint, "ping",
            {"message": "This is a test event from VidhiSangh."},
            get_webhook_transport(),
        )
        await self.session.flush()
        return delivery

    async def deliveries(self, endpoint_id: uuid.UUID, limit: int, offset: int) -> list[WebhookDelivery]:
        await self.get(endpoint_id)  # tenant ownership check
        return await self.repo.list_deliveries(self.tenant_id, endpoint_id, limit, offset)
