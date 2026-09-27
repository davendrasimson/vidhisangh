"""Data-access layer for payments. Tenant queries filter by ``tenant_id``; the
webhook path resolves a payment by gateway order id across tenants."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import Payment, PaymentStatus


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, payment: Payment) -> None:
        self.session.add(payment)

    async def get(self, tenant_id: uuid.UUID, payment_id: uuid.UUID) -> Payment | None:
        res = await self.session.execute(
            select(Payment).where(
                Payment.id == payment_id,
                Payment.tenant_id == tenant_id,
                Payment.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def list(self, tenant_id: uuid.UUID, limit: int, offset: int) -> list[Payment]:
        res = await self.session.execute(
            select(Payment)
            .where(Payment.tenant_id == tenant_id, Payment.deleted_at.is_(None))
            .order_by(Payment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())

    async def by_order_id(self, order_id: str) -> Payment | None:
        """Resolve a payment by gateway order id (webhook path — bypass session)."""
        res = await self.session.execute(
            select(Payment).where(Payment.provider_order_id == order_id)
        )
        return res.scalar_one_or_none()

    async def paid_total_for_invoice(
        self, tenant_id: uuid.UUID, invoice_id: uuid.UUID
    ) -> int:
        """Sum of captured payments (smallest unit) applied to an invoice."""
        res = await self.session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.tenant_id == tenant_id,
                Payment.invoice_id == invoice_id,
                Payment.status == PaymentStatus.PAID,
            )
        )
        return int(res.scalar_one())
