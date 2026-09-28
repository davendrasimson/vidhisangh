"""Drafting models — authored documents and their versions (tenant-scoped)."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import TenantScopedBase

# Default page: A4 portrait with 1-inch margins, what Indian courts expect.
DEFAULT_PAGE: dict[str, Any] = {
    "size": "A4",
    "orientation": "portrait",
    "margins": {"top": 25.4, "right": 25.4, "bottom": 25.4, "left": 25.4},
}


class DraftStatus(StrEnum):
    DRAFT = "draft"
    FINAL = "final"


class DraftTemplate(TenantScopedBase):
    """A firm's reusable Word template, converted into the editor structure."""

    __tablename__ = "draft_templates"

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="Firm templates")
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    source_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    source_storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    source_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    page: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=lambda: dict(DEFAULT_PAGE)
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class Draft(TenantScopedBase):
    """One authored document.

    ``content_json`` is the editor's own structure (a ProseMirror document);
    everything else — the HTML for display, the DOCX export — is derived from
    it, so it is the source of truth. ``content_html`` is kept alongside so a
    draft can be shown or searched without the editor.
    """

    __tablename__ = "drafts"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
    template_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[DraftStatus] = mapped_column(
        String(10), default=DraftStatus.DRAFT, nullable=False
    )
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    content_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    page: Mapped[dict] = mapped_column(JSON, nullable=False, default=lambda: dict(DEFAULT_PAGE))
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # The library Document this draft was last filed to (DOCX); later filings
    # add versions to it rather than creating duplicates.
    library_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    versions: Mapped[list[DraftVersion]] = relationship(
        back_populates="draft", cascade="all, delete-orphan", order_by="DraftVersion.version_no"
    )


class DraftVersion(TenantScopedBase):
    """A named snapshot of a draft, taken on demand (not on every autosave)."""

    __tablename__ = "draft_versions"

    draft_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    content_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    draft: Mapped[Draft] = relationship(back_populates="versions")
