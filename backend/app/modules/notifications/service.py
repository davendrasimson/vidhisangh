"""Notifications service.

``create_notification`` is a module-level helper that any other module's service
calls (within its own transaction) to record an event. It writes the in-app row
and then fans the event out across the recipient's enabled channels (the rule
engine), recording every routing decision in the delivery log.
``NotificationService`` / ``PreferenceService`` back the HTTP endpoints.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.channels import ChannelMessage, get_channels
from app.core.exceptions import NotFoundError, PermissionDeniedError
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
            user_id=user_id, type=type, channel=channel, status=status, detail=detail
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
    for channel in active:
        provider = registry.provider_for(channel)
        if provider is None:
            _record(session, user_id=user_id, type=type, channel=channel,
                    status=DeliveryStatus.SKIPPED, detail="no provider configured")
            continue
        payload = ChannelMessage(
            to_email=getattr(recipient, "email", None),
            to_name=getattr(recipient, "full_name", None),
            subject=f"VidhiSangh: {type.value.replace('_', ' ')}",
            body=message,
            link=link,
        )
        try:
            await provider.send(payload)
            _record(session, user_id=user_id, type=type, channel=channel,
                    status=DeliveryStatus.SENT, detail=f"via {provider.name}")
        except Exception as exc:  # a channel failure must never break the caller's txn
            logger.warning("notification channel %s failed: %s", channel, exc)
            _record(session, user_id=user_id, type=type, channel=channel,
                    status=DeliveryStatus.FAILED, detail=str(exc)[:400])


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
