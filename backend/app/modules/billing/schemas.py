"""Pydantic schemas for the billing module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.billing.models import InvoiceDocumentType, InvoiceStatus


class LineItemCreate(BaseModel):
    description: str = Field(min_length=1, max_length=300)
    quantity: Decimal = Field(default=Decimal(1), gt=0)
    unit_price: Decimal = Field(ge=0)


class MatterInvoicePrepare(BaseModel):
    event_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)


class LineItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class InvoiceCreate(BaseModel):
    client_name: str = Field(min_length=1, max_length=200)
    client_id: uuid.UUID | None = None
    matter_id: uuid.UUID | None = None
    issue_date: date | None = None
    due_date: date | None = None
    currency: str = Field(default="INR", min_length=3, max_length=3)
    tax_rate: Decimal = Field(default=Decimal(0), ge=0, le=100)
    notes: str | None = Field(default=None, max_length=5000)
    line_items: list[LineItemCreate] = Field(default_factory=list, max_length=100)
    document_type: InvoiceDocumentType = InvoiceDocumentType.TAX_INVOICE


class InvoiceUpdate(BaseModel):
    client_name: str | None = Field(default=None, min_length=1, max_length=200)
    status: InvoiceStatus | None = None
    issue_date: date | None = None
    due_date: date | None = None
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=5000)


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    invoice_number: str
    document_type: InvoiceDocumentType
    client_name: str
    client_id: uuid.UUID | None
    matter_id: uuid.UUID | None
    status: InvoiceStatus
    issue_date: date | None
    due_date: date | None
    currency: str
    tax_rate: Decimal
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    amount_paid: Decimal
    notes: str | None
    verification_code: str
    payment_token: str
    source_proforma_id: uuid.UUID | None
    converted_invoice_id: uuid.UUID | None
    next_follow_up_on: date | None
    last_follow_up_at: datetime | None
    created_at: datetime


class FollowUpCreate(BaseModel):
    channel: str = Field(default="phone", min_length=2, max_length=24)
    remark: str = Field(min_length=2, max_length=5000)
    outcome: str | None = Field(default=None, max_length=300)
    next_follow_up_on: date | None = None


class FollowUpRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    invoice_id: uuid.UUID
    channel: str
    remark: str
    outcome: str | None
    next_follow_up_on: date | None
    created_at: datetime


class ReceiptCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    received_on: date | None = None
    payment_method: str = Field(default="bank_transfer", min_length=2, max_length=40)
    reference: str | None = Field(default=None, max_length=160)
    remarks: str | None = Field(default=None, max_length=2000)


class ReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    receipt_number: str
    invoice_id: uuid.UUID
    payment_id: uuid.UUID | None
    amount: Decimal
    received_on: date
    payment_method: str
    reference: str | None
    remarks: str | None
    verification_code: str
    created_at: datetime


class InvoiceDetail(InvoiceRead):
    line_items: list[LineItemRead] = Field(default_factory=list)
    follow_ups: list[FollowUpRead] = Field(default_factory=list)
    receipts: list[ReceiptRead] = Field(default_factory=list)


class BillingSummary(BaseModel):
    pending_count: int
    pending_total: Decimal
    overdue_count: int
    follow_ups_due: int
    receipts_total: Decimal


class BillingBranding(BaseModel):
    template_id: str = Field(default="classic", pattern="^(classic|modern|minimal)$")
    legal_name: str = Field(default="", max_length=200)
    address: str = Field(default="", max_length=1000)
    email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=40)
    gstin: str = Field(default="", max_length=20)
    pan: str = Field(default="", max_length=20)
    logo_url: str = Field(default="", max_length=500)
    accent_color: str = Field(default="#215dcc", pattern="^#[0-9A-Fa-f]{6}$")
    bank_details: str = Field(default="", max_length=2000)
    payment_terms: str = Field(default="Payment due within 15 days.", max_length=1000)
    footer: str = Field(default="This is a system-generated document.", max_length=1000)
    signature_name: str = Field(default="", max_length=200)
    proforma_prefix: str = Field(default="PF", min_length=1, max_length=10)
    invoice_prefix: str = Field(default="INV", min_length=1, max_length=10)
    credit_note_prefix: str = Field(default="CN", min_length=1, max_length=10)
    receipt_prefix: str = Field(default="RCT", min_length=1, max_length=10)


class PublicInvoiceRead(BaseModel):
    invoice_number: str
    document_type: InvoiceDocumentType
    client_name: str
    status: InvoiceStatus
    issue_date: date | None
    due_date: date | None
    currency: str
    subtotal: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total: Decimal
    amount_paid: Decimal
    notes: str | None
    verification_code: str
    line_items: list[LineItemRead]
    branding: BillingBranding


class BillingVerification(BaseModel):
    valid: bool
    document_type: InvoiceDocumentType | str
    number: str
    firm: str
    client_name: str | None = None
    issue_date: date | None = None
    received_on: date | None = None
    total: Decimal
    currency: str
    status: str
