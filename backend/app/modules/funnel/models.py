"""First-party sign-up funnel: one counter per step per day (India time).

No person, IP, cookie or device is stored — only how many times each step
happened that day — so it needs no consent and no third-party tracker.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import AuditedBase


class FunnelDaily(AuditedBase):
    __tablename__ = "funnel_daily"
    __table_args__ = (UniqueConstraint("day", "step", name="uq_funnel_daily_day_step"),)

    day: Mapped[date] = mapped_column(Date, nullable=False)
    step: Mapped[str] = mapped_column(String(40), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
