"""Data-access layer for the marketplace (global tables)."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_utils import LIKE_ESCAPE, contains
from app.modules.marketplace.models import (
    Listing,
    ListingResponse,
    ListingStatus,
    ListingType,
)


class MarketplaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def get(self, listing_id: uuid.UUID) -> Listing | None:
        res = await self.session.execute(
            select(Listing).where(Listing.id == listing_id, Listing.deleted_at.is_(None))
        )
        return res.scalar_one_or_none()

    async def list(
        self,
        *,
        type_: ListingType | None,
        practice_area: str | None,
        query: str | None,
        status: ListingStatus | None,
        limit: int,
        offset: int,
    ) -> list[Listing]:
        stmt = select(Listing).where(Listing.deleted_at.is_(None))
        if type_ is not None:
            stmt = stmt.where(Listing.type == type_)
        if status is not None:
            stmt = stmt.where(Listing.status == status)
        if practice_area:
            stmt = stmt.where(Listing.practice_area.ilike(contains(practice_area), escape=LIKE_ESCAPE))
        if query:
            like = contains(query)
            stmt = stmt.where(
                or_(Listing.title.ilike(like, escape=LIKE_ESCAPE), Listing.description.ilike(like, escape=LIKE_ESCAPE), Listing.location.ilike(like, escape=LIKE_ESCAPE))
            )
        res = await self.session.execute(
            stmt.order_by(Listing.created_at.desc()).limit(limit).offset(offset)
        )
        return list(res.scalars().all())

    async def by_poster(self, user_id: uuid.UUID) -> list[Listing]:
        res = await self.session.execute(
            select(Listing)
            .where(Listing.posted_by == user_id, Listing.deleted_at.is_(None))
            .order_by(Listing.created_at.desc())
        )
        return list(res.scalars().all())

    async def responses(self, listing_id: uuid.UUID) -> list[ListingResponse]:
        res = await self.session.execute(
            select(ListingResponse)
            .where(ListingResponse.listing_id == listing_id)
            .order_by(ListingResponse.created_at.desc())
        )
        return list(res.scalars().all())

    async def response(self, listing_id: uuid.UUID, response_id: uuid.UUID) -> ListingResponse | None:
        return (await self.session.execute(select(ListingResponse).where(
            ListingResponse.id == response_id, ListingResponse.listing_id == listing_id
        ))).scalar_one_or_none()
