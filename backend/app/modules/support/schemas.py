"""API contracts for user support and platform administration."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.support.models import TicketPriority, TicketStatus


class TicketCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=20000)
    category: str = Field(
        pattern="^(bug|feature_request|ui_issue|performance|data_issue|access|billing|privacy|other)$"
    )
    priority: TicketPriority = TicketPriority.MEDIUM
    page_url: str | None = Field(default=None, max_length=1000)
    browser_context: str | None = Field(default=None, max_length=500)


class TicketMessageCreate(BaseModel):
    body: str = Field(min_length=2, max_length=10000)


class TicketMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    is_staff: bool
    body: str
    created_at: datetime


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    ticket_number: str
    requester_id: uuid.UUID
    requester_name: str
    requester_email: EmailStr
    subject: str
    description: str
    category: str
    priority: TicketPriority
    status: TicketStatus
    page_url: str | None
    assigned_to_id: uuid.UUID | None
    assigned_to_name: str | None
    first_response_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    messages: list[TicketMessageRead] = []


class TicketAdminUpdate(BaseModel):
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    assign_to_me: bool = False
    response: str | None = Field(default=None, min_length=2, max_length=10000)


class ModerationRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class AccountStatusRequest(ModerationRequest):
    active: bool


class TenantStatusRequest(ModerationRequest):
    status: str = Field(pattern="^(trial|active|suspended|cancelled)$")


class PlatformOverview(BaseModel):
    users_total: int
    users_active: int
    users_blocked: int
    users_new_30d: int
    tenants_total: int
    tenants_active: int
    tenants_suspended: int
    posts_total: int
    posts_removed: int
    tickets_open: int
    tickets_urgent: int
    tickets_overdue: int
    tickets_closed: int


class PlatformUserRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_name: str
    full_name: str
    email: EmailStr
    is_active: bool
    is_superuser: bool
    is_email_verified: bool
    mfa_enabled: bool
    last_login_at: datetime | None
    created_at: datetime
    post_count: int
    ticket_count: int


class PlatformUserDetail(PlatformUserRead):
    connection_count: int
    comment_count: int
    last_ticket_at: datetime | None


class PlatformTenantRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    plan: str
    type: str
    created_at: datetime
    user_count: int
    active_user_count: int
    matter_count: int
    invoice_count: int
    ticket_count: int


class PlatformPostRead(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    title: str | None
    content: str
    visibility: str
    like_count: int
    comment_count: int
    created_at: datetime
    deleted_at: datetime | None


class AdminActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    actor_email: str
    action: str
    entity_type: str
    entity_id: str
    reason: str | None
    detail: dict | None
    created_at: datetime
