"""Outreach: invitation emails to non-members (platform-level, no tenant).

Global tables like the network tables (no RLS); only the platform admin
reaches them. Every address is invited at most once. An unsubscribe or a hard
bounce is also written to ``outreach_suppressions`` as a peppered hash, which
outlives the contact row, so the address is never emailed again even after the
contact list is cleared.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import AuditedBase


class OutreachStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    JOINED = "joined"            # signed up (before or after the invitation)
    UNSUBSCRIBED = "unsubscribed"
    BOUNCED = "bounced"          # the mail server refused the address
    SKIPPED = "skipped"          # already a member or suppressed when its turn came
    REMOVAL_REQUESTED = "removal_requested"  # asked (by reply, call, grievance) to be taken off: suppressed


class OutreachContact(AuditedBase):
    __tablename__ = "outreach_contacts"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Published alongside the email on some lists; shown to the admin, never used for sending.
    mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    court: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Where the address was found, shown in the email ("publicly listed in …").
    source: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[OutreachStatus] = mapped_column(String(20), nullable=False, default=OutreachStatus.QUEUED, index=True)
    # Random, for the unsubscribe link (and to recognise the invitation at sign-up).
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    joined_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    removal_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removal_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Engagement (migration 0087): first time each happened. `delivered_at` and `complained_at` come from the
    # relay's webhook; `opened_at` from our tracking image or the webhook; `clicked_at` from our own join link
    # (`/outreach/j/<token>`) or the webhook. A click counts as an open.
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    complained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutreachSuppression(AuditedBase):
    __tablename__ = "outreach_suppressions"

    email_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    reason: Mapped[str] = mapped_column(String(30), nullable=False)


class OutreachSettings(AuditedBase):
    """A single row: the admin's pause switch and daily number."""

    __tablename__ = "outreach_settings"

    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    # Court by court (owner, 2 Nov 2026): while set, only contacts whose city or court matches are sent.
    focus: Mapped[str | None] = mapped_column(String(200), nullable=True)


class OutreachFollowUp(AuditedBase):
    """A message sent to a contact after the invitation (22 Nov 2026): the single automatic
    **reminder** a week later to people who opened but did not click, or a **personal** note the
    platform admin sends from the Warm leads list. ``channel`` email | whatsapp (WhatsApp notes are
    sent by the admin from their own phone through a wa.me link; the row records that it was opened).
    One reminder per contact, ever."""

    __tablename__ = "outreach_followups"

    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(10), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # reminder | personal
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
