"""Drafting service — autosaving drafts, named versions, DOCX export, filing."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.malware import scan_upload
from app.core.storage import Storage
from app.modules.clients.lookup import client_names, require_client
from app.modules.documents.models import Document
from app.modules.documents.service import DocumentService
from app.modules.drafting.docx_export import export_docx, word_count
from app.modules.drafting.docx_import import fill_template, import_docx_template, template_fields
from app.modules.drafting.models import Draft, DraftTemplate, DraftVersion
from app.modules.drafting.repository import DraftRepository
from app.modules.drafting.schemas import (
    DraftCreate,
    DraftFromTemplate,
    DraftSummary,
    DraftTemplateUpdate,
    DraftToTemplate,
    DraftUpdate,
    FileToLibrary,
    PageSettings,
)

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _filename(title: str) -> str:
    clean = re.sub(r'[\\/:*?"<>|]+', "-", title).strip() or "Document"
    return f"{clean[:120]}.docx"


class DraftingService:
    def __init__(
        self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID, storage: Storage
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.storage = storage
        self.repo = DraftRepository(session)

    async def _require(self, draft_id: uuid.UUID) -> Draft:
        draft = await self.repo.get(self.tenant_id, draft_id)
        if draft is None:
            raise NotFoundError("Draft not found.")
        return draft

    async def _require_template(self, template_id: uuid.UUID) -> DraftTemplate:
        template = await self.repo.get_template(self.tenant_id, template_id)
        if template is None:
            raise NotFoundError("Word template not found.")
        return template

    # ── Firm Word templates ──────────────────────────────────────
    async def create_template(
        self,
        *,
        data: bytes,
        source_filename: str,
        name: str,
        description: str,
        category: str,
        language: str,
    ) -> DraftTemplate:
        await scan_upload(data)
        content_json, fields, page = import_docx_template(data)
        template_id = uuid.uuid4()
        storage_key = f"{self.tenant_id}/draft-templates/{template_id}/source.docx"
        await self.storage.put(storage_key, data, _DOCX)
        template = DraftTemplate(
            id=template_id,
            tenant_id=self.tenant_id,
            name=name,
            description=description,
            category=category,
            language=language,
            source_filename=source_filename,
            source_storage_key=storage_key,
            source_size=len(data),
            fields=fields,
            content_json=content_json,
            page=page,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        self.repo.add(template)
        try:
            await self.session.flush()
        except Exception:
            await self.storage.delete(storage_key)
            raise
        await self.session.refresh(template)
        return template

    async def templates(self) -> list[DraftTemplate]:
        return await self.repo.list_templates(self.tenant_id)

    async def get_template(self, template_id: uuid.UUID) -> DraftTemplate:
        return await self._require_template(template_id)

    async def update_template(
        self, template_id: uuid.UUID, data: DraftTemplateUpdate
    ) -> DraftTemplate:
        template = await self._require_template(template_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(template, field, value)
        template.updated_by = self.user_id
        await self.session.flush()
        await self.session.refresh(template)
        return template

    async def delete_template(self, template_id: uuid.UUID) -> None:
        template = await self._require_template(template_id)
        template.deleted_at = datetime.now(UTC)
        await self.session.flush()
        await self.storage.delete(template.source_storage_key)

    async def template_source(self, template_id: uuid.UUID) -> tuple[str, bytes]:
        template = await self._require_template(template_id)
        try:
            return template.source_filename, await self.storage.get(template.source_storage_key)
        except FileNotFoundError as exc:
            raise NotFoundError("The original Word template file is unavailable.") from exc

    async def create_from_template(self, template_id: uuid.UUID, data: DraftFromTemplate) -> Draft:
        template = await self._require_template(template_id)
        missing = [
            str(field.get("label") or field.get("key"))
            for field in template.fields
            if field.get("required") and not data.values.get(str(field.get("key")), "").strip()
        ]
        if missing:
            raise ValidationError(f"Complete the required template fields: {', '.join(missing)}.")
        content = fill_template(template.content_json, template.fields, data.values)
        return await self.create(
            DraftCreate(
                title=data.title or template.name,
                language=template.language,
                template_id=str(template.id),
                matter_id=data.matter_id,
                client_id=data.client_id,
                content_json=content,
                page=PageSettings.model_validate(template.page),
            )
        )

    async def save_draft_as_template(
        self, draft_id: uuid.UUID, data: DraftToTemplate
    ) -> DraftTemplate:
        draft = await self._require(draft_id)
        blob = export_docx(draft.content_json, draft.page, title=draft.title)
        name = data.name or draft.title
        await scan_upload(blob)
        template_id = uuid.uuid4()
        storage_key = f"{self.tenant_id}/draft-templates/{template_id}/source.docx"
        await self.storage.put(storage_key, blob, _DOCX)
        template = DraftTemplate(
            id=template_id,
            tenant_id=self.tenant_id,
            name=name,
            description=data.description,
            category=data.category,
            language=draft.language,
            source_filename=_filename(name),
            source_storage_key=storage_key,
            source_size=len(blob),
            fields=template_fields(draft.content_json),
            content_json=draft.content_json,
            page=draft.page,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        self.repo.add(template)
        try:
            await self.session.flush()
        except Exception:
            await self.storage.delete(storage_key)
            raise
        await self.session.refresh(template)
        return template

    # ── Drafts ────────────────────────────────────────────────────
    async def create(self, data: DraftCreate) -> Draft:
        if data.client_id is not None:
            await require_client(self.session, self.tenant_id, data.client_id)
        draft = Draft(
            tenant_id=self.tenant_id,
            title=data.title,
            language=data.language,
            template_id=data.template_id,
            matter_id=data.matter_id,
            client_id=data.client_id,
            content_json=data.content_json,
            content_html=data.content_html,
            page=data.page.model_dump(),
            word_count=word_count(data.content_json),
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        self.repo.add(draft)
        await self.session.flush()
        await self.session.refresh(draft)
        return draft

    async def get(self, draft_id: uuid.UUID) -> Draft:
        return await self._require(draft_id)

    async def list(
        self, *, matter_id: uuid.UUID | None, q: str | None, client_id: uuid.UUID | None = None
    ) -> list[Draft]:
        return await self.repo.list(self.tenant_id, matter_id=matter_id, q=q, client_id=client_id)

    async def to_summary(self, drafts: list[Draft]) -> list[DraftSummary]:
        names = await client_names(self.session, self.tenant_id, (d.client_id for d in drafts))
        out = []
        for d in drafts:
            r = DraftSummary.model_validate(d)
            r.client_name = names.get(d.client_id) if d.client_id else None
            out.append(r)
        return out

    async def update(self, draft_id: uuid.UUID, data: DraftUpdate) -> Draft:
        draft = await self._require(draft_id)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("client_id") is not None:
            await require_client(self.session, self.tenant_id, changes["client_id"])
        if "page" in changes and changes["page"] is not None:
            changes["page"] = data.page.model_dump()  # type: ignore[union-attr]
        for field, value in changes.items():
            setattr(draft, field, value)
        if "content_json" in changes:
            draft.word_count = word_count(draft.content_json)
        draft.updated_by = self.user_id
        await self.session.flush()
        await self.session.refresh(draft)
        return draft

    async def delete(self, draft_id: uuid.UUID) -> None:
        draft = await self._require(draft_id)
        draft.deleted_at = datetime.now(UTC)  # soft delete, like every other record
        await self.session.flush()

    # ── Versions ──────────────────────────────────────────────────
    async def versions(self, draft_id: uuid.UUID) -> list[DraftVersion]:
        await self._require(draft_id)
        return await self.repo.versions(self.tenant_id, draft_id)

    async def snapshot(self, draft_id: uuid.UUID, note: str | None) -> DraftVersion:
        draft = await self._require(draft_id)
        version = DraftVersion(
            tenant_id=self.tenant_id,
            draft_id=draft.id,
            version_no=await self.repo.next_version_no(draft.id),
            note=note,
            content_json=draft.content_json,
            content_html=draft.content_html,
            word_count=draft.word_count,
            created_by=self.user_id,
        )
        self.repo.add(version)
        draft.version_count += 1
        await self.session.flush()
        await self.session.refresh(version)
        return version

    async def get_version(self, draft_id: uuid.UUID, version_id: uuid.UUID) -> DraftVersion:
        await self._require(draft_id)
        version = await self.repo.get_version(self.tenant_id, draft_id, version_id)
        if version is None:
            raise NotFoundError("Version not found.")
        return version

    async def restore(self, draft_id: uuid.UUID, version_id: uuid.UUID) -> Draft:
        """Bring a version back. The current text is snapshotted first, so
        restoring is never destructive."""
        draft = await self._require(draft_id)
        version = await self.get_version(draft_id, version_id)
        await self.snapshot(draft_id, note=f"Before restoring v{version.version_no}")
        draft.content_json = version.content_json
        draft.content_html = version.content_html
        draft.word_count = version.word_count
        draft.updated_by = self.user_id
        await self.session.flush()
        await self.session.refresh(draft)
        return draft

    # ── Export / filing ───────────────────────────────────────────
    async def docx(self, draft_id: uuid.UUID) -> tuple[str, bytes]:
        draft = await self._require(draft_id)
        return _filename(draft.title), export_docx(
            draft.content_json, draft.page, title=draft.title
        )

    async def file_to_library(self, draft_id: uuid.UUID, data: FileToLibrary) -> Document:
        """Put the DOCX into the document library — a new Document the first
        time, a new version of the same Document after that."""
        draft = await self._require(draft_id)
        filename, blob = (
            _filename(draft.title),
            export_docx(draft.content_json, draft.page, title=draft.title),
        )
        docs = DocumentService(self.session, self.user_id, self.tenant_id, self.storage)
        if draft.library_document_id is not None:
            try:
                document = await docs.add_version(
                    draft.library_document_id, content_type=_DOCX, data=blob, comment=data.comment
                )
                if document.name != filename:
                    document.name = filename
                    await self.session.flush()
                    await self.session.refresh(document)
                return document
            except NotFoundError:
                pass  # the library copy was deleted; file a fresh one
        document = await docs.upload(
            name=filename,
            content_type=_DOCX,
            data=blob,
            folder_id=data.folder_id,
            matter_id=draft.matter_id,
            tags=["draft"],
            client_id=draft.client_id,
        )
        draft.library_document_id = document.id
        await self.session.flush()
        return document
