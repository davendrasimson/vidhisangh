"""Notifications service.

``create_notification`` is a module-level helper that any other module's service
calls (within its own transaction) to record an event. It writes the in-app row
and then fans the event out across the recipient's enabled channels (the rule
engine), recording every routing decision in the delivery log.
``NotificationService`` / ``PreferenceService`` back the HTTP endpoints.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.channels import ChannelMessage, get_channels
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.link_preview import assert_public_http_url, http_client
from app.modules.identity.repository import UserRepository
from app.modules.notifications.models import (
    DeliveryStatus,
    Notification,
    NotificationChannel,
    NotificationDelivery,
    NotificationType,
)
from app.modules.notifications.repository import (
    DeliveryRepository,
    NotificationRepository,
    PreferenceRepository,
)

logger = logging.getLogger("vidhisangh.notifications")

# Channels that are on unless the user turns them off; everything else is opt-in.
_DEFAULT_ENABLED = {NotificationChannel.IN_APP}

# Delivery-log rows older than this are purged (audit P-12). The log is an
# operational trace, not a business record.
DELIVERY_RETENTION_DAYS = 90

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def mask_emails(text: str | None) -> str | None:
    """Replace every e-mail address with ``***@domain`` so the (long-lived)
    delivery log never stores a recipient address (audit P-12)."""
    if not text:
        return text
    return _EMAIL_RE.sub(lambda m: f"***@{m.group(1)}", text)


# ── Per-tenant Slack (audit P-11) ──────────────────────────────────
# A firm's notifications go to the firm's own Slack workspace; the operator-wide
# ``VS_SLACK_WEBHOOK`` is reserved for operator/security alerts and is never
# used for a tenant's user notifications.
SlackSender = Callable[[str, str], Awaitable[None]]


async def _post_slack(webhook_url: str, text: str) -> None:
    pinned = await assert_public_http_url(webhook_url, require_https=True)
    async with http_client(timeout=10) as client:
        resp = await client.post(
            pinned.pinned_url, json={"text": text}, headers=pinned.headers, extensions=pinned.extensions
        )
        resp.raise_for_status()


_slack_sender: SlackSender = _post_slack


def set_slack_sender(sender: SlackSender | None) -> None:
    """Test hook: capture tenant Slack posts instead of calling out."""
    global _slack_sender
    _slack_sender = sender or _post_slack


async def _tenant_slack_url(session: AsyncSession, recipient) -> str | None:  # noqa: ANN001
    if recipient is None or getattr(recipient, "tenant_id", None) is None:
        return None
    from app.modules.tenancy.repository import TenantRepository
    from app.modules.tenancy.service import tenant_slack_webhook

    return tenant_slack_webhook(await TenantRepository(session).get_by_id(recipient.tenant_id))


async def create_notification(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    type: NotificationType,
    message: str,
    actor_id: uuid.UUID | None = None,
    actor_name: str | None = None,
    link: str | None = None,
) -> None:
    """Record a notification for ``user_id`` and route it to enabled channels.
    No-op if the actor is the recipient."""
    if actor_id is not None and actor_id == user_id:
        return
    session.add(
        Notification(
            user_id=user_id,
            type=type,
            actor_id=actor_id,
            actor_name=actor_name,
            message=message,
            link=link,
        )
    )
    await _dispatch_channels(session, user_id=user_id, type=type, message=message, link=link)


def _record(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    type: NotificationType,
    channel: NotificationChannel,
    status: DeliveryStatus,
    detail: str | None = None,
) -> None:
    session.add(
        NotificationDelivery(
            user_id=user_id, type=type, channel=channel, status=status, detail=mask_emails(detail)
        )
    )


async def _dispatch_channels(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    type: NotificationType,
    message: str,
    link: str | None,
) -> None:
    # In-app is implicit and always delivered; log it for a complete audit trail.
    _record(session, user_id=user_id, type=type, channel=NotificationChannel.IN_APP, status=DeliveryStatus.SENT)

    prefs = {p.channel: p for p in await PreferenceRepository(session).for_user(user_id)}
    active = [
        channel
        for channel in NotificationChannel
        if channel != NotificationChannel.IN_APP
        and (p := prefs.get(channel)) is not None
        and p.enabled
        and (not p.types or type.value in p.types)
    ]
    if not active:
        return

    registry = get_channels()
    recipient = await UserRepository(session).get_by_id(user_id)
    subject = f"VidhiSangh: {type.value.replace('_', ' ')}"
    for channel in active:
        if channel == NotificationChannel.SLACK:
            await _dispatch_tenant_slack(
                session, recipient=recipient, user_id=user_id, type=type,
                subject=subject, message=message, link=link,
            )
            continue
        provider = registry.provider_for(channel)
        if provider is None:
            _record(session, user_id=user_id, type=type, channel=channel,
                    status=DeliveryStatus.SKIPPED, detail="no provider configured")
            continue
        payload = ChannelMessage(
            to_email=getattr(recipient, "email", None),
            to_name=getattr(recipient, "full_name", None),
            subject=subject,
            body=message,
            link=link,
        )
        try:
            await provider.send(payload)
            _record(session, user_id=user_id, type=type, channel=channel,
                    status=DeliveryStatus.SENT, detail=f"via {provider.name}")
        except Exception as exc:  # a channel failure must never break the caller's txn
            logger.warning("notification channel %s failed: %s", channel, type(exc).__name__)
            # Only the exception class is logged: provider messages can echo the address.
            _record(session, user_id=user_id, type=type, channel=channel,
                    status=DeliveryStatus.FAILED, detail=f"failed: {type(exc).__name__}")


async def _dispatch_tenant_slack(
    session: AsyncSession, *, recipient, user_id: uuid.UUID, type: NotificationType,  # noqa: ANN001
    subject: str, message: str, link: str | None,
) -> None:
    url = await _tenant_slack_url(session, recipient)
    if url is None:
        _record(session, user_id=user_id, type=type, channel=NotificationChannel.SLACK,
                status=DeliveryStatus.SKIPPED, detail="no Slack webhook configured for the organisation")
        return
    text = f"*{subject}*\n{message}" + (f"\n{link}" if link else "")
    try:
        await _slack_sender(url, text)
        _record(session, user_id=user_id, type=type, channel=NotificationChannel.SLACK,
                status=DeliveryStatus.SENT, detail="via tenant slack")
    except Exception as exc:  # noqa: BLE001
        logger.warning("tenant slack delivery failed: %s", type(exc).__name__)
        _record(session, user_id=user_id, type=type, channel=NotificationChannel.SLACK,
                status=DeliveryStatus.FAILED, detail=f"failed: {type(exc).__name__}")


async def purge_old_deliveries(session: AsyncSession, days: int = DELIVERY_RETENTION_DAYS) -> int:
    """Delete delivery-log rows older than ``days`` (audit P-12). Returns the
    number of rows removed. Registered in ``app.scripts.retention_purge``."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    res = await session.execute(delete(NotificationDelivery).where(NotificationDelivery.created_at < cutoff))
    return int(res.rowcount or 0)


async def count_deliveries(session: AsyncSession) -> int:
    res = await session.execute(select(func.count()).select_from(NotificationDelivery))
    return int(res.scalar_one())


# ─── Client-facing messages (consent-gated) ──────────────────────────
class ClientSendOutcome:
    SENT = "sent"
    BLOCKED_NO_CONSENT = "blocked_no_consent"
    NO_PROVIDER = "no_provider"
    NO_ADDRESS = "no_address"
    FAILED = "failed"


async def send_to_client(
    session: AsyncSession,
    *,
    client_id: uuid.UUID,
    channel: NotificationChannel,
    to_email: str | None,
    to_name: str | None,
    subject: str,
    body: str,
    link: str | None = None,
    basis: str = "consent",
) -> str:
    """Send a message to a *client* (a Data Principal, not a user) on ``channel``.

    DPDP s.6/s.7 gate: unless the message rests on a basis other than consent
    (``basis="contract"`` — e.g. the KYC link the engagement itself requires,
    or ``"legal_obligation"``), the client's latest consent event for the
    channel's purpose must be a grant. The decision (never the address) is
    logged so a withdrawal is provably honoured.
    """
    from app.modules.privacy.consent import client_channel_allowed

    if basis == "consent" and not await client_channel_allowed(session, client_id, str(channel)):
        logger.info("client message blocked: no consent client=%s channel=%s", client_id, channel)
        return ClientSendOutcome.BLOCKED_NO_CONSENT
    if channel == NotificationChannel.EMAIL and not to_email:
        return ClientSendOutcome.NO_ADDRESS
    provider = get_channels().provider_for(channel)
    if provider is None:
        return ClientSendOutcome.NO_PROVIDER
    try:
        await provider.send(ChannelMessage(to_email=to_email, to_name=to_name, subject=subject, body=body, link=link))
    except Exception as exc:  # noqa: BLE001 — a channel failure must never break the caller's txn
        logger.warning("client message via %s failed: %s", channel, exc)
        return ClientSendOutcome.FAILED
    logger.info("client message sent client=%s channel=%s basis=%s", client_id, channel, basis)
    return ClientSendOutcome.SENT


class NotificationService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.repo = NotificationRepository(session)

    async def list(self, limit: int, offset: int) -> list[Notification]:
        return await self.repo.list_for_user(self.user_id, limit, offset)

    async def unread_count(self) -> int:
        return await self.repo.unread_count(self.user_id)

    async def mark_read(self, notification_id: uuid.UUID) -> None:
        notification = await self.repo.get(notification_id)
        if notification is None:
            raise NotFoundError("Notification not found.")
        if notification.user_id != self.user_id:
            raise PermissionDeniedError("This notification is not yours.")
        notification.is_read = True

    async def mark_all_read(self) -> None:
        await self.repo.mark_all_read(self.user_id)

    async def deliveries(self, limit: int, offset: int) -> list[NotificationDelivery]:
        return await DeliveryRepository(self.session).list_for_user(self.user_id, limit, offset)


class PreferenceService:
    """Read/write the per-channel notification rule set for the current user."""

    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.repo = PreferenceRepository(session)

    async def list(self) -> list[dict]:
        """Every channel merged with the user's stored rows, so the UI always
        sees the full set with sensible defaults for unset channels."""
        stored = {p.channel: p for p in await self.repo.for_user(self.user_id)}
        result: list[dict] = []
        for channel in NotificationChannel:
            pref = stored.get(channel)
            result.append(
                {
                    "channel": channel,
                    "enabled": pref.enabled if pref else (channel in _DEFAULT_ENABLED),
                    "types": (pref.types or []) if pref else [],
                }
            )
        return result

    async def update(
        self, channel: NotificationChannel, enabled: bool, types: list[str] | None
    ) -> dict:
        if channel == NotificationChannel.IN_APP and not enabled:
            raise PermissionDeniedError("In-app notifications cannot be disabled.")
        pref = await self.repo.get(self.user_id, channel)
        if pref is None:
            from app.modules.notifications.models import NotificationPreference

            pref = NotificationPreference(user_id=self.user_id, channel=channel)
            self.repo.add(pref)
        pref.enabled = enabled
        pref.types = types or None
        return {"channel": channel, "enabled": pref.enabled, "types": pref.types or []}
