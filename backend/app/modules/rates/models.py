"""Counsel rate cards — tenant-scoped with RLS.

One row per (person, basis, period): "Adv. Mehta — hourly ₹6,000 from
01/04/2026", "Adv. Mehta — per hearing ₹25,000". A matter's team row may
override the card for that matter alone (see `MatterTeamMember.rate_*`).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import TenantScopedBase
from app.modules.matters.models import RateBasis


class CounselRate(TenantScopedBase):
    __tablename__ = "counsel_rates"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    basis: Mapped[RateBasis] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
