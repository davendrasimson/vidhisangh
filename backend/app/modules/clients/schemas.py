"""Pydantic schemas for the client master and KYC."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.clients.models import ClientKind, ClientStatus, GstTreatment, KycRequestStatus, KycStatus

# Every editable client field, shared by create/update/KYC payloads.
_EDITABLE_FIELDS = (
    "display_name", "client_code", "status", "first_name", "last_name", "date_of_birth",
    "father_or_spouse_name", "occupation", "legal_name", "trade_name", "business_type", "cin",
    "incorporation_date", "contact_person_name", "contact_person_designation",
    "contact_person_email", "contact_person_mobile", "pan", "email", "phone", "mobile",
    "address_line1", "address_line2", "city", "state", "state_code", "pincode", "country",
    "consent_email", "consent_mobile", "consent_whatsapp", "gst_applicable", "gstin",
    "gst_treatment", "reverse_charge", "place_of_supply_code", "tds_applicable", "tds_section",
    "tds_rate", "tan", "msme_udyam", "notes", "tags",
)
# What a client may set on the public KYC form (no status, code, notes, tags).
# Reverse charge is a consequence of the law (RCM on legal services to a
# business entity), decided by the firm's defaults — never by the client's tick.
KYC_FIELDS = tuple(
    f for f in _EDITABLE_FIELDS if f not in ("client_code", "status", "notes", "tags", "reverse_charge")
)


class _ClientFields(BaseModel):
    display_name: str | None = Field(default=None, max_length=300)
    client_code: str | None = Field(default=None, max_length=30)
    status: ClientStatus | None = None
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    date_of_birth: date | None = None
    father_or_spouse_name: str | None = Field(default=None, max_length=200)
    occupation: str | None = Field(default=None, max_length=120)
    legal_name: str | None = Field(default=None, max_length=300)
    trade_name: str | None = Field(default=None, max_length=300)
    business_type: str | None = Field(default=None, max_length=40)
    cin: str | None = Field(default=None, max_length=21)
    incorporation_date: date | None = None
    contact_person_name: str | None = Field(default=None, max_length=200)
    contact_person_designation: str | None = Field(default=None, max_length=120)
    contact_person_email: str | None = Field(default=None, max_length=254)
    contact_person_mobile: str | None = Field(default=None, max_length=20)
    pan: str | None = Field(default=None, max_length=10)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=20)
    mobile: str | None = Field(default=None, max_length=20)
    address_line1: str | None = Field(default=None, max_length=300)
    address_line2: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    state_code: str | None = Field(default=None, max_length=2)
    pincode: str | None = Field(default=None, max_length=10)
    country: str | None = Field(default=None, max_length=60)
    consent_email: bool | None = None
    consent_mobile: bool | None = None
    consent_whatsapp: bool | None = None
    gst_applicable: bool | None = None
    gstin: str | None = Field(default=None, max_length=15)
    gst_treatment: GstTreatment | None = None
    reverse_charge: bool | None = None
    place_of_supply_code: str | None = Field(default=None, max_length=2)
    tds_applicable: bool | None = None
    tds_section: str | None = Field(default=None, max_length=10)
    tds_rate: float | None = Field(default=None, ge=0, le=30)
    tan: str | None = Field(default=None, max_length=10)
    msme_udyam: str | None = Field(default=None, max_length=25)
    notes: str | None = Field(default=None, max_length=5000)
    tags: list[str] | None = None

    @field_validator("pan", "gstin", "tan", "cin", "msme_udyam")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.strip().upper().replace(" ", "") or None if v else v

    @field_validator("email", "contact_person_email")
    @classmethod
    def _lower(cls, v: str | None) -> str | None:
        return v.strip().lower() or None if v else v


class ClientCreate(_ClientFields):
    kind: ClientKind
    display_name: str = Field(min_length=1, max_length=300)


class ClientUpdate(_ClientFields):
    """Partial update — only the fields sent change."""

    kind: ClientKind | None = None


class ValidationIssue(BaseModel):
    field: str
    message: str
    severity: str = "error"


class ClientSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: ClientKind
    status: ClientStatus
    client_code: str | None
    display_name: str
    email: str | None
    mobile: str | None
    city: str | None
    state: str | None
    pan: str | None
    gstin: str | None
    gst_applicable: bool
    tds_applicable: bool
    kyc_status: KycStatus
    updated_at: datetime
    created_at: datetime


class ClientRead(ClientSummary):
    first_name: str | None
    last_name: str | None
    date_of_birth: date | None
    father_or_spouse_name: str | None
    occupation: str | None
    legal_name: str | None
    trade_name: str | None
    business_type: str | None
    cin: str | None
    incorporation_date: date | None
    contact_person_name: str | None
    contact_person_designation: str | None
    contact_person_email: str | None
    contact_person_mobile: str | None
    phone: str | None
    address_line1: str | None
    address_line2: str | None
    state_code: str | None
    pincode: str | None
    country: str
    consent_email: bool
    consent_mobile: bool
    consent_whatsapp: bool
    consent_recorded_at: datetime | None
    consent_source: str | None
    gst_treatment: GstTreatment
    reverse_charge: bool
    place_of_supply_code: str | None
    tds_section: str | None
    tds_rate: float | None
    tan: str | None
    msme_udyam: str | None
    kyc_verified_at: datetime | None
    kyc_verified_by: uuid.UUID | None
    notes: str | None
    tags: list[str]
    created_by: uuid.UUID
    updated_by: uuid.UUID
    # Findings from the validation rules against the current record.
    issues: list[ValidationIssue] = Field(default_factory=list)


# ── KYC ─────────────────────────────────────────────────────────────
class KycRequestCreate(BaseModel):
    send_to_email: str | None = Field(default=None, max_length=254)
    send_to_mobile: str | None = Field(default=None, max_length=20)
    message: str | None = Field(default=None, max_length=2000)
    expires_in_days: int = Field(default=14, ge=1, le=90)


class KycRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    client_id: uuid.UUID
    status: KycRequestStatus
    sent_to_email: str | None
    sent_to_mobile: str | None
    message: str | None
    expires_at: datetime
    submitted_at: datetime | None
    applied_at: datetime | None
    initiated_by: uuid.UUID
    created_at: datetime
    issues: list[ValidationIssue] = Field(default_factory=list)
    # The shareable link — the initiator may send it by any channel.
    url: str | None = None


class KycRequestDetail(KycRequestRead):
    prefill: dict[str, Any]
    submitted_data: dict[str, Any] | None
    # Field-by-field: what the record holds now vs what the client submitted.
    changes: list[dict[str, Any]] = Field(default_factory=list)


class KycPublicView(BaseModel):
    """What the public form receives: who is asking, what to fill."""

    firm_name: str
    client_kind: ClientKind
    display_name: str
    message: str | None
    expires_at: datetime
    status: KycRequestStatus
    prefill: dict[str, Any]
    tds_sections: list[dict[str, Any]]
    business_types: list[str]
    states: list[dict[str, str]]


class KycSubmission(_ClientFields):
    """The client's answers. Consent is explicit here."""

    consent_email: bool = False
    consent_mobile: bool = False
    consent_whatsapp: bool = False
    declaration_accepted: bool = Field(description="The client confirms the details are true.")


class KycSubmitResult(BaseModel):
    status: KycRequestStatus
    issues: list[ValidationIssue]
    message: str


class KycApply(BaseModel):
    """Which submitted fields to apply; default all."""

    fields: list[str] | None = None
    mark_verified: bool = True
