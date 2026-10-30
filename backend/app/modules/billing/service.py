"""Billing service — invoices, line items, GST totals, pay + reconcile."""

from __future__ import annotations

import calendar
import secrets
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.payments import PaymentProvider
from app.modules.billing.models import (
    RECURRENCE_MONTHS,
    BillingReceipt,
    Invoice,
    InvoiceDocumentType,
    InvoiceFollowUp,
    InvoiceLineItem,
    InvoiceRecurrence,
    InvoiceStatus,
)
from app.modules.billing.repository import BillingRepository
from app.modules.billing.schemas import (
    BillingBranding,
    BillingSummary,
    FollowUpCreate,
    InvoiceCreate,
    InvoiceUpdate,
    LineItemCreate,
    MatterInvoicePrepare,
    ReceiptCreate,
)
from app.modules.clients.models import Client
from app.modules.matters.models import FeeEventKind, FeeEventStatus, Matter, MatterFeeEvent
from app.modules.payments.models import Payment, PaymentStatus
from app.modules.payments.schemas import OrderCreate
from app.modules.payments.service import PaymentService
from app.modules.tenancy.models import Tenant

_CENTS = Decimal("0.01")
_BILLING_SETTINGS_KEY = "billing"


def add_months(start: date, months: int) -> date:
    """Same day `months` later; the 31st becomes the last day of a shorter month."""
    month = start.month - 1 + months
    year, month = start.year + month // 12, month % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(start.day, last))


def next_issue_on(
    issue_date: date | None, recurrence: InvoiceRecurrence | str | None, until: date | None, *, after: date | None = None
) -> date | None:
    """When the next copy of a recurring invoice is due: the first period boundary
    after ``after`` (default: the issue date itself), or None once past ``until``."""
    if not recurrence or issue_date is None:
        return None
    months = RECURRENCE_MONTHS[InvoiceRecurrence(recurrence)]
    floor = after or issue_date
    n = 1
    while (candidate := add_months(issue_date, n * months)) <= floor:
        n += 1
    if until is not None and candidate > until:
        return None
    return candidate


def _code() -> str:
    return secrets.token_hex(12).upper()


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

    async def branding(self) -> BillingBranding:
        tenant = await self.session.scalar(select(Tenant).where(Tenant.id == self.tenant_id))
        block = dict((tenant.settings if tenant else {}).get(_BILLING_SETTINGS_KEY) or {})
        if tenant and not block.get("legal_name"):
            block["legal_name"] = tenant.name
        return BillingBranding(
            **{key: value for key, value in block.items() if key in BillingBranding.model_fields}
        )

    async def set_branding(self, data: BillingBranding) -> BillingBranding:
        tenant = await self.session.scalar(select(Tenant).where(Tenant.id == self.tenant_id))
        if tenant is None:
            raise NotFoundError("Organisation not found.")
        settings = dict(tenant.settings or {})
        settings[_BILLING_SETTINGS_KEY] = data.model_dump()
        tenant.settings = settings
        return data

    async def _number(self, kind: InvoiceDocumentType) -> str:
        branding = await self.branding()
        prefix = {
            InvoiceDocumentType.PROFORMA: branding.proforma_prefix,
            InvoiceDocumentType.TAX_INVOICE: branding.invoice_prefix,
            InvoiceDocumentType.CREDIT_NOTE: branding.credit_note_prefix,
        }[kind]
        return f"{prefix}-{await self.repo.count_type(self.tenant_id, kind) + 1:04d}"

    # ── Invoices ────────────────────────────────────────────────────
    async def _client(self, client_id: uuid.UUID | None) -> Client | None:
        if client_id is None:
            return None
        return await self.session.scalar(select(Client).where(
            Client.id == client_id, Client.tenant_id == self.tenant_id, Client.deleted_at.is_(None)))

    async def _tax_position(self, invoice: Invoice, client: Client | None, tax_rate: Decimal | None) -> None:
        """Copy the client master's tax position onto a new invoice."""
        gstin = (await self.branding()).gstin.strip()
        invoice.supplier_state_code = gstin[:2] if gstin[:2].isdigit() else None
        if client is not None:
            invoice.client_gstin = client.gstin or None
            invoice.gst_treatment = str(client.gst_treatment) if client.gst_treatment else None
            invoice.place_of_supply_code = client.place_of_supply_code or client.state_code
            invoice.reverse_charge = bool(client.reverse_charge)
            if client.tds_applicable and client.tds_rate:
                invoice.tds_section, invoice.tds_rate = client.tds_section, Decimal(str(client.tds_rate)).quantize(_CENTS)
        if tax_rate is None:
            tax_rate = Decimal(0) if client is None or client.reverse_charge else Decimal(18 if client.gst_applicable else 0)
        invoice.tax_rate = Decimal(tax_rate).quantize(_CENTS)

    async def create_invoice(self, data: InvoiceCreate) -> Invoice:
        number = await self._number(data.document_type)
        invoice = Invoice(
            tenant_id=self.tenant_id,
            invoice_number=number,
            document_type=data.document_type,
            client_name=data.client_name,
            client_id=data.client_id,
            matter_id=data.matter_id,
            issue_date=data.issue_date or date.today(),
            due_date=data.due_date,
            currency=data.currency,
            notes=data.notes,
            verification_code=_code(),
            payment_token=secrets.token_urlsafe(24),
            created_by=self.user_id,
            recurrence=data.recurrence,
            recur_until=data.recur_until,
        )
        invoice.next_issue_on = next_issue_on(invoice.issue_date, data.recurrence, data.recur_until)
        await self._tax_position(invoice, await self._client(data.client_id), data.tax_rate)
        invoice.line_items = [self._line(invoice.id, li) for li in data.line_items]
        self.repo.add(invoice)
        self._apply_totals(invoice, invoice.line_items)
        await self.session.flush()
        return await self._require(invoice.id, detail=True)

    async def prepare_matter_invoice(
        self, matter_id: uuid.UUID, data: MatterInvoicePrepare
    ) -> Invoice:
        matter = (
            await self.session.execute(
                select(Matter).where(
                    Matter.id == matter_id,
                    Matter.tenant_id == self.tenant_id,
                    Matter.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
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
        events = list(
            (await self.session.execute(stmt.order_by(MatterFeeEvent.occurred_on))).scalars().all()
        )
        if not events:
            raise ValidationError("This matter has no selected unbilled fee events.")
        client = await self._client(matter.client_id)
        invoice = await self.create_invoice(
            InvoiceCreate(
                client_id=matter.client_id,
                client_name=client.display_name if client else matter.client_name,
                matter_id=matter.id,
                due_date=data.due_date,
                notes=data.notes,
                line_items=[
                    LineItemCreate(
                        description=(f"Expense: {e.description}" if e.kind == FeeEventKind.EXPENSE else e.description)[:300],
                        quantity=Decimal(1), unit_price=e.amount,
                    )
                    for e in events
                ],
            )
        )
        for event in events:
            event.status = FeeEventStatus.INVOICED
            event.invoice_id = invoice.id
        await self.session.flush()
        return await self._require(invoice.id, detail=True)

    async def list_invoices(
        self,
        status: InvoiceStatus | None,
        limit: int,
        offset: int,
        *,
        client_id: uuid.UUID | None = None,
        matter_id: uuid.UUID | None = None,
    ) -> list[Invoice]:
        return await self.repo.list(
            self.tenant_id, status, limit, offset, client_id=client_id, matter_id=matter_id
        )

    async def pending_invoices(self, limit: int = 500) -> list[Invoice]:
        rows = await self.repo.list(self.tenant_id, None, limit, 0)
        return [
            row
            for row in rows
            if row.status not in (InvoiceStatus.PAID, InvoiceStatus.CANCELLED)
            and row.total > row.amount_paid
        ]

    async def summary(self) -> BillingSummary:
        pending = await self.pending_invoices()
        receipts = await self.repo.list_receipts(self.tenant_id, 1000, 0)
        today = date.today()
        return BillingSummary(
            pending_count=len(pending),
            pending_total=sum((row.total - row.amount_paid for row in pending), Decimal(0)),
            overdue_count=sum(1 for row in pending if row.due_date and row.due_date < today),
            follow_ups_due=sum(
                1 for row in pending if row.next_follow_up_on and row.next_follow_up_on <= today
            ),
            receipts_total=sum((row.amount for row in receipts), Decimal(0)),
        )

    async def get_invoice(self, invoice_id: uuid.UUID) -> Invoice:
        return await self._require(invoice_id, detail=True)

    async def update_invoice(self, invoice_id: uuid.UUID, data: InvoiceUpdate) -> Invoice:
        invoice = await self._require(invoice_id, detail=True)
        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "reverse_charge" and value is None:
                continue
            if field in ("tax_rate", "tds_rate") and value is not None:
                value = Decimal(value).quantize(_CENTS)
            setattr(invoice, field, value)
        if "tax_rate" in data.model_dump(exclude_unset=True):
            if invoice.tax_rate is None:  # "from the client" again
                await self._tax_position(invoice, await self._client(invoice.client_id), None)
            self._apply_totals(invoice, invoice.line_items)  # tax changed → recompute
        if data.model_fields_set & {"recurrence", "recur_until"}:
            # The next copy falls on the first period boundary after today.
            invoice.next_issue_on = next_issue_on(
                invoice.issue_date, invoice.recurrence, invoice.recur_until, after=date.today()
            )
        return await self._require(invoice_id, detail=True)

    async def delete_invoice(self, invoice_id: uuid.UUID) -> None:
        invoice = await self._require(invoice_id)
        invoice.deleted_at = datetime.now(UTC)

    # ── Follow-up / collections ─────────────────────────────────────
    async def add_follow_up(self, invoice_id: uuid.UUID, data: FollowUpCreate) -> Invoice:
        invoice = await self._require(invoice_id, detail=True)
        row = InvoiceFollowUp(
            tenant_id=self.tenant_id,
            invoice_id=invoice.id,
            channel=data.channel,
            remark=data.remark,
            outcome=data.outcome,
            next_follow_up_on=data.next_follow_up_on,
            created_by=self.user_id,
        )
        self.repo.add(row)
        invoice.last_follow_up_at = datetime.now(UTC)
        invoice.next_follow_up_on = data.next_follow_up_on
        await self.session.flush()
        return await self._require(invoice.id, detail=True)

    async def list_follow_ups(self, limit: int, offset: int) -> list[InvoiceFollowUp]:
        return await self.repo.list_follow_ups(self.tenant_id, limit, offset)

    async def list_receipts(self, limit: int, offset: int) -> list[BillingReceipt]:
        return await self.repo.list_receipts(self.tenant_id, limit, offset)

    async def _new_receipt(
        self,
        invoice: Invoice,
        *,
        amount: Decimal,
        received_on: date,
        payment_method: str,
        reference: str | None,
        remarks: str | None,
        payment_id: uuid.UUID | None = None,
    ) -> BillingReceipt:
        branding = await self.branding()
        receipt_count = await self.repo.receipt_count(self.tenant_id)
        receipt = BillingReceipt(
            tenant_id=self.tenant_id,
            receipt_number=f"{branding.receipt_prefix}-{receipt_count + 1:04d}",
            invoice_id=invoice.id,
            payment_id=payment_id,
            amount=amount.quantize(_CENTS),
            received_on=received_on,
            payment_method=payment_method,
            reference=reference,
            remarks=remarks,
            verification_code=_code(),
            created_by=self.user_id,
            invoice=invoice,
        )
        self.repo.add(receipt)
        await self.session.flush()
        return receipt

    async def record_receipt(self, invoice_id: uuid.UUID, data: ReceiptCreate) -> Invoice:
        invoice = await self._require(invoice_id, detail=True)
        balance = invoice.total - invoice.amount_paid
        if data.amount > balance:
            raise ValidationError("Receipt amount cannot exceed the outstanding balance.")
        await self._new_receipt(
            invoice,
            amount=data.amount,
            received_on=data.received_on or date.today(),
            payment_method=data.payment_method,
            reference=data.reference,
            remarks=data.remarks,
        )
        invoice.amount_paid = (invoice.amount_paid + data.amount).quantize(_CENTS)
        await self._complete_paid_document(invoice)
        await self.session.flush()
        return await self._require(invoice.id, detail=True)

    async def _complete_paid_document(self, invoice: Invoice) -> Invoice | None:
        if invoice.total <= 0 or invoice.amount_paid < invoice.total:
            return None
        invoice.status = InvoiceStatus.PAID
        if invoice.document_type != InvoiceDocumentType.PROFORMA:
            return None
        if invoice.converted_invoice_id:
            return await self._require(invoice.converted_invoice_id, detail=True)
        tax_invoice = await self.create_invoice(
            InvoiceCreate(
                client_name=invoice.client_name,
                client_id=invoice.client_id,
                matter_id=invoice.matter_id,
                issue_date=date.today(),
                due_date=date.today(),
                currency=invoice.currency,
                tax_rate=invoice.tax_rate,
                notes=f"Automatically issued against paid proforma {invoice.invoice_number}.",
                document_type=InvoiceDocumentType.TAX_INVOICE,
                line_items=[
                    LineItemCreate(
                        description=item.description,
                        quantity=item.quantity,
                        unit_price=item.unit_price,
                    )
                    for item in invoice.line_items
                ],
            )
        )
        tax_invoice.status = InvoiceStatus.PAID
        tax_invoice.amount_paid = invoice.amount_paid
        tax_invoice.source_proforma_id = invoice.id
        invoice.converted_invoice_id = tax_invoice.id
        for receipt in invoice.receipts:
            receipt.invoice_id = tax_invoice.id
        await self.session.flush()
        return tax_invoice

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
        payments = list(
            (
                await self.session.execute(
                    select(Payment).where(
                        Payment.tenant_id == self.tenant_id,
                        Payment.invoice_id == invoice_id,
                        Payment.status == PaymentStatus.PAID,
                    )
                )
            )
            .scalars()
            .all()
        )
        for payment in payments:
            if await self.repo.receipt_for_payment(self.tenant_id, payment.id) is None:
                await self._new_receipt(
                    invoice,
                    amount=Decimal(payment.amount) / Decimal(100),
                    received_on=payment.paid_at.date() if payment.paid_at else date.today(),
                    payment_method=payment.provider,
                    reference=payment.provider_payment_id,
                    remarks="Automatically generated from online payment.",
                    payment_id=payment.id,
                )
        await self.session.flush()
        fresh = await self._require(invoice_id, detail=True)
        fresh.amount_paid = sum((row.amount for row in fresh.receipts), Decimal(0)).quantize(_CENTS)
        await self._complete_paid_document(fresh)
        await self.session.flush()
        return await self._require(invoice_id, detail=True)
