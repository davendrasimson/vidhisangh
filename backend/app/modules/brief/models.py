"""Daily brief: who was sent it, who opened it, and quiz answers (migration 0089).

Global tables (no tenant scoping): a member's brief is personal, not firm data.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import AuditedBase


class DailyBriefSend(AuditedBase):
    """One member's brief for one day: the push (claimed before sending, so a
    rerun never sends twice) and whether they opened the page.

    ``status``: sending | sent | failed | viewed (opened without a push).
    """

    __tablename__ = "daily_brief_sends"
    __table_args__ = (UniqueConstraint("user_id", "for_date", name="uq_daily_brief_user_day"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    for_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    lead: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_via: Mapped[str | None] = mapped_column(String(20), nullable=True)  # push | app


class DailyQuizAnswer(AuditedBase):
    """A member's answer to one quiz question (one attempt per question)."""

    __tablename__ = "daily_quiz_answers"
    __table_args__ = (UniqueConstraint("user_id", "quiz_id", name="uq_daily_quiz_user_question"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    quiz_id: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    for_date: Mapped[date] = mapped_column(Date, nullable=False)
    chosen: Mapped[int] = mapped_column(Integer, nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
