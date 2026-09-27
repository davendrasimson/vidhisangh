"""Privacy-programme models (tenant-scoped, RLS).

``ClientConsentEvent`` is the append-only consent ledger required by DPDP
s.6: every grant *and* every withdrawal is a new row, so a withdrawal never
destroys the evidence that consent was once given. The boolean
``consent_*`` columns on ``clients`` are a derived cache of the latest event
per purpose.

``PrivacyRequest`` records the exercise of a Data Principal's rights
(s.11 access, s.12 correction/erasure, s.13 grievance) whether raised by
staff on the client's behalf or by the client through the portal.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import TenantScopedBase


class ConsentPurpose(StrEnum):
    CONTACT_EMAIL = "contact_email"
    CONTACT_SMS = "contact_sms"
    CONTACT_WHATSAPP = "contact_whatsapp"
    PROCESSING_CASE = "processing_case"
    PROCESSING_BILLING = "processing_billing"
    PROCESSING_FILING = "processing_filing"
    MARKETING = "marketing"
    # DPDP s.9: verifiable consent of the parent/guardian of a minor.
    GUARDIAN_CONSENT = "guardian_consent"


class ConsentSource(StrEnum):
    STAFF = "staff"
    KYC_FORM = "kyc_form"
    PORTAL = "portal"


# Client boolean cache column ↔ consent purpose.
CONSENT_FLAG_PURPOSES: dict[str, ConsentPurpose] = {
    "consent_email": ConsentPurpose.CONTACT_EMAIL,
    "consent_mobile": ConsentPurpose.CONTACT_SMS,
    "consent_whatsapp": ConsentPurpose.CONTACT_WHATSAPP,
}


class ClientConsentEvent(TenantScopedBase):
    __tablename__ = "client_consent_events"
    __table_args__ = (
        Index("ix_consent_events_client_purpose", "client_id", "purpose", "recorded_at"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[ConsentPurpose] = mapped_column(String(24), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[ConsentSource] = mapped_column(String(12), nullable=False)
    notice_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Coarsened submitter address (sha256 prefix + /24) — never the raw IP.
    ip_coarse: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)


class PrivacyRequestKind(StrEnum):
    ACCESS = "access"
    CORRECTION = "correction"
    ERASURE = "erasure"
    GRIEVANCE = "grievance"


class PrivacyRequestStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class PrivacyRequestSource(StrEnum):
    STAFF = "staff"
    PORTAL = "portal"


class PrivacyRequest(TenantScopedBase):
    __tablename__ = "privacy_requests"

    kind: Mapped[PrivacyRequestKind] = mapped_column(String(12), nullable=False, index=True)
    status: Mapped[PrivacyRequestStatus] = mapped_column(
        String(12), nullable=False, default=PrivacyRequestStatus.OPEN, index=True
    )
    source: Mapped[PrivacyRequestSource] = mapped_column(String(8), nullable=False)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    matter_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    subject_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    subject_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
