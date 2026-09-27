"""Data-access layer for documents. Filters by ``tenant_id`` explicitly
(alongside RLS) so isolation holds under the SQLite tests too."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_utils import LIKE_ESCAPE, contains
from app.modules.documents.models import (
    Document,
    DocumentFolder,
    DocumentVersion,
)


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def delete(self, obj: object) -> None:
        await self.session.delete(obj)

    # ── Folders ─────────────────────────────────────────────────────
    async def get_folder(
        self, tenant_id: uuid.UUID, folder_id: uuid.UUID
    ) -> DocumentFolder | None:
        res = await self.session.execute(
            select(DocumentFolder).where(
                DocumentFolder.id == folder_id,
                DocumentFolder.tenant_id == tenant_id,
                DocumentFolder.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def list_folders(
        self,
        tenant_id: uuid.UUID,
        parent_id: uuid.UUID | None,
        matter_id: uuid.UUID | None,
    ) -> list[DocumentFolder]:
        stmt = select(DocumentFolder).where(
            DocumentFolder.tenant_id == tenant_id,
            DocumentFolder.deleted_at.is_(None),
            DocumentFolder.parent_id == parent_id,
        )
        if matter_id is not None:
            stmt = stmt.where(DocumentFolder.matter_id == matter_id)
        res = await self.session.execute(stmt.order_by(DocumentFolder.name))
        return list(res.scalars().all())

    # ── Documents ───────────────────────────────────────────────────
    async def get_document(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        res = await self.session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.tenant_id == tenant_id,
                Document.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def list_documents(
        self,
        tenant_id: uuid.UUID,
        *,
        folder_id: uuid.UUID | None,
        matter_id: uuid.UUID | None,
        query: str | None,
        limit: int,
        offset: int,
        client_id: uuid.UUID | None = None,
    ) -> list[Document]:
        stmt = select(Document).where(
            Document.tenant_id == tenant_id, Document.deleted_at.is_(None)
        )
        if folder_id is not None:
            stmt = stmt.where(Document.folder_id == folder_id)
        if matter_id is not None:
            stmt = stmt.where(Document.matter_id == matter_id)
        if client_id is not None:
            stmt = stmt.where(Document.client_id == client_id)
        if query:
            stmt = stmt.where(Document.name.ilike(contains(query), escape=LIKE_ESCAPE))
        res = await self.session.execute(
            stmt.order_by(Document.updated_at.desc()).limit(limit).offset(offset)
        )
        return list(res.scalars().all())

    # ── Versions ────────────────────────────────────────────────────
    async def list_versions(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> list[DocumentVersion]:
        res = await self.session.execute(
            select(DocumentVersion)
            .where(
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.document_id == document_id,
            )
            .order_by(DocumentVersion.version_no.desc())
        )
        return list(res.scalars().all())

    async def get_version(
        self, tenant_id: uuid.UUID, version_id: uuid.UUID
    ) -> DocumentVersion | None:
        res = await self.session.execute(
            select(DocumentVersion).where(
                DocumentVersion.id == version_id,
                DocumentVersion.tenant_id == tenant_id,
            )
        )
        return res.scalar_one_or_none()
