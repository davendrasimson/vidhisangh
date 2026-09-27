"""Marketplace service — listings & responses (global, snapshot-backed)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.modules.identity.repository import UserRepository
from app.modules.marketplace.models import (
    Listing,
    ListingResponse,
    ListingStatus,
    ListingType,
)
from app.modules.marketplace.repository import MarketplaceRepository
from app.modules.marketplace.schemas import ListingCreate, ResponseCreate
from app.modules.network.repository import IdentityRepository
from app.modules.matters.models import AdvocateRole, Matter, MatterAdvocate, PartySide


class MarketplaceService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.repo = MarketplaceRepository(session)

    async def _my_name(self) -> str:
        identity = await IdentityRepository(self.session).get(self.user_id)
        if identity is not None:
            return identity.display_name
        user = await UserRepository(self.session).get_by_id(self.user_id)
        return (user.display_name or user.full_name) if user is not None else "A professional"

    async def _get(self, listing_id: uuid.UUID) -> Listing:
        listing = await self.repo.get(listing_id)
        if listing is None:
            raise NotFoundError("Listing not found.")
        return listing

    async def create_listing(self, data: ListingCreate) -> Listing:
        listing = Listing(
            type=data.type,
            title=data.title,
            description=data.description,
            practice_area=data.practice_area,
            location=data.location,
            budget=data.budget,
            posted_by=self.user_id,
            poster_name=await self._my_name(),
            poster_tenant_id=self.tenant_id,
            matter_id=data.matter_id,
        )
        self.repo.add(listing)
        await self.session.flush()
        return listing

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
        return await self.repo.list(
            type_=type_,
            practice_area=practice_area,
            query=query,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def get(self, listing_id: uuid.UUID) -> Listing:
        return await self._get(listing_id)

    async def my_listings(self) -> list[Listing]:
        return await self.repo.by_poster(self.user_id)

    async def close(self, listing_id: uuid.UUID) -> Listing:
        listing = await self._get(listing_id)
        if listing.posted_by != self.user_id:
            raise PermissionDeniedError("Only the poster can close a listing.")
        listing.status = ListingStatus.CLOSED
        return listing

    async def respond(self, listing_id: uuid.UUID, data: ResponseCreate) -> ListingResponse:
        listing = await self._get(listing_id)
        if listing.posted_by == self.user_id:
            raise ValidationError("You cannot respond to your own listing.")
        if listing.status == ListingStatus.CLOSED:
            raise ConflictError("This listing is closed.")
        user = await UserRepository(self.session).get_by_id(self.user_id)
        response = ListingResponse(
            listing_id=listing_id,
            responder_id=self.user_id,
            responder_name=await self._my_name(),
            responder_email=user.email if user is not None else None,
            message=data.message,
        )
        self.repo.add(response)
        listing.response_count += 1
        await self.session.flush()
        return response

    async def list_responses(self, listing_id: uuid.UUID) -> list[ListingResponse]:
        listing = await self._get(listing_id)
        if listing.posted_by != self.user_id:
            raise PermissionDeniedError("Only the poster can see responses.")
        return await self.repo.responses(listing_id)

    async def accept_response(self, listing_id: uuid.UUID, response_id: uuid.UUID) -> Listing:
        listing = await self._get(listing_id)
        if listing.posted_by != self.user_id or listing.poster_tenant_id != self.tenant_id:
            raise PermissionDeniedError("Only the posting firm can engage a responder.")
        if listing.matter_id is None:
            raise ValidationError("This listing is not linked to a matter.")
        response = await self.repo.response(listing_id, response_id)
        if response is None:
            raise NotFoundError("Response not found.")
        matter = (await self.session.execute(select(Matter).where(
            Matter.id == listing.matter_id, Matter.tenant_id == self.tenant_id, Matter.deleted_at.is_(None)
        ))).scalar_one_or_none()
        if matter is None:
            raise NotFoundError("Linked matter not found.")
        self.repo.add(MatterAdvocate(
            tenant_id=self.tenant_id, matter_id=matter.id, name=response.responder_name,
            email=response.responder_email, user_id=response.responder_id, side=PartySide.OURS,
            role=AdvocateRole.ARGUING_COUNSEL, firm="VidhiSangh marketplace",
            notes=f"Engaged from listing: {listing.title}",
        ))
        listing.accepted_response_id = response.id
        listing.status = ListingStatus.CLOSED
        await self.session.flush()
        return listing
