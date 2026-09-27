"""Client master models (tenant-scoped).

Identity data is encrypted at rest (DPDP s.8(5)): PAN, GSTIN, TAN, CIN, Udyam,
date of birth, father's/spouse's name and every phone number are
``EncryptedString`` columns, decrypted transparently by the ORM. Exact-match
search on PAN/GSTIN/email goes through HMAC blind indexes (``*_bidx``); the
ciphertext itself is never searched.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import BlindIndex, EncryptedString
from app.db.base_class import TenantScopedBase


class EncryptedDate(EncryptedString):
    """A date stored as an encrypted ISO string; exposed as ``datetime.date``."""

    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None or value == "":
            return None
        text = value.isoformat() if hasattr(value, "isoformat") else str(value)
        return super().process_bind_param(text, dialect)

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        raw = super().process_result_value(value, dialect)
        return date.fromisoformat(raw) if raw else None


class EncryptedJSON(EncryptedString):
    """A JSON document stored as encrypted text (KYC prefill / submissions)."""

    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        return super().process_bind_param(json.dumps(value, default=str), dialect)

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        raw = super().process_result_value(value, dialect)
        return json.loads(raw) if raw else None


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


class LawfulBasis(StrEnum):
    """DPDP s.4/s.7 basis on which a record is processed or a message sent."""

    CONSENT = "consent"
    CONTRACT = "contract"
    LEGAL_OBLIGATION = "legal_obligation"
    LEGITIMATE_USE = "legitimate_use"
    PUBLIC_DATA = "public_data"


# Columns whose plaintext is encrypted at rest (kept in one place so the
# migration, the export and the tests agree on the list).
ENCRYPTED_CLIENT_FIELDS: tuple[str, ...] = (
    "pan", "gstin", "tan", "cin", "msme_udyam", "date_of_birth",
    "father_or_spouse_name", "contact_person_mobile", "mobile", "phone",
)
# Fields that identify a person beyond what the engagement needs — collected
# only when a matter actually requires them (P-15).
OPTIONAL_IDENTITY_FIELDS: tuple[str, ...] = ("date_of_birth", "father_or_spouse_name", "occupation")


class Client(TenantScopedBase):
    """One client of the firm — a person or a business entity.

    Tax settings live on the client so invoices can default from them:
    GST (registered? GSTIN, treatment, reverse charge — legal services to a
    business are under RCM by default) and TDS the client deducts (section,
    rate). The ``consent_*`` flags are a cache of the latest
    ``client_consent_events`` row per purpose.
    """

    __tablename__ = "clients"
    __table_args__ = (
        Index("ix_clients_tenant_name", "tenant_id", "display_name"),
        Index("ix_clients_tenant_kind", "tenant_id", "kind"),
        Index("ix_clients_tenant_pan_bidx", "tenant_id", "pan_bidx"),
        Index("ix_clients_tenant_gstin_bidx", "tenant_id", "gstin_bidx"),
        Index("ix_clients_tenant_email_bidx", "tenant_id", "email_bidx"),
    )

    kind: Mapped[ClientKind] = mapped_column(String(12), nullable=False)
    status: Mapped[ClientStatus] = mapped_column(String(10), default=ClientStatus.ACTIVE, nullable=False)
    client_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # What the firm calls them — a person's full name or the business's name.
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)

    # ── Individual ─────────────────────────────────────────────────
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(EncryptedDate(255), nullable=True)
    father_or_spouse_name: Mapped[str | None] = mapped_column(EncryptedString(512), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # DPDP s.9 — a child's data needs the verifiable consent of a parent/guardian.
    is_minor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    guardian_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    guardian_relation: Mapped[str | None] = mapped_column(String(60), nullable=True)
    guardian_consent_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Business ───────────────────────────────────────────────────
    legal_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    trade_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cin: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    incorporation_date: Mapped[date | None] = mapped_column(nullable=True)
    contact_person_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_person_designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_person_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    contact_person_mobile: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)

    # ── Identity & contact ─────────────────────────────────────────
    pan: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    pan_bidx: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    email_bidx: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    mobile: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(300), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)  # GST state code
    pincode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    country: Mapped[str] = mapped_column(String(60), default="India", nullable=False)

    # ── Consent (cache of the latest consent event per purpose) ────
    consent_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_mobile: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_whatsapp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_source: Mapped[str | None] = mapped_column(String(40), nullable=True)  # "kyc_form" / "staff"

    # ── Tax configuration ──────────────────────────────────────────
    gst_applicable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gstin: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    gstin_bidx: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gst_treatment: Mapped[GstTreatment] = mapped_column(
        String(24), default=GstTreatment.UNREGISTERED, nullable=False
    )
    reverse_charge: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    place_of_supply_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    tds_applicable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tds_section: Mapped[str | None] = mapped_column(String(10), nullable=True)
    tds_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    tan: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    msme_udyam: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)

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

    def sync_blind_indexes(self) -> None:
        self.pan_bidx = BlindIndex.pan(self.pan)
        self.gstin_bidx = BlindIndex.gstin(self.gstin)
        self.email_bidx = BlindIndex.email(self.email)


@event.listens_for(Client, "before_insert")
@event.listens_for(Client, "before_update")
def _client_blind_indexes(mapper, connection, target: Client) -> None:  # noqa: ANN001
    target.sync_blind_indexes()


class ClientKycRequest(TenantScopedBase):
    """A KYC form sent to a client. The token authenticates the public form
    (no login); the submission is validated and held until the initiator
    reviews and applies it. The link is sent on the basis of the engagement
    contract (``lawful_basis``), not marketing consent."""

    __tablename__ = "client_kyc_requests"

    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The raw token is shown once (creation response / email) and stored only as a
    # peppered SHA-256 in ``token_hash`` (audit A-9). ``token`` is the legacy
    # clear-text column: nullable, always NULL for new rows.
    token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    status: Mapped[KycRequestStatus] = mapped_column(String(12), default=KycRequestStatus.SENT, nullable=False)
    sent_to_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    sent_to_mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lawful_basis: Mapped[LawfulBasis] = mapped_column(String(20), default=LawfulBasis.CONTRACT, nullable=False)
    # What the client saw (prefill — nulled once applied) and what they sent
    # back. Both encrypted: they duplicate the identity set.
    prefill: Mapped[dict | None] = mapped_column(EncryptedJSON(), nullable=True, default=dict)
    submitted_data: Mapped[dict | None] = mapped_column(EncryptedJSON(), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Coarsened: "<net>/24#<sha256 prefix>" — never the raw address.
    submitted_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The privacy-notice version shown with the declaration the client accepted.
    notice_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Validation findings on the submission (format checks, GSTIN↔PAN, …).
    issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    initiated_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    client: Mapped[Client] = relationship(back_populates="kyc_requests")
