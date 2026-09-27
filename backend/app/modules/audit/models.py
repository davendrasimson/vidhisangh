"""Audit-event domain model (Phase 6) — tenant-scoped with RLS, append-only.

Deliberately **not** built on ``TenantScopedBase``: an audit row is never
soft-deleted (no ``deleted_at``) and is never updated — migration 0048 removes the
column, revokes UPDATE/DELETE from the application role and adds a trigger that
rejects both (audit A-20 / P-7). Each row carries a tamper-evident hash chain:
``entry_hash = sha256(prev_hash || canonical row content)`` (see
``app.modules.audit.service``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AuditEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    __tablename__ = "audit_events"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    actor_label: Mapped[str | None] = mapped_column(String(320), nullable=True)  # email/name snapshot
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)  # e.g. "subscription.changed"
    entity_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    summary: Mapped[str] = mapped_column(String(400), nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Tamper-evident chain (per tenant): hash of the previous row and of this row.
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
