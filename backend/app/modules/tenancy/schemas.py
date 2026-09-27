"""Pydantic schemas for the tenancy module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.tenancy.models import PlanTier, TenantStatus, TenantType


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    type: TenantType
    status: TenantStatus
    plan: PlanTier
    region: str
    created_at: datetime
    cancelled_at: datetime | None = None
    erase_after: datetime | None = None


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    type: TenantType | None = None
    primary_contact_email: str | None = None
    settings: dict | None = None


class TenantNotificationSettings(BaseModel):
    """``tenants.settings["notifications"]`` — the firm's own Slack incoming
    webhook. ``null`` removes it. Validated as a public https URL (SSRF guard)."""

    slack_webhook: str | None = Field(default=None, max_length=500)


class TenantNotificationSettingsRead(BaseModel):
    slack_webhook_configured: bool
    # Only the host is echoed back — the full URL is a bearer credential.
    slack_webhook_host: str | None = None


# ── Privacy (privacy agent) ─────────────────────────────────────────
class TenantPrivacySettings(BaseModel):
    """``tenants.settings["privacy"]`` — the firm's own DPDP programme facts:
    its grievance contact as a Data Fiduciary for its clients, and the
    retention period it applies to closed matters."""

    data_protection_contact_name: str | None = Field(default=None, max_length=200)
    data_protection_contact_email: str | None = Field(default=None, max_length=320)
    data_protection_contact_phone: str | None = Field(default=None, max_length=30)
    # Years a closed matter (and the client record behind it) is retained.
    matter_retention_years: int | None = Field(default=None, ge=1, le=30)
    # Whether new users of this firm are listed in the cross-tenant directory.
    directory_listing_default: bool | None = None


class TenantPrivacySettingsRead(TenantPrivacySettings):
    matter_retention_years: int = 8
    directory_listing_default: bool = False
    dpa_version: str
    processor_name: str = "VidhiSangh"
    sub_processors: list[str]


class TenantDeleteRequest(BaseModel):
    confirm_slug: str = Field(min_length=1, max_length=80, description="Type the organisation slug to confirm.")
    password: str = Field(min_length=1, max_length=128)


class TenantDeleteResult(BaseModel):
    status: TenantStatus
    cancelled_at: datetime
    erase_after: datetime
    users_disabled: int
