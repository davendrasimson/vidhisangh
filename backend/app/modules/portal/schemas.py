"""Pydantic schemas for the client portal module."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.portal.models import ApprovalStatus


# ─── Firm-side: access management ───────────────────────────────────
class PortalAccessCreate(BaseModel):
    matter_id: uuid.UUID
    client_name: str = Field(min_length=1, max_length=200)
    client_email: EmailStr


class PortalAccessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    matter_id: uuid.UUID
    client_name: str
    client_email: str
    # The raw token is returned ONCE, in the create response; listings carry null
    # (only a hash is stored). Revoke and re-issue to get a new link.
    token: str | None = None
    is_active: bool
    expires_at: datetime | None = None
    last_accessed_at: datetime | None = None
    created_at: datetime


# ─── Firm-side: updates & approvals ─────────────────────────────────
class UpdateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=8000)


class UpdateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    body: str
    created_at: datetime


class ApprovalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    description: str | None
    status: ApprovalStatus
    response_note: str | None
    responded_at: datetime | None
    created_at: datetime


# ─── Client-side (token) ────────────────────────────────────────────
class PortalDocumentRead(BaseModel):
    id: uuid.UUID  # document id
    name: str
    size: int
    version_count: int
    updated_at: datetime


class PortalHearing(BaseModel):
    scheduled_on: datetime
    court: str | None
    purpose: str | None
    status: str


class PortalInvoice(BaseModel):
    id: uuid.UUID
    invoice_number: str
    status: str
    issue_date: date | None
    due_date: date | None
    total: float
    amount_paid: float


class PortalView(BaseModel):
    client_name: str
    matter_number: str
    matter_title: str
    status: str
    stage: str
    court: str | None
    opened_on: date | None
    hearings: list[PortalHearing] = Field(default_factory=list)
    updates: list[UpdateRead] = Field(default_factory=list)
    approvals: list[ApprovalRead] = Field(default_factory=list)
    documents: list[PortalDocumentRead] = Field(default_factory=list)
    invoices: list[PortalInvoice] = Field(default_factory=list)


class ApprovalRespond(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=1000)
