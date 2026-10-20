"""Notification domain model (Phase 2 hardening) — global cross-tenant layer.

Phase 6 extends this with multi-channel delivery: a per-user channel
``NotificationPreference`` rule set and an auditable ``NotificationDelivery``
log recording every routing decision.
"""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import JSON, Boolean, Date, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import AuditedBase


class NotificationType(StrEnum):
    MENTION = "mention"
    CONNECTION_REQUEST = "connection_request"
    CONNECTION_ACCEPTED = "connection_accepted"
    GROUP_INVITE = "group_invite"
    ENDORSEMENT = "endorsement"
    RECOMMENDATION = "recommendation"
    # A client completed the KYC form the user sent them.
    KYC_SUBMITTED = "kyc_submitted"
    MATTER_ASSIGNED = "matter_assigned"
    SUPPORT_UPDATE = "support_update"
    DOCUMENT_SIGNATURE = "document_signature"


class NotificationChannel(StrEnum):
    """Delivery channels. ``in_app`` + ``email`` + ``slack`` have live providers;
    the rest are recognised routes whose providers await infra (see deferred items)."""

    IN_APP = "in_app"
    EMAIL = "email"
    SLACK = "slack"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    PUSH = "push"
    TEAMS = "teams"


class DeliveryStatus(StrEnum):
    SENT = "sent"  # handed to the provider successfully
    FAILED = "failed"  # provider raised
    SKIPPED = "skipped"  # channel enabled but its provider is not configured


class Notification(AuditedBase):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    type: Mapped[NotificationType] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message: Mapped[str] = mapped_column(String(400), nullable=False)
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class NotificationPreference(AuditedBase):
    """One row per (user, channel). ``types`` is an optional allowlist of
    ``NotificationType`` values — empty/null means *every* type routes here."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "channel", name="uq_notif_pref_user_channel"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    channel: Mapped[NotificationChannel] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    types: Mapped[list | None] = mapped_column(JSON, nullable=True)


class NotificationDelivery(AuditedBase):
    """Immutable audit row: how one notification was routed to one channel."""

    __tablename__ = "notification_deliveries"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    type: Mapped[NotificationType] = mapped_column(String(40), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(String(20), nullable=False)
    status: Mapped[DeliveryStatus] = mapped_column(String(10), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(400), nullable=True)


class HearingReminderSend(AuditedBase):
    """One evening WhatsApp reminder: a member's hearings for one day.

    The unique (user, day) row is written before the message goes out, so a
    rerun of the job never sends the same day twice. Holds counts and the
    outcome only, never the hearings or the number.
    """

    __tablename__ = "hearing_reminder_sends"
    __table_args__ = (UniqueConstraint("user_id", "for_date", name="uq_hearing_reminder_user_day"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    for_date: Mapped[date] = mapped_column(Date, nullable=False)
    hearing_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # sending | sent | failed
    detail: Mapped[str | None] = mapped_column(String(200), nullable=True)


class PushDevice(AuditedBase):
    """A phone that receives push notifications (Firebase token), per member.

    Registered by the app after sign-in (the OS permission prompt is the
    consent); removed at sign-out or when Firebase reports the token gone.
    A token moves to whoever signs in on that phone last.
    """

    __tablename__ = "push_devices"
    __table_args__ = (UniqueConstraint("token", name="uq_push_devices_token"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(512), nullable=False)
    platform: Mapped[str] = mapped_column(String(10), nullable=False)
