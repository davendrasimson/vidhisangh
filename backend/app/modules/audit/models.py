"""Audit-event domain model (Phase 6) — tenant-scoped with RLS, append-only."""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import TenantScopedBase


class AuditEvent(TenantScopedBase):
    __tablename__ = "audit_events"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    actor_label: Mapped[str | None] = mapped_column(String(320), nullable=True)  # email/name snapshot
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)  # e.g. "subscription.changed"
    entity_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    summary: Mapped[str] = mapped_column(String(400), nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
