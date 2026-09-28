"""Payments service — order creation, signature verification, webhook reconcile."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.core.payments import PaymentProvider
from app.modules.payments.models import Payment, PaymentStatus
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import OrderCreate, PaymentVerify


class PaymentService:
    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        provider: PaymentProvider,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.provider = provider
        self.repo = PaymentRepository(session)

    async def create_order(self, data: OrderCreate) -> Payment:
        payment = Payment(
            tenant_id=self.tenant_id,
            amount=data.amount,
            currency=data.currency,
            provider=self.provider.name,
            provider_order_id="",  # set after the gateway call
            receipt=data.receipt,
            description=data.description,
            matter_id=data.matter_id,
            invoice_id=data.invoice_id,
            created_by=self.user_id,
        )
        self.repo.add(payment)
        await self.session.flush()
        order_id = await self.provider.create_order(
            amount=data.amount,
            currency=data.currency,
            receipt=data.receipt or str(payment.id),
        )
        payment.provider_order_id = order_id
        await self.session.flush()
        return payment

    async def verify(self, payment_id: uuid.UUID, data: PaymentVerify) -> Payment:
        payment = await self.repo.get(self.tenant_id, payment_id)
        if payment is None:
            raise NotFoundError("Payment not found.")
        if payment.status == PaymentStatus.PAID:
            return payment  # idempotent
        valid = self.provider.verify_payment(
            order_id=payment.provider_order_id,
            payment_id=data.razorpay_payment_id,
            signature=data.razorpay_signature,
        )
        if not valid:
            raise ValidationError("Payment signature verification failed.")
        payment.status = PaymentStatus.PAID
        payment.provider_payment_id = data.razorpay_payment_id
        payment.paid_at = datetime.now(UTC)
        return payment

    async def list(self, limit: int, offset: int) -> list[Payment]:
        return await self.repo.list(self.tenant_id, limit, offset)

    async def get(self, payment_id: uuid.UUID) -> Payment:
        payment = await self.repo.get(self.tenant_id, payment_id)
        if payment is None:
            raise NotFoundError("Payment not found.")
        return payment


async def handle_webhook(
    session: AsyncSession, provider: PaymentProvider, *, body: bytes, signature: str | None
) -> dict:
    """Reconcile a Razorpay webhook. Runs on a bypass-RLS session; the payment is
    resolved by gateway order id across tenants."""
    if not signature or not provider.verify_webhook(body=body, signature=signature):
        raise PermissionDeniedError("Invalid webhook signature.")
    try:
        event = json.loads(body)
    except ValueError as exc:
        raise ValidationError("Malformed webhook payload.") from exc

    if event.get("event") != "payment.captured":
        return {"status": "ignored"}

    entity = event.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = entity.get("order_id")
    if not order_id:
        return {"status": "ignored"}

    payment = await PaymentRepository(session).by_order_id(order_id)
    if payment is None:
        return {"status": "unknown_order"}
    if payment.status != PaymentStatus.PAID:
        payment.status = PaymentStatus.PAID
        payment.provider_payment_id = entity.get("id")
        payment.paid_at = datetime.now(UTC)
    if payment.invoice_id is not None:
        # Webhooks may arrive even when the payer closes the browser before the
        # return request. Reconcile here so the receipt and, for a proforma,
        # the final tax invoice are still issued exactly once.
        await session.flush()
        from app.modules.billing.service import BillingService

        await BillingService(session, payment.created_by, payment.tenant_id).reconcile(
            payment.invoice_id
        )
    return {"status": "ok"}
