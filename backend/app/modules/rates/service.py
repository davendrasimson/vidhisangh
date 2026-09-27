"""Counsel rate cards — business rules."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.modules.identity.models import User
from app.modules.rates.models import CounselRate
from app.modules.rates.repository import RateRepository
from app.modules.rates.schemas import RateCardRead, RateCreate, RateRead, RateUpdate


class RateService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.repo = RateRepository(session)

    async def _people(self) -> list[User]:
        res = await self.session.execute(
            select(User)
            .where(User.tenant_id == self.tenant_id, User.deleted_at.is_(None))
            .order_by(User.full_name)
        )
        return list(res.scalars().all())

    @staticmethod
    def _read(rate: CounselRate, name: str | None, today: date) -> RateRead:
        out = RateRead.model_validate(rate)
        out.user_name = name
        out.is_current = rate.effective_from <= today and (rate.effective_to is None or rate.effective_to >= today)
        return out

    async def cards(self) -> list[RateCardRead]:
        """Everyone in the firm with their rate rows (people without rates included)."""
        today = date.today()
        people = await self._people()
        rates = await self.repo.list(self.tenant_id)
        by_user: dict[uuid.UUID, list[CounselRate]] = {}
        for r in rates:
            by_user.setdefault(r.user_id, []).append(r)
        return [
            RateCardRead(
                user_id=p.id, full_name=p.full_name, email=p.email, is_active=p.is_active,
                rates=[self._read(r, p.full_name, today) for r in by_user.get(p.id, [])],
            )
            for p in people
        ]

    async def create(self, data: RateCreate) -> RateRead:
        person = await self.session.get(User, data.user_id)
        if person is None or person.tenant_id != self.tenant_id or person.deleted_at is not None:
            raise NotFoundError("That person is not a member of this organisation.")
        start = data.effective_from or date.today()
        if data.effective_to is not None and data.effective_to < start:
            raise ValidationError("The rate cannot end before it starts.")
        # A new rate for the same basis supersedes the open one from the day before.
        for existing in await self.repo.list(self.tenant_id, data.user_id):
            if existing.basis == data.basis and existing.effective_to is None and existing.effective_from < start:
                existing.effective_to = date.fromordinal(start.toordinal() - 1)
            elif existing.basis == data.basis and existing.effective_to is None and existing.effective_from >= start:
                raise ValidationError(
                    f"An open {data.basis.replace('_', ' ')} rate already starts on "
                    f"{existing.effective_from:%d/%m/%Y}; end or edit that one first."
                )
        rate = CounselRate(
            tenant_id=self.tenant_id, user_id=data.user_id, basis=data.basis, amount=data.amount,
            currency=data.currency.upper(), effective_from=start, effective_to=data.effective_to,
            notes=data.notes, created_by=self.user_id,
        )
        self.repo.add(rate)
        await self.session.flush()
        return self._read(rate, person.full_name, date.today())

    async def update(self, rate_id: uuid.UUID, data: RateUpdate) -> RateRead:
        rate = await self.repo.get(self.tenant_id, rate_id)
        if rate is None:
            raise NotFoundError("Rate not found.")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(rate, field, value)
        if rate.effective_to is not None and rate.effective_to < rate.effective_from:
            raise ValidationError("The rate cannot end before it starts.")
        await self.session.flush()
        person = await self.session.get(User, rate.user_id)
        return self._read(rate, person.full_name if person else None, date.today())

    async def delete(self, rate_id: uuid.UUID) -> None:
        rate = await self.repo.get(self.tenant_id, rate_id)
        if rate is None:
            raise NotFoundError("Rate not found.")
        rate.deleted_at = datetime.now(UTC)
