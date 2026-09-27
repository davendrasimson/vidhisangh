"""Pydantic schemas for the privacy module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.privacy.models import (
    PrivacyRequestKind,
    PrivacyRequestSource,
    PrivacyRequestStatus,
)


class GrievanceOfficer(BaseModel):
    name: str
    email: str
    address: str


class PrivacyNoticeRead(BaseModel):
    """Public: what a Data Principal needs before deciding (DPDP s.5)."""

    terms_version: str
    notice_version: str
    grievance_officer: GrievanceOfficer
    notice_url: str
    terms_url: str
    legal_hold_years: int
    tenant_erase_grace_days: int
    retention_days: dict[str, int]
    data_protection_board_url: str = "https://www.dpb.gov.in/"
    sub_processors: list[dict[str, str]]
    hosting_region: str = "India (ap-south-1)"


class UserDeleteRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class UserDeleteResult(BaseModel):
    user_id: uuid.UUID
    erased: bool
    anonymised_email: str
    sessions_revoked: int
    api_keys_revoked: int
    note: str = (
        "Audit-log rows naming this account are retained (DPDP s.8(7)/s.17(1)(a): "
        "legal obligation and the firm's own record-keeping)."
    )


class PrivacyRequestCreate(BaseModel):
    kind: PrivacyRequestKind
    message: str = Field(min_length=1, max_length=5000)
    client_id: uuid.UUID | None = None
    matter_id: uuid.UUID | None = None
    subject_name: str | None = Field(default=None, max_length=200)
    subject_email: str | None = Field(default=None, max_length=320)


class PrivacyRequestUpdate(BaseModel):
    status: PrivacyRequestStatus
    resolution_note: str | None = Field(default=None, max_length=5000)


class PrivacyRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: PrivacyRequestKind
    status: PrivacyRequestStatus
    source: PrivacyRequestSource
    client_id: uuid.UUID | None
    matter_id: uuid.UUID | None
    subject_name: str | None
    subject_email: str | None
    message: str
    created_by: uuid.UUID | None
    due_at: datetime
    resolved_at: datetime | None
    resolved_by: uuid.UUID | None
    resolution_note: str | None
    created_at: datetime
