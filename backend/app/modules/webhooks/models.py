"""Webhook domain models (Phase 6) — tenant-scoped with RLS."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import TenantScopedBase

# Consecutive failed delivery attempts after which an endpoint is switched off
# automatically (circuit breaker, audit A-25). Re-enabling via PATCH resets it.
AUTO_DISABLE_AFTER_FAILURES = 5


class WebhookEndpoint(TenantScopedBase):
    __tablename__ = "webhook_endpoints"

    url: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    secret: Mapped[str] = mapped_column(String(80), nullable=False)  # HMAC signing key
    event_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # Circuit breaker state.
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    auto_disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )


class WebhookDelivery(TenantScopedBase):
    __tablename__ = "webhook_deliveries"

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # success | failed
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A fixed reason only ("delivered" / "failed: <cause>") — never the receiver's body.
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    endpoint: Mapped[WebhookEndpoint] = relationship(back_populates="deliveries")
