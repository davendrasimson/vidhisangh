"""Billing domain models (Phase 5) — tenant-scoped with RLS."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
