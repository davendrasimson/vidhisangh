"""Client portal domain models (Phase 3) — tenant-scoped with RLS."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import TenantScopedBase


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PortalAccess(TenantScopedBase):
    """A client's tokened access to a single matter's portal.

    The raw token is shown once at creation and stored only as a peppered
    SHA-256 (``token_hash``); links expire (``expires_at``) and record their
    last use (audit A-9). The legacy clear-text ``token`` column is kept
    nullable for the migration and is always NULL for new rows.
    """

    __tablename__ = "portal_accesses"
    __table_args__ = (UniqueConstraint("token", name="portal_access_token"),)

    matter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True
    )
    client_name: Mapped[str] = mapped_column(String(200), nullable=False)
    client_email: Mapped[str] = mapped_column(String(320), nullable=False)
    token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class PortalUpdate(TenantScopedBase):
    """A firm-posted update visible to the client in the portal."""

    __tablename__ = "portal_updates"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class PortalApproval(TenantScopedBase):
    """Something the firm asks the client to approve or reject."""

    __tablename__ = "portal_approvals"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ApprovalStatus] = mapped_column(
        String(20), default=ApprovalStatus.PENDING, nullable=False, index=True
    )
    response_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class PortalDocument(TenantScopedBase):
    """A document the firm has shared into the matter's portal."""

    __tablename__ = "portal_documents"
    __table_args__ = (
        UniqueConstraint("matter_id", "document_id", name="portal_document_unique"),
    )

    matter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    shared_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
