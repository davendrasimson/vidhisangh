"""Legal news domain model (Phase 4) — global shared feed."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import AuditedBase


class NewsCategory(StrEnum):
    JUDGMENT = "judgment"
    LEGISLATION = "legislation"
    NOTIFICATION = "notification"
    CIRCULAR = "circular"
    NEWS = "news"


class NewsItem(AuditedBase):
    __tablename__ = "news_items"

    title: Mapped[str] = mapped_column(String(400), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    category: Mapped[NewsCategory] = mapped_column(
        String(20), default=NewsCategory.NEWS, nullable=False, index=True
    )
    url: Mapped[str | None] = mapped_column(String(600), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    added_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
