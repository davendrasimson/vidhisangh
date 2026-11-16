"""Court desk: which cause lists a court has published for a day (migration 0091).

Global table: a court's cause-list index is public and the same for everyone.
``lists`` holds ``[{"label": ..., "url": ...}]`` as read from the court's own
index page; nothing from inside a list is ever stored.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import AuditedBase


class CourtCauseList(AuditedBase):
    __tablename__ = "court_cause_lists"
    __table_args__ = (UniqueConstraint("court_slug", "for_date", name="uq_court_cause_list_day"),)

    court_slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    for_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    lists: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The post in the court's official group announcing the lists (once per court and day).
    group_post_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
