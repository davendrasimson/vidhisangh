"""Billing domain models (Phase 5) — tenant-scoped with RLS."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.db.base_class import TenantScopedBase


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class InvoiceDocumentType(StrEnum):
    PROFORMA = "proforma"
    TAX_INVOICE = "tax_invoice"
    CREDIT_NOTE = "credit_note"


class TimeEntryStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    BILLED = "billed"


class TimeEntrySource(StrEnum):
    MANUAL = "manual"
    IMPORT = "import"


class Invoice(TenantScopedBase):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_number", name="invoice_number_per_tenant"),
    )

    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False)
    document_type: Mapped[InvoiceDocumentType] = mapped_column(
        String(24), default=InvoiceDocumentType.TAX_INVOICE, nullable=False, index=True
    )
    client_name: Mapped[str] = mapped_column(String(200), nullable=False)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        String(20), default=InvoiceStatus.DRAFT, nullable=False, index=True
    )
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)  # GST %
    # The client's tax position when the invoice was made (from the client master),
    # so a later change to the client does not rewrite an issued invoice.
    client_gstin: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    gst_treatment: Mapped[str | None] = mapped_column(String(30), nullable=True)
    place_of_supply_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # Our GST state (first two digits of the firm's GSTIN): same as the place of
    # supply → CGST + SGST, otherwise IGST.
    supplier_state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    reverse_charge: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tds_section: Mapped[str | None] = mapped_column(String(10), nullable=True)
    tds_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_code: Mapped[str] = mapped_column(
        String(24), nullable=False, unique=True, index=True
    )
    payment_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    source_proforma_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    converted_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    next_follow_up_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    last_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    line_items: Mapped[list[InvoiceLineItem]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )

    @property
    def place_of_supply(self) -> str | None:
        from app.modules.clients.kyc import GST_STATE_CODES
        code = self.place_of_supply_code
        return f"{code} – {GST_STATE_CODES[code]}" if code in GST_STATE_CODES else code

    @property
    def tax_split(self) -> dict[str, Decimal] | None:
        """CGST + SGST within the state, IGST across states; None when we cannot tell."""
        if not self.tax_amount or not self.place_of_supply_code or not self.supplier_state_code:
            return None
        if self.place_of_supply_code != self.supplier_state_code:
            return {"igst": self.tax_amount}
        cgst = (self.tax_amount / 2).quantize(Decimal("0.01"))
        return {"cgst": cgst, "sgst": self.tax_amount - cgst}

    @property
    def tds_amount(self) -> Decimal | None:
        """What the client is expected to deduct at source (on the fee, not the GST)."""
        if not self.tds_rate:
            return None
        return (self.subtotal * self.tds_rate / Decimal(100)).quantize(Decimal("0.01"))
    follow_ups: Mapped[list[InvoiceFollowUp]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceFollowUp.created_at.desc()",
    )
    receipts: Mapped[list[BillingReceipt]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="BillingReceipt.received_on.desc()",
    )


class InvoiceLineItem(TenantScopedBase):
    __tablename__ = "invoice_line_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="line_items")


class TimeEntry(TenantScopedBase):
    """Counsel work recorded against a matter/client and later billed once."""

    __tablename__ = "time_entries"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    activity_type: Mapped[str] = mapped_column(
        String(80), nullable=False, default="Professional work"
    )
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    status: Mapped[TimeEntryStatus] = mapped_column(
        String(20), nullable=False, default=TimeEntryStatus.DRAFT, index=True
    )
    source: Mapped[TimeEntrySource] = mapped_column(
        String(20), nullable=False, default=TimeEntrySource.MANUAL
    )
    import_batch: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class InvoiceFollowUp(TenantScopedBase):
    __tablename__ = "invoice_follow_ups"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(24), nullable=False, default="phone")
    remark: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(300), nullable=True)
    next_follow_up_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="follow_ups")


class BillingReceipt(TenantScopedBase):
    __tablename__ = "billing_receipts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "receipt_number", name="receipt_number_per_tenant"),
    )

    receipt_number: Mapped[str] = mapped_column(String(40), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    received_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_method: Mapped[str] = mapped_column(String(40), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_code: Mapped[str] = mapped_column(
        String(24), nullable=False, unique=True, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="receipts")
