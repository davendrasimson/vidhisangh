"""Data-access layer for the client portal. Firm queries filter by ``tenant_id``;
the client (token) path resolves the access first, then filters by its
tenant + matter."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.portal.models import (
    PortalAccess,
    PortalApproval,
    PortalDocument,
    PortalUpdate,
)


class PortalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def delete(self, obj: object) -> None:
        await self.session.delete(obj)

    # ── Access ──────────────────────────────────────────────────────
    async def get_access(
        self, tenant_id: uuid.UUID, access_id: uuid.UUID
    ) -> PortalAccess | None:
        res = await self.session.execute(
            select(PortalAccess).where(
                PortalAccess.id == access_id,
                PortalAccess.tenant_id == tenant_id,
                PortalAccess.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def list_access(
        self, tenant_id: uuid.UUID, matter_id: uuid.UUID
    ) -> list[PortalAccess]:
        res = await self.session.execute(
            select(PortalAccess)
            .where(
                PortalAccess.tenant_id == tenant_id,
                PortalAccess.matter_id == matter_id,
                PortalAccess.deleted_at.is_(None),
            )
            .order_by(PortalAccess.created_at.desc())
        )
        return list(res.scalars().all())

    async def by_token_hash(self, token_hash: str) -> PortalAccess | None:
        """Resolve a portal token by its hash (client path — runs on a bypass session)."""
        res = await self.session.execute(
            select(PortalAccess).where(
                PortalAccess.token_hash == token_hash, PortalAccess.deleted_at.is_(None)
            )
        )
        return res.scalar_one_or_none()

    # ── Updates ─────────────────────────────────────────────────────
    async def updates(self, tenant_id: uuid.UUID, matter_id: uuid.UUID) -> list[PortalUpdate]:
        res = await self.session.execute(
            select(PortalUpdate)
            .where(
                PortalUpdate.tenant_id == tenant_id,
                PortalUpdate.matter_id == matter_id,
                PortalUpdate.deleted_at.is_(None),
            )
            .order_by(PortalUpdate.created_at.desc())
        )
        return list(res.scalars().all())

    # ── Approvals ───────────────────────────────────────────────────
    async def approvals(self, tenant_id: uuid.UUID, matter_id: uuid.UUID) -> list[PortalApproval]:
        res = await self.session.execute(
            select(PortalApproval)
            .where(
                PortalApproval.tenant_id == tenant_id,
                PortalApproval.matter_id == matter_id,
                PortalApproval.deleted_at.is_(None),
            )
            .order_by(PortalApproval.created_at.desc())
        )
        return list(res.scalars().all())

    async def get_approval(
        self, tenant_id: uuid.UUID, matter_id: uuid.UUID, approval_id: uuid.UUID
    ) -> PortalApproval | None:
        res = await self.session.execute(
            select(PortalApproval).where(
                PortalApproval.id == approval_id,
                PortalApproval.tenant_id == tenant_id,
                PortalApproval.matter_id == matter_id,
            )
        )
        return res.scalar_one_or_none()

    # ── Shared documents ────────────────────────────────────────────
    async def shared_documents(
        self, tenant_id: uuid.UUID, matter_id: uuid.UUID
    ) -> list[PortalDocument]:
        res = await self.session.execute(
            select(PortalDocument).where(
                PortalDocument.tenant_id == tenant_id,
                PortalDocument.matter_id == matter_id,
            )
        )
        return list(res.scalars().all())

    async def get_shared(
        self, tenant_id: uuid.UUID, matter_id: uuid.UUID, document_id: uuid.UUID
    ) -> PortalDocument | None:
        res = await self.session.execute(
            select(PortalDocument).where(
                PortalDocument.tenant_id == tenant_id,
                PortalDocument.matter_id == matter_id,
                PortalDocument.document_id == document_id,
            )
        )
        return res.scalar_one_or_none()
