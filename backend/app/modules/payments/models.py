"""Payment domain model (Phase 5) — tenant-scoped with RLS."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import TenantScopedBase


class PaymentStatus(StrEnum):
    CREATED = "created"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class Payment(TenantScopedBase):
    __tablename__ = "payments"

    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # smallest unit (paise)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        String(20), default=PaymentStatus.CREATED, nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_order_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    receipt: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
