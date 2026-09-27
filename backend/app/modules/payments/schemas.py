"""Pydantic schemas for the payments module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.payments.models import PaymentStatus


class OrderCreate(BaseModel):
    amount: int = Field(ge=100, description="Amount in the smallest unit (paise for INR).")
    currency: str = Field(default="INR", min_length=3, max_length=3)
    description: str | None = Field(default=None, max_length=300)
    receipt: str | None = Field(default=None, max_length=120)
    matter_id: uuid.UUID | None = None
    invoice_id: uuid.UUID | None = None


class OrderResponse(BaseModel):
    """Everything the client needs to open Razorpay Checkout."""

    payment_id: uuid.UUID       # our record id
    order_id: str               # gateway order id
    key_id: str                 # gateway public key
    amount: int
    currency: str
    provider: str


class PaymentVerify(BaseModel):
    razorpay_payment_id: str = Field(min_length=1, max_length=80)
    razorpay_signature: str = Field(min_length=1, max_length=256)


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    amount: int
    currency: str
    status: PaymentStatus
    provider: str
    provider_order_id: str
    provider_payment_id: str | None
    receipt: str | None
    description: str | None
    matter_id: uuid.UUID | None
    invoice_id: uuid.UUID | None
    paid_at: datetime | None
    created_at: datetime
