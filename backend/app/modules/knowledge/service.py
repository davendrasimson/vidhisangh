"""Knowledge base service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.modules.documents.repository import DocumentRepository
from app.modules.knowledge.models import KnowledgeCategory, KnowledgeItem
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.schemas import KnowledgeCreate, KnowledgeUpdate


class KnowledgeService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.repo = KnowledgeRepository(session)

    async def create(self, data: KnowledgeCreate) -> KnowledgeItem:
        await self._validate_attachments(data.attachments)
        item = KnowledgeItem(
            tenant_id=self.tenant_id,
            title=data.title,
            category=data.category,
            body=data.body,
            practice_area=data.practice_area,
            tags=data.tags,
            created_by=self.user_id,
            source_url=str(data.source_url) if data.source_url else None,
            reviewed_on=data.reviewed_on,
            attachments=[str(i) for i in data.attachments],
        )
        self.repo.add(item)
        await self.session.flush()
        return item

    async def get(self, item_id: uuid.UUID) -> KnowledgeItem:
        item = await self.repo.get(self.tenant_id, item_id)
        if item is None:
            raise NotFoundError("Knowledge item not found.")
        return item

    async def list(
        self,
        *,
        category: KnowledgeCategory | None,
        practice_area: str | None,
        query: str | None,
        limit: int,
        offset: int,
    ) -> list[KnowledgeItem]:
        return await self.repo.list(
            self.tenant_id,
            category=category,
            practice_area=practice_area,
            query=query,
            limit=limit,
            offset=offset,
        )

    async def update(self, item_id: uuid.UUID, data: KnowledgeUpdate) -> KnowledgeItem:
        item = await self.get(item_id)
        if "attachments" in data.model_fields_set:
            await self._validate_attachments(data.attachments)
        for field, value in data.model_dump(mode="json", exclude_unset=True).items():
            if field in {"title", "category", "body", "tags"} and value is None:
                raise ValidationError(f"{field} cannot be null.")
            if field == "reviewed_on":
                value = data.reviewed_on
            setattr(item, field, value)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def delete(self, item_id: uuid.UUID) -> None:
        item = await self.get(item_id)
        item.deleted_at = datetime.now(UTC)

    async def _validate_attachments(self, ids: list[uuid.UUID]) -> None:
        documents = DocumentRepository(self.session)
        for document_id in ids:
            if await documents.get_document(self.tenant_id, document_id) is None:
                raise NotFoundError("Attachment not found in this firm.")
