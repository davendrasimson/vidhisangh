"""Pydantic schemas for the billing module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.billing.models import InvoiceStatus


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
    created_at: datetime


class InvoiceDetail(InvoiceRead):
    line_items: list[LineItemRead] = Field(default_factory=list)
