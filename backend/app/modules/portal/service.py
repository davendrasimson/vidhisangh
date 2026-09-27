"""Client portal services — firm-side management and client-side (token) access."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.storage import Storage
from app.modules.documents.models import Document, DocumentVersion
from app.modules.documents.repository import DocumentRepository
from app.modules.matters.models import Matter
from app.modules.matters.repository import MatterRepository
from app.modules.portal.models import (
    ApprovalStatus,
    PortalAccess,
    PortalApproval,
    PortalDocument,
    PortalUpdate,
)
from app.modules.portal.repository import PortalRepository
from app.modules.portal.schemas import ApprovalCreate, PortalAccessCreate, UpdateCreate
from app.modules.billing.models import Invoice, InvoiceStatus


class FirmPortalService:
    """Firm-side management (JWT + RBAC, tenant-scoped session)."""

    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.repo = PortalRepository(session)
        self.matters = MatterRepository(session)
        self.documents = DocumentRepository(session)

    async def _require_matter(self, matter_id: uuid.UUID) -> Matter:
        matter = await self.matters.get(self.tenant_id, matter_id)
        if matter is None:
            raise NotFoundError("Matter not found.")
        return matter

    async def create_access(self, data: PortalAccessCreate) -> PortalAccess:
        await self._require_matter(data.matter_id)
        access = PortalAccess(
            tenant_id=self.tenant_id,
            matter_id=data.matter_id,
            client_name=data.client_name,
            client_email=str(data.client_email),
            token=secrets.token_urlsafe(32),
            created_by=self.user_id,
        )
        self.repo.add(access)
        await self.session.flush()
        return access

    async def list_access(self, matter_id: uuid.UUID) -> list[PortalAccess]:
        return await self.repo.list_access(self.tenant_id, matter_id)

    async def revoke(self, access_id: uuid.UUID) -> PortalAccess:
        access = await self.repo.get_access(self.tenant_id, access_id)
        if access is None:
            raise NotFoundError("Portal access not found.")
        access.is_active = False
        return access

    async def post_update(self, matter_id: uuid.UUID, data: UpdateCreate) -> PortalUpdate:
        await self._require_matter(matter_id)
        update = PortalUpdate(
            tenant_id=self.tenant_id,
            matter_id=matter_id,
            title=data.title,
            body=data.body,
            created_by=self.user_id,
        )
        self.repo.add(update)
        await self.session.flush()
        return update

    async def request_approval(
        self, matter_id: uuid.UUID, data: ApprovalCreate
    ) -> PortalApproval:
        await self._require_matter(matter_id)
        approval = PortalApproval(
            tenant_id=self.tenant_id,
            matter_id=matter_id,
            title=data.title,
            description=data.description,
            created_by=self.user_id,
        )
        self.repo.add(approval)
        await self.session.flush()
        return approval

    async def list_approvals(self, matter_id: uuid.UUID) -> list[PortalApproval]:
        return await self.repo.approvals(self.tenant_id, matter_id)

    async def share_document(
        self, matter_id: uuid.UUID, document_id: uuid.UUID
    ) -> PortalDocument:
        await self._require_matter(matter_id)
        document = await self.documents.get_document(self.tenant_id, document_id)
        if document is None:
            raise NotFoundError("Document not found.")
        if document.matter_id != matter_id:
            raise ConflictError("Only documents filed to this matter can be shared in its portal.")
        existing = await self.repo.get_shared(self.tenant_id, matter_id, document_id)
        if existing is not None:
            raise ConflictError("Document is already shared with the client.")
        shared = PortalDocument(
            tenant_id=self.tenant_id,
            matter_id=matter_id,
            document_id=document_id,
            shared_by=self.user_id,
        )
        self.repo.add(shared)
        await self.session.flush()
        return shared

    async def unshare_document(self, matter_id: uuid.UUID, document_id: uuid.UUID) -> None:
        shared = await self.repo.get_shared(self.tenant_id, matter_id, document_id)
        if shared is not None:
            await self.repo.delete(shared)

    async def shared_document_ids(self, matter_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self.repo.shared_documents(self.tenant_id, matter_id)
        return [row.document_id for row in rows]


class ClientPortalService:
    """Client-side access authenticated by token (bypass-RLS session)."""

    def __init__(self, session: AsyncSession, storage: Storage) -> None:
        self.session = session
        self.storage = storage
        self.repo = PortalRepository(session)
        self.matters = MatterRepository(session)
        self.documents = DocumentRepository(session)

    async def resolve(self, token: str) -> PortalAccess:
        access = await self.repo.by_token(token)
        if access is None or not access.is_active:
            raise NotFoundError("This portal link is invalid or has been revoked.")
        return access

    async def view(self, token: str) -> dict:
        access = await self.resolve(token)
        matter = await self.matters.get(access.tenant_id, access.matter_id, detail=True)
        if matter is None:
            raise NotFoundError("Matter not found.")
        updates = await self.repo.updates(access.tenant_id, access.matter_id)
        approvals = await self.repo.approvals(access.tenant_id, access.matter_id)
        shared = await self.repo.shared_documents(access.tenant_id, access.matter_id)
        documents: list[Document] = []
        for link in shared:
            doc = await self.documents.get_document(access.tenant_id, link.document_id)
            if doc is not None:
                documents.append(doc)
        invoices = list((await self.session.execute(select(Invoice).where(
            Invoice.tenant_id == access.tenant_id, Invoice.matter_id == access.matter_id,
            Invoice.deleted_at.is_(None), Invoice.status != InvoiceStatus.CANCELLED,
        ).order_by(Invoice.created_at.desc()))).scalars().all())
        return {
            "access": access,
            "matter": matter,
            "updates": updates,
            "approvals": approvals,
            "documents": documents,
            "invoices": invoices,
        }

    async def respond_approval(
        self, token: str, approval_id: uuid.UUID, *, approve: bool, note: str | None
    ) -> PortalApproval:
        access = await self.resolve(token)
        approval = await self.repo.get_approval(access.tenant_id, access.matter_id, approval_id)
        if approval is None:
            raise NotFoundError("Approval request not found.")
        if approval.status != ApprovalStatus.PENDING:
            raise ConflictError("This request has already been answered.")
        approval.status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
        approval.response_note = note
        approval.responded_at = datetime.now(UTC)
        return approval

    async def download(self, token: str, document_id: uuid.UUID) -> tuple[Document, bytes]:
        access = await self.resolve(token)
        if await self.repo.get_shared(access.tenant_id, access.matter_id, document_id) is None:
            raise NotFoundError("This document is not shared with you.")
        document = await self.documents.get_document(access.tenant_id, document_id)
        if document is None or document.current_version_id is None:
            raise NotFoundError("Document not available.")
        version: DocumentVersion | None = await self.documents.get_version(
            access.tenant_id, document.current_version_id
        )
        if version is None:
            raise NotFoundError("Document version not available.")
        try:
            data = await self.storage.get(version.storage_key)
        except FileNotFoundError as exc:
            raise NotFoundError("The stored file is missing.") from exc
        return document, data
