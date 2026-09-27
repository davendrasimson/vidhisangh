"""Documents service — folders, versioned uploads, check-in/out, download."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.storage import Storage
from app.modules.clients.lookup import client_names, require_client
from app.modules.documents.models import Document, DocumentFolder, DocumentVersion
from app.modules.documents.repository import DocumentRepository
from app.modules.matters.repository import MatterRepository
from app.modules.documents.schemas import DocumentRead, FolderCreate


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        storage: Storage,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.storage = storage
        self.repo = DocumentRepository(session)

    async def _require_document(self, document_id: uuid.UUID) -> Document:
        document = await self.repo.get_document(self.tenant_id, document_id)
        if document is None:
            raise NotFoundError("Document not found.")
        return document

    async def _validate_placement(
        self, folder_id: uuid.UUID | None, matter_id: uuid.UUID | None = None
    ) -> None:
        if folder_id is not None and await self.repo.get_folder(self.tenant_id, folder_id) is None:
            raise NotFoundError("Folder not found.")
        if (
            matter_id is not None
            and await MatterRepository(self.session).get(self.tenant_id, matter_id) is None
        ):
            raise NotFoundError("Matter not found.")

    # ── Folders ─────────────────────────────────────────────────────
    async def create_folder(self, data: FolderCreate) -> DocumentFolder:
        await self._validate_placement(data.parent_id, data.matter_id)
        folder = DocumentFolder(
            tenant_id=self.tenant_id,
            name=data.name,
            parent_id=data.parent_id,
            matter_id=data.matter_id,
            created_by=self.user_id,
        )
        self.repo.add(folder)
        await self.session.flush()
        return folder

    async def list_folders(
        self, parent_id: uuid.UUID | None, matter_id: uuid.UUID | None
    ) -> list[DocumentFolder]:
        return await self.repo.list_folders(self.tenant_id, parent_id, matter_id)

    # ── Upload / versioning ─────────────────────────────────────────
    async def upload(
        self,
        *,
        name: str,
        content_type: str,
        data: bytes,
        folder_id: uuid.UUID | None,
        matter_id: uuid.UUID | None,
        tags: list[str],
        client_id: uuid.UUID | None = None,
    ) -> Document:
        await self._validate_placement(folder_id, matter_id)
        if client_id is not None:
            await require_client(self.session, self.tenant_id, client_id)
        document = Document(
            tenant_id=self.tenant_id,
            name=name,
            folder_id=folder_id,
            matter_id=matter_id,
            client_id=client_id,
            content_type=content_type,
            size=len(data),
            tags=tags,
            uploaded_by=self.user_id,
        )
        self.repo.add(document)
        await self.session.flush()
        version = await self._store_version(document, data, content_type, comment=None)
        document.current_version_id = version.id
        document.version_count = 1
        await self.session.flush()
        # The UPDATE expires server-generated columns (updated_at); reload them so
        # serialization doesn't trigger a sync lazy-load in async context.
        await self.session.refresh(document)
        return document

    async def add_version(
        self, document_id: uuid.UUID, *, content_type: str, data: bytes, comment: str | None
    ) -> Document:
        document = await self._require_document(document_id)
        if document.locked_by is not None and document.locked_by != self.user_id:
            raise PermissionDeniedError("Document is checked out by someone else.")
        version = await self._store_version(document, data, content_type, comment=comment)
        document.current_version_id = version.id
        document.version_count += 1
        document.size = len(data)
        document.content_type = content_type
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def _store_version(
        self, document: Document, data: bytes, content_type: str, *, comment: str | None
    ) -> DocumentVersion:
        key = f"{self.tenant_id}/{document.id}/{uuid.uuid4().hex}"
        await self.storage.put(key, data, content_type)
        version = DocumentVersion(
            tenant_id=self.tenant_id,
            document_id=document.id,
            version_no=document.version_count + 1,
            storage_key=key,
            size=len(data),
            content_type=content_type,
            checksum=hashlib.sha256(data).hexdigest(),
            comment=comment,
            uploaded_by=self.user_id,
        )
        self.repo.add(version)
        await self.session.flush()
        return version

    # ── Read / download ─────────────────────────────────────────────
    async def list_documents(
        self,
        *,
        folder_id: uuid.UUID | None,
        matter_id: uuid.UUID | None,
        query: str | None,
        limit: int,
        offset: int,
        client_id: uuid.UUID | None = None,
    ) -> list[Document]:
        return await self.repo.list_documents(
            self.tenant_id,
            folder_id=folder_id,
            matter_id=matter_id,
            query=query,
            limit=limit,
            offset=offset,
            client_id=client_id,
        )

    async def to_read(self, documents: list[Document]) -> list[DocumentRead]:
        """Read models with the client's display name filled in."""
        names = await client_names(self.session, self.tenant_id, (d.client_id for d in documents))
        out = []
        for d in documents:
            r = DocumentRead.model_validate(d)
            r.client_name = names.get(d.client_id) if d.client_id else None
            out.append(r)
        return out

    async def get_document(self, document_id: uuid.UUID) -> Document:
        return await self._require_document(document_id)

    async def list_versions(self, document_id: uuid.UUID) -> list[DocumentVersion]:
        await self._require_document(document_id)
        return await self.repo.list_versions(self.tenant_id, document_id)

    async def download_current(self, document_id: uuid.UUID) -> tuple[Document, bytes]:
        document = await self._require_document(document_id)
        if document.current_version_id is None:
            raise NotFoundError("Document has no content.")
        version = await self.repo.get_version(self.tenant_id, document.current_version_id)
        if version is None:
            raise NotFoundError("Document version not found.")
        return document, await self._read(version)

    async def download_version(
        self, version_id: uuid.UUID
    ) -> tuple[DocumentVersion, bytes]:
        version = await self.repo.get_version(self.tenant_id, version_id)
        if version is None:
            raise NotFoundError("Version not found.")
        return version, await self._read(version)

    async def _read(self, version: DocumentVersion) -> bytes:
        try:
            return await self.storage.get(version.storage_key)
        except FileNotFoundError as exc:
            raise NotFoundError("The stored file is missing.") from exc

    # ── Check-in / check-out ────────────────────────────────────────
    async def checkout(self, document_id: uuid.UUID) -> Document:
        document = await self._require_document(document_id)
        if document.locked_by is not None and document.locked_by != self.user_id:
            raise ConflictError("Document is already checked out.")
        document.locked_by = self.user_id
        document.locked_at = datetime.now(UTC)
        return document

    async def checkin(self, document_id: uuid.UUID) -> Document:
        document = await self._require_document(document_id)
        if document.locked_by is not None and document.locked_by != self.user_id:
            raise PermissionDeniedError("Only the person who checked it out can check it in.")
        document.locked_by = None
        document.locked_at = None
        return document

    # ── Update / delete ─────────────────────────────────────────────
    async def rename(
        self, document_id: uuid.UUID, *, name: str | None, folder_id: uuid.UUID | None, tags: list[str] | None,
        client_id: uuid.UUID | None = None, set_client: bool = False,
    ) -> Document:
        document = await self._require_document(document_id)
        if folder_id is not None:
            await self._validate_placement(folder_id)
            document.folder_id = folder_id
        if set_client:
            if client_id is not None:
                await require_client(self.session, self.tenant_id, client_id)
            document.client_id = client_id
        if name is not None:
            document.name = name
        if tags is not None:
            document.tags = tags
        return document

    async def delete_document(self, document_id: uuid.UUID) -> None:
        document = await self._require_document(document_id)
        document.deleted_at = datetime.now(UTC)  # bytes are GC'd by a storage sweep (follow-up)
