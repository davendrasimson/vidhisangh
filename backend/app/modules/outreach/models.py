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


class OutreachContact(AuditedBase):
    __tablename__ = "outreach_contacts"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
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


class OutreachSuppression(AuditedBase):
    __tablename__ = "outreach_suppressions"

    email_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    reason: Mapped[str] = mapped_column(String(30), nullable=False)


class OutreachSettings(AuditedBase):
    """A single row: the admin's pause switch and daily number."""

    __tablename__ = "outreach_settings"

    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
