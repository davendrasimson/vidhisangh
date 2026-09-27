"""Feature-flag domain model (Phase 6) — tenant-scoped with RLS."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import TenantScopedBase


class FeatureFlag(TenantScopedBase):
    """A tenant's override for a catalog flag. Absence of a row = catalog default."""

    __tablename__ = "feature_flags"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_feature_flag_tenant_key"),
    )

    key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
