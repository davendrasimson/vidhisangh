"""Daily official-order intake, explicit subscriptions and durable email claims."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import AuditedBase


class DailyOrder(AuditedBase):
    __tablename__ = "sc_daily_orders"

    judgment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("judgments.id", ondelete="CASCADE"),
        unique=True,
    )
    source_url: Mapped[str] = mapped_column(String(1000), unique=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_text", index=True)
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)


class DailyOrderSubscription(AuditedBase):
    __tablename__ = "sc_daily_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    subscribed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Rotate on re-subscription so old messages cannot cancel a new grant.
    token: Mapped[str] = mapped_column(String(64), unique=True)


class DailyOrderEmail(AuditedBase):
    __tablename__ = "sc_daily_emails"
    __table_args__ = (
        UniqueConstraint("subscription_id", "for_date", name="uq_sc_daily_email_day"),
    )

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sc_daily_subscriptions.id", ondelete="CASCADE"),
        index=True,
    )
    for_date: Mapped[date] = mapped_column(Date)
    judgment_ids: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))  # sending | sent | uncertain
