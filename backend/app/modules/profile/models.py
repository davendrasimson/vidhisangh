"""Professional profile domain models (Phase 2).

The public, professional identity of a legal practitioner — the backbone the
social network, marketplace, verification badges and consultation booking build
on. One ``ProfessionalProfile`` per user (1:1), plus peer **endorsements**,
**recommendations**, and **bar-council verification** requests.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import TenantScopedBase


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ProfileVisibility(StrEnum):
    PUBLIC = "public"
    CONNECTIONS = "connections"
    PRIVATE = "private"


DEFAULT_PROFILE_GROUP_VISIBILITY = {
    "about": "everyone",
    "professional": "everyone",
    "education": "connections",
    "location": "connections",
    "contact": "none",
    "judicial": "connections",
}


class ProfessionalProfile(TenantScopedBase):
    __tablename__ = "professional_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="professional_profiles_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # ── Headline / narrative ────────────────────────────────────────
    headline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    professional_role: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    designation: Mapped[str | None] = mapped_column(String(160), nullable=True)

    # ── Bar enrolment ───────────────────────────────────────────────
    enrollment_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    bar_council: Mapped[str | None] = mapped_column(String(150), nullable=True)
    year_of_enrollment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    years_of_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Expertise (arrays kept as JSON for portability) ─────────────
    practice_areas: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    courts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    languages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    education: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    achievements: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    publications: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    employment_history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    memberships: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # ── Location & contact ──────────────────────────────────────────
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    office_address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    professional_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    professional_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(12), nullable=True)

    # ── Judicial office / order drafting ───────────────────────────
    judicial_court_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    judicial_court_address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    judicial_district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    judicial_state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # e-Courts officer identifier written on every order (JO code / UID No.).
    judicial_officer_code: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # ── Consultation & availability ─────────────────────────────────
    consultation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consultation_fee: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    availability: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # ── Trust signals ───────────────────────────────────────────────
    verification_status: Mapped[VerificationStatus] = mapped_column(
        String(20), default=VerificationStatus.UNVERIFIED, nullable=False
    )
    visibility: Mapped[ProfileVisibility] = mapped_column(
        String(20), default=ProfileVisibility.PUBLIC, nullable=False
    )
    visibility_settings: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=lambda: dict(DEFAULT_PROFILE_GROUP_VISIBILITY)
    )
    avg_rating: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    endorsements: Mapped[list["Endorsement"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )

    @property
    def is_verified(self) -> bool:
        return self.verification_status == VerificationStatus.VERIFIED


class Endorsement(TenantScopedBase):
    """A peer endorsing a practitioner for a specific skill / practice area."""

    __tablename__ = "profile_endorsements"
    __table_args__ = (
        UniqueConstraint("profile_id", "endorser_user_id", "skill", name="endorsement_unique"),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("professional_profiles.id", ondelete="CASCADE"), index=True
    )
    endorser_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    skill: Mapped[str] = mapped_column(String(120), nullable=False)

    profile: Mapped[ProfessionalProfile] = relationship(back_populates="endorsements")


class Recommendation(TenantScopedBase):
    """A written recommendation from a peer or client."""

    __tablename__ = "profile_recommendations"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("professional_profiles.id", ondelete="CASCADE"), index=True
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    relationship_context: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    profile: Mapped[ProfessionalProfile] = relationship(back_populates="recommendations")


class BarVerificationRequest(TenantScopedBase):
    """A request to verify bar-council enrolment (reviewed by an admin)."""

    __tablename__ = "bar_verification_requests"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    enrollment_number: Mapped[str] = mapped_column(String(80), nullable=False)
    bar_council: Mapped[str] = mapped_column(String(150), nullable=False)
    document_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[VerificationStatus] = mapped_column(
        String(20), default=VerificationStatus.PENDING, nullable=False
    )
    reviewer_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
