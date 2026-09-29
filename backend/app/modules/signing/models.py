"""Tenant-scoped document e-signature models."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.db.base_class import TenantScopedBase


class EnvelopeStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class SignerKind(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class SignatureStepStatus(StrEnum):
    WAITING = "waiting"
    PENDING = "pending"
    SIGNED = "signed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class SignatureEnvelope(TenantScopedBase):
    __tablename__ = "signature_envelopes"

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_versions.id", ondelete="RESTRICT")
    )
    source_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[EnvelopeStatus] = mapped_column(
        String(20), nullable=False, default=EnvelopeStatus.PENDING, index=True
    )
    sequential: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    final_content_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    final_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    certificate_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    steps: Mapped[list[SignatureStep]] = relationship(
        back_populates="envelope", cascade="all, delete-orphan", order_by="SignatureStep.step_order"
    )
    events: Mapped[list[SignatureEvent]] = relationship(
        back_populates="envelope",
        cascade="all, delete-orphan",
        order_by="SignatureEvent.created_at",
    )


class SignatureStep(TenantScopedBase):
    __tablename__ = "signature_steps"
    __table_args__ = (
        UniqueConstraint("envelope_id", "step_order", name="signature_step_order_unique"),
    )

    envelope_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("signature_envelopes.id", ondelete="CASCADE"), index=True
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    signer_kind: Mapped[SignerKind] = mapped_column(String(20), nullable=False)
    signer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    signer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    signer_email: Mapped[str] = mapped_column(EncryptedString(1024), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[SignatureStepStatus] = mapped_column(
        String(20), nullable=False, default=SignatureStepStatus.WAITING, index=True
    )
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    otp_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    otp_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    session_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    signature_data: Mapped[str | None] = mapped_column(EncryptedString(800_000), nullable=True)
    consent_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(EncryptedString(512), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(EncryptedString(2000), nullable=True)

    envelope: Mapped[SignatureEnvelope] = relationship(back_populates="steps")


class SignatureEvent(TenantScopedBase):
    __tablename__ = "signature_events"

    envelope_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("signature_envelopes.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    actor_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(EncryptedString(512), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    envelope: Mapped[SignatureEnvelope] = relationship(back_populates="events")
