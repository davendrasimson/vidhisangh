"""Billing service — invoices, line items, GST totals, pay + reconcile."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.payments import PaymentProvider
from app.modules.billing.models import Invoice, InvoiceLineItem, InvoiceStatus
from app.modules.billing.repository import BillingRepository
from app.modules.billing.schemas import InvoiceCreate, InvoiceUpdate, LineItemCreate, MatterInvoicePrepare
from app.modules.clients.models import Client
from app.modules.matters.models import FeeEventStatus, Matter, MatterFeeEvent
from app.modules.payments.models import Payment
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import OrderCreate
from app.modules.payments.service import PaymentService

_CENTS = Decimal("0.01")


class BillingService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.repo = BillingRepository(session)

    async def _require(self, invoice_id: uuid.UUID, *, detail: bool = False) -> Invoice:
        invoice = await self.repo.get(self.tenant_id, invoice_id, detail=detail)
        if invoice is None:
            raise NotFoundError("Invoice not found.")
        return invoice

    def _line(self, invoice_id: uuid.UUID, data: LineItemCreate) -> InvoiceLineItem:
        amount = (data.quantity * data.unit_price).quantize(_CENTS)
        return InvoiceLineItem(
            tenant_id=self.tenant_id,
            invoice_id=invoice_id,
            description=data.description,
            quantity=data.quantity,
            unit_price=data.unit_price,
            amount=amount,
        )

    def _apply_totals(self, invoice: Invoice, items: Iterable[InvoiceLineItem]) -> None:
        subtotal = sum((item.amount for item in items), Decimal(0)).quantize(_CENTS)
        tax = (subtotal * invoice.tax_rate / Decimal(100)).quantize(_CENTS)
        invoice.subtotal = subtotal
        invoice.tax_amount = tax
        invoice.total = (subtotal + tax).quantize(_CENTS)

    # ── Invoices ────────────────────────────────────────────────────
    async def create_invoice(self, data: InvoiceCreate) -> Invoice:
        number = f"INV-{await self.repo.count(self.tenant_id) + 1:04d}"
        invoice = Invoice(
            tenant_id=self.tenant_id,
            invoice_number=number,
            client_name=data.client_name,
            client_id=data.client_id,
            matter_id=data.matter_id,
            issue_date=data.issue_date,
            due_date=data.due_date,
            currency=data.currency,
            tax_rate=data.tax_rate,
            notes=data.notes,
            created_by=self.user_id,
        )
        invoice.line_items = [self._line(invoice.id, li) for li in data.line_items]
        self.repo.add(invoice)
        self._apply_totals(invoice, invoice.line_items)
        await self.session.flush()
        return await self._require(invoice.id, detail=True)

    async def prepare_matter_invoice(self, matter_id: uuid.UUID, data: MatterInvoicePrepare) -> Invoice:
        matter = (await self.session.execute(select(Matter).where(
            Matter.id == matter_id, Matter.tenant_id == self.tenant_id, Matter.deleted_at.is_(None)
        ))).scalar_one_or_none()
        if matter is None:
            raise NotFoundError("Matter not found.")
        stmt = select(MatterFeeEvent).where(
            MatterFeeEvent.matter_id == matter_id,
            MatterFeeEvent.tenant_id == self.tenant_id,
            MatterFeeEvent.deleted_at.is_(None),
            MatterFeeEvent.status == FeeEventStatus.UNBILLED,
        )
        if data.event_ids:
            stmt = stmt.where(MatterFeeEvent.id.in_(data.event_ids))
        events = list((await self.session.execute(stmt.order_by(MatterFeeEvent.occurred_on))).scalars().all())
        if not events:
            raise ValidationError("This matter has no selected unbilled fee events.")
        client = None
        if matter.client_id:
            client = (await self.session.execute(select(Client).where(
                Client.id == matter.client_id, Client.tenant_id == self.tenant_id, Client.deleted_at.is_(None)
            ))).scalar_one_or_none()
        tax_rate = Decimal(0) if client and client.reverse_charge else Decimal(18 if client and client.gst_applicable else 0)
        invoice = await self.create_invoice(InvoiceCreate(
            client_id=matter.client_id, client_name=client.display_name if client else matter.client_name,
            matter_id=matter.id, due_date=data.due_date, tax_rate=tax_rate, notes=data.notes,
            line_items=[LineItemCreate(description=e.description, quantity=Decimal(1), unit_price=e.amount) for e in events],
        ))
        for event in events:
            event.status = FeeEventStatus.INVOICED
            event.invoice_id = invoice.id
        await self.session.flush()
        return await self._require(invoice.id, detail=True)

    async def list_invoices(
        self, status: InvoiceStatus | None, limit: int, offset: int,
        *, client_id: uuid.UUID | None = None, matter_id: uuid.UUID | None = None,
    ) -> list[Invoice]:
        return await self.repo.list(self.tenant_id, status, limit, offset, client_id=client_id, matter_id=matter_id)

    async def get_invoice(self, invoice_id: uuid.UUID) -> Invoice:
        return await self._require(invoice_id, detail=True)

    async def update_invoice(self, invoice_id: uuid.UUID, data: InvoiceUpdate) -> Invoice:
        invoice = await self._require(invoice_id, detail=True)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(invoice, field, value)
        if "tax_rate" in data.model_dump(exclude_unset=True):
            self._apply_totals(invoice, invoice.line_items)  # tax changed → recompute
        return await self._require(invoice_id, detail=True)

    async def delete_invoice(self, invoice_id: uuid.UUID) -> None:
        from datetime import UTC, datetime

        invoice = await self._require(invoice_id)
        invoice.deleted_at = datetime.now(UTC)

    # ── Line items ──────────────────────────────────────────────────
    async def add_line_item(self, invoice_id: uuid.UUID, data: LineItemCreate) -> Invoice:
        invoice = await self._require(invoice_id, detail=True)
        if invoice.status not in (InvoiceStatus.DRAFT, InvoiceStatus.SENT):
            raise ValidationError("Line items can only change on a draft or sent invoice.")
        invoice.line_items.append(self._line(invoice.id, data))
        self._apply_totals(invoice, invoice.line_items)
        await self.session.flush()
        return await self._require(invoice_id, detail=True)

    async def remove_line_item(self, item_id: uuid.UUID) -> Invoice:
        item = await self.repo.get_line_item(self.tenant_id, item_id)
        if item is None:
            raise NotFoundError("Line item not found.")
        invoice = await self._require(item.invoice_id, detail=True)
        remaining = [li for li in invoice.line_items if li.id != item_id]
        await self.repo.delete(item)
        self._apply_totals(invoice, remaining)
        await self.session.flush()
        return await self._require(item.invoice_id, detail=True)

    # ── Payment ─────────────────────────────────────────────────────
    async def pay(self, invoice_id: uuid.UUID, provider: PaymentProvider) -> Payment:
        invoice = await self._require(invoice_id)
        if invoice.status == InvoiceStatus.CANCELLED:
            raise ValidationError("This invoice is cancelled.")
        balance = invoice.total - invoice.amount_paid
        if balance <= 0:
            raise ValidationError("This invoice is already fully paid.")
        payments = PaymentService(self.session, self.user_id, self.tenant_id, provider)
        return await payments.create_order(
            OrderCreate(
                amount=int((balance * 100).to_integral_value()),  # rupees → paise
                currency=invoice.currency,
                description=f"Invoice {invoice.invoice_number}",
                receipt=invoice.invoice_number,
                matter_id=invoice.matter_id,
                invoice_id=invoice.id,
            )
        )

    async def reconcile(self, invoice_id: uuid.UUID) -> Invoice:
        invoice = await self._require(invoice_id, detail=True)
        paid_paise = await PaymentRepository(self.session).paid_total_for_invoice(
            self.tenant_id, invoice_id
        )
        invoice.amount_paid = (Decimal(paid_paise) / Decimal(100)).quantize(_CENTS)
        if invoice.total > 0 and invoice.amount_paid >= invoice.total:
            invoice.status = InvoiceStatus.PAID
        return invoice
