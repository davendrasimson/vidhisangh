"""Client master models (tenant-scoped)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import TenantScopedBase


class ClientKind(StrEnum):
    INDIVIDUAL = "individual"
    BUSINESS = "business"


class ClientStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class GstTreatment(StrEnum):
    """How the client stands under GST — drives invoicing."""

    UNREGISTERED = "unregistered"
    REGISTERED_REGULAR = "registered_regular"
    REGISTERED_COMPOSITION = "registered_composition"
    SEZ = "sez"
    OVERSEAS = "overseas"
    GOVERNMENT = "government"


class KycStatus(StrEnum):
    NOT_STARTED = "not_started"   # no form sent yet
    PENDING = "pending"           # form sent, waiting for the client
    SUBMITTED = "submitted"       # client submitted; initiator to review
    VERIFIED = "verified"         # reviewed and applied to the record


class KycRequestStatus(StrEnum):
    SENT = "sent"
    SUBMITTED = "submitted"
    APPLIED = "applied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Client(TenantScopedBase):
    """One client of the firm — a person or a business entity.

    Tax settings live on the client so invoices can default from them:
    GST (registered? GSTIN, treatment, reverse charge — legal services to a
    business are under RCM by default) and TDS the client deducts (section,
    rate). Consent records how the client agreed to be contacted.
    """

    __tablename__ = "clients"
    __table_args__ = (
        Index("ix_clients_tenant_name", "tenant_id", "display_name"),
        Index("ix_clients_tenant_kind", "tenant_id", "kind"),
    )

    kind: Mapped[ClientKind] = mapped_column(String(12), nullable=False)
    status: Mapped[ClientStatus] = mapped_column(String(10), default=ClientStatus.ACTIVE, nullable=False)
    client_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # What the firm calls them — a person's full name or the business's name.
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)

    # ── Individual ─────────────────────────────────────────────────
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(nullable=True)
    father_or_spouse_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # ── Business ───────────────────────────────────────────────────
    legal_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    trade_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cin: Mapped[str | None] = mapped_column(String(21), nullable=True)
    incorporation_date: Mapped[date | None] = mapped_column(nullable=True)
    contact_person_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_person_designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_person_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    contact_person_mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ── Identity & contact ─────────────────────────────────────────
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(300), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)  # GST state code
    pincode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    country: Mapped[str] = mapped_column(String(60), default="India", nullable=False)

    # ── Consent ────────────────────────────────────────────────────
    consent_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_mobile: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_whatsapp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_source: Mapped[str | None] = mapped_column(String(40), nullable=True)  # "kyc_form" / "staff"

    # ── Tax configuration ──────────────────────────────────────────
    gst_applicable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    gst_treatment: Mapped[GstTreatment] = mapped_column(
        String(24), default=GstTreatment.UNREGISTERED, nullable=False
    )
    reverse_charge: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    place_of_supply_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    tds_applicable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tds_section: Mapped[str | None] = mapped_column(String(10), nullable=True)
    tds_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    tan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    msme_udyam: Mapped[str | None] = mapped_column(String(25), nullable=True)

    # ── KYC ────────────────────────────────────────────────────────
    kyc_status: Mapped[KycStatus] = mapped_column(String(12), default=KycStatus.NOT_STARTED, nullable=False)
    kyc_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kyc_verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    kyc_requests: Mapped[list["ClientKycRequest"]] = relationship(
        back_populates="client", cascade="all, delete-orphan", order_by="ClientKycRequest.created_at.desc()"
    )


class ClientKycRequest(TenantScopedBase):
    """A KYC form sent to a client. The token authenticates the public form
    (no login); the submission is validated and held until the initiator
    reviews and applies it."""

    __tablename__ = "client_kyc_requests"

    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[KycRequestStatus] = mapped_column(String(12), default=KycRequestStatus.SENT, nullable=False)
    sent_to_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    sent_to_mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # What the client saw (prefill) and what they sent back.
    prefill: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    submitted_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Validation findings on the submission (format checks, GSTIN↔PAN, …).
    issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    initiated_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    client: Mapped[Client] = relationship(back_populates="kyc_requests")
