"""Marketplace domain models (Phase 5) — global cross-tenant board."""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import AuditedBase


class ListingType(StrEnum):
    REFERRAL = "referral"
    LOCAL_COUNSEL = "local_counsel"
    EXPERT = "expert"
    RESEARCHER = "researcher"
    ARBITRATOR = "arbitrator"
    JOB = "job"
    INTERNSHIP = "internship"


class ListingStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class Listing(AuditedBase):
    __tablename__ = "marketplace_listings"

    type: Mapped[ListingType] = mapped_column(
        String(20), default=ListingType.REFERRAL, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    practice_area: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    budget: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[ListingStatus] = mapped_column(
        String(10), default=ListingStatus.OPEN, nullable=False, index=True
    )
    posted_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    poster_name: Mapped[str] = mapped_column(String(200), nullable=False)
    poster_tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    accepted_response_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    response_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    responses: Mapped[list["ListingResponse"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )


class ListingResponse(AuditedBase):
    __tablename__ = "marketplace_responses"

    listing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_listings.id", ondelete="CASCADE"), index=True
    )
    responder_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    responder_name: Mapped[str] = mapped_column(String(200), nullable=False)
    responder_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    listing: Mapped[Listing] = relationship(back_populates="responses")
