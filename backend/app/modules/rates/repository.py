"""Data access for counsel rate cards (explicit tenant filter alongside RLS)."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.matters.models import RateBasis
from app.modules.rates.models import CounselRate


class RateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, obj: CounselRate) -> None:
        self.session.add(obj)

    async def get(self, tenant_id: uuid.UUID, rate_id: uuid.UUID) -> CounselRate | None:
        res = await self.session.execute(
            select(CounselRate).where(
                CounselRate.id == rate_id, CounselRate.tenant_id == tenant_id, CounselRate.deleted_at.is_(None)
            )
        )
        return res.scalar_one_or_none()

    async def list(self, tenant_id: uuid.UUID, user_id: uuid.UUID | None = None) -> list[CounselRate]:
        stmt = select(CounselRate).where(CounselRate.tenant_id == tenant_id, CounselRate.deleted_at.is_(None))
        if user_id is not None:
            stmt = stmt.where(CounselRate.user_id == user_id)
        res = await self.session.execute(
            stmt.order_by(CounselRate.user_id, CounselRate.basis, CounselRate.effective_from.desc())
        )
        return list(res.scalars().all())

    async def current(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, basis: RateBasis | None, on: date
    ) -> CounselRate | None:
        """The rate in force on `on` for this basis (any basis when None, hourly first)."""
        stmt = select(CounselRate).where(
            CounselRate.tenant_id == tenant_id,
            CounselRate.user_id == user_id,
            CounselRate.deleted_at.is_(None),
            CounselRate.effective_from <= on,
            or_(CounselRate.effective_to.is_(None), CounselRate.effective_to >= on),
        )
        if basis is not None:
            stmt = stmt.where(CounselRate.basis == basis)
        res = await self.session.execute(stmt.order_by(CounselRate.effective_from.desc()))
        rows = list(res.scalars().all())
        if not rows:
            return None
        if basis is None:
            hourly = [r for r in rows if r.basis == RateBasis.HOURLY]
            return hourly[0] if hourly else rows[0]
        return rows[0]

    async def current_for_users(
        self, tenant_id: uuid.UUID, user_ids: set[uuid.UUID], on: date
    ) -> dict[tuple[uuid.UUID, str], CounselRate]:
        """{(user_id, basis): rate in force} for a set of people, one query."""
        if not user_ids:
            return {}
        res = await self.session.execute(
            select(CounselRate)
            .where(
                CounselRate.tenant_id == tenant_id,
                CounselRate.user_id.in_(user_ids),
                CounselRate.deleted_at.is_(None),
                CounselRate.effective_from <= on,
                or_(CounselRate.effective_to.is_(None), CounselRate.effective_to >= on),
            )
            .order_by(CounselRate.effective_from.desc())
        )
        out: dict[tuple[uuid.UUID, str], CounselRate] = {}
        for r in res.scalars().all():
            out.setdefault((r.user_id, str(r.basis)), r)
        return out
