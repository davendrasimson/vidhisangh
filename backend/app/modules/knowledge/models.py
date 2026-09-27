"""Knowledge base domain model (Phase 5) — tenant-scoped with RLS."""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import JSON, Date, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import TenantScopedBase


class KnowledgeCategory(StrEnum):
    TEMPLATE = "template"
    PRECEDENT = "precedent"
    SOP = "sop"
    CHECKLIST = "checklist"
    NOTE = "note"


class KnowledgeItem(TenantScopedBase):
    __tablename__ = "knowledge_items"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[KnowledgeCategory] = mapped_column(
        String(20), default=KnowledgeCategory.NOTE, nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    practice_area: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    reviewed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    attachments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
