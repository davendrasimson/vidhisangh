from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.referrals.models import Referral, ReferralCode


class ReferralRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def code_for(self, user_id: uuid.UUID) -> ReferralCode | None:
        stmt = select(ReferralCode).where(ReferralCode.user_id == user_id, ReferralCode.deleted_at.is_(None))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def by_code(self, code: str) -> ReferralCode | None:
        stmt = select(ReferralCode).where(ReferralCode.code == code, ReferralCode.deleted_at.is_(None))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def code_exists(self, code: str) -> bool:
        stmt = select(func.count()).where(ReferralCode.code == code)
        return (await self.session.execute(stmt)).scalar_one() > 0

    async def joined_count(self, user_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(Referral.referrer_user_id == user_id, Referral.deleted_at.is_(None))
        return (await self.session.execute(stmt)).scalar_one()

    def add(self, obj: ReferralCode | Referral) -> None:
        self.session.add(obj)
