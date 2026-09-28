"""Data-access layer for billing. Filters by ``tenant_id`` alongside RLS."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.billing.models import (
    BillingReceipt,
    Invoice,
    InvoiceDocumentType,
    InvoiceFollowUp,
    InvoiceLineItem,
    InvoiceStatus,
)


class BillingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def delete(self, obj: object) -> None:
        await self.session.delete(obj)

    async def count(self, tenant_id: uuid.UUID) -> int:
        res = await self.session.execute(
            select(func.count()).select_from(Invoice).where(Invoice.tenant_id == tenant_id)
        )
        return int(res.scalar_one())

    async def get(
        self, tenant_id: uuid.UUID, invoice_id: uuid.UUID, *, detail: bool = False
    ) -> Invoice | None:
        stmt = select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == tenant_id,
            Invoice.deleted_at.is_(None),
        )
        if detail:
            stmt = stmt.options(
                selectinload(Invoice.line_items),
                selectinload(Invoice.follow_ups),
                selectinload(Invoice.receipts),
            )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list(
        self,
        tenant_id: uuid.UUID,
        status: InvoiceStatus | None,
        limit: int,
        offset: int,
        *,
        client_id: uuid.UUID | None = None,
        matter_id: uuid.UUID | None = None,
    ) -> list[Invoice]:
        stmt = select(Invoice).where(Invoice.tenant_id == tenant_id, Invoice.deleted_at.is_(None))
        if status is not None:
            stmt = stmt.where(Invoice.status == status)
        if client_id is not None:
            stmt = stmt.where(Invoice.client_id == client_id)
        if matter_id is not None:
            stmt = stmt.where(Invoice.matter_id == matter_id)
        res = await self.session.execute(
            stmt.order_by(Invoice.created_at.desc()).limit(limit).offset(offset)
        )
        return list(res.scalars().all())

    async def count_type(self, tenant_id: uuid.UUID, kind: InvoiceDocumentType) -> int:
        res = await self.session.execute(
            select(func.count())
            .select_from(Invoice)
            .where(Invoice.tenant_id == tenant_id, Invoice.document_type == kind)
        )
        return int(res.scalar_one())

    async def receipt_count(self, tenant_id: uuid.UUID) -> int:
        res = await self.session.execute(
            select(func.count())
            .select_from(BillingReceipt)
            .where(BillingReceipt.tenant_id == tenant_id)
        )
        return int(res.scalar_one())

    async def list_receipts(
        self, tenant_id: uuid.UUID, limit: int, offset: int
    ) -> list[BillingReceipt]:
        res = await self.session.execute(
            select(BillingReceipt)
            .where(BillingReceipt.tenant_id == tenant_id, BillingReceipt.deleted_at.is_(None))
            .order_by(BillingReceipt.received_on.desc(), BillingReceipt.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())

    async def list_follow_ups(
        self, tenant_id: uuid.UUID, limit: int, offset: int
    ) -> list[InvoiceFollowUp]:
        res = await self.session.execute(
            select(InvoiceFollowUp)
            .where(InvoiceFollowUp.tenant_id == tenant_id, InvoiceFollowUp.deleted_at.is_(None))
            .order_by(InvoiceFollowUp.next_follow_up_on.asc(), InvoiceFollowUp.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())

    async def receipt_for_payment(
        self, tenant_id: uuid.UUID, payment_id: uuid.UUID
    ) -> BillingReceipt | None:
        return await self.session.scalar(
            select(BillingReceipt).where(
                BillingReceipt.tenant_id == tenant_id, BillingReceipt.payment_id == payment_id
            )
        )

    async def get_line_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> InvoiceLineItem | None:
        res = await self.session.execute(
            select(InvoiceLineItem).where(
                InvoiceLineItem.id == item_id, InvoiceLineItem.tenant_id == tenant_id
            )
        )
        return res.scalar_one_or_none()
