"""Pydantic schemas for the professional profile module."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.profile.models import ProfileVisibility, VerificationStatus


class EducationItem(BaseModel):
    institution: str = Field(max_length=200)
    degree: str | None = Field(default=None, max_length=150)
    year: int | None = Field(default=None, ge=1900, le=2100)


class PublicationItem(BaseModel):
    title: str = Field(max_length=300)
    publisher: str | None = Field(default=None, max_length=200)
    year: int | None = Field(default=None, ge=1900, le=2100)
    url: str | None = Field(default=None, max_length=500)


class ProfileUpdate(BaseModel):
    """Fields the profile owner may edit (all optional / partial update)."""

    headline: str | None = Field(default=None, max_length=200)
    bio: str | None = Field(default=None, max_length=5000)
    enrollment_number: str | None = Field(default=None, max_length=80)
    bar_council: str | None = Field(default=None, max_length=150)
    year_of_enrollment: int | None = Field(default=None, ge=1900, le=2100)
    years_of_experience: int | None = Field(default=None, ge=0, le=80)
    practice_areas: list[str] | None = Field(default=None, max_length=30)
    courts: list[str] | None = Field(default=None, max_length=50)
    languages: list[str] | None = Field(default=None, max_length=30)
    education: list[EducationItem] | None = None
    achievements: list[str] | None = Field(default=None, max_length=50)
    publications: list[PublicationItem] | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    office_address: str | None = Field(default=None, max_length=400)
    website: str | None = Field(default=None, max_length=300)
    linkedin_url: str | None = Field(default=None, max_length=300)
    consultation_enabled: bool | None = None
    consultation_fee: Decimal | None = Field(default=None, ge=0)
    availability: dict | None = None
    visibility: ProfileVisibility | None = None


class EndorsementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    skill: str
    endorser_user_id: uuid.UUID


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    author_user_id: uuid.UUID
    relationship_context: str | None
    body: str
    created_at: datetime


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    headline: str | None
    bio: str | None
    enrollment_number: str | None
    bar_council: str | None
    year_of_enrollment: int | None
    years_of_experience: int | None
    practice_areas: list[str]
    courts: list[str]
    languages: list[str]
    education: list
    achievements: list[str]
    publications: list
    city: str | None
    state: str | None
    office_address: str | None
    website: str | None
    linkedin_url: str | None
    consultation_enabled: bool
    consultation_fee: Decimal | None
    availability: dict
    verification_status: VerificationStatus
    visibility: ProfileVisibility
    avg_rating: Decimal | None
    rating_count: int


class ProfileDetail(ProfileRead):
    """Full profile view including social proof."""

    endorsement_summary: dict[str, int] = Field(
        default_factory=dict, description="skill → number of endorsements"
    )
    recommendations: list[RecommendationRead] = []


# ─── Write payloads ─────────────────────────────────────────────────
class EndorsementCreate(BaseModel):
    skill: str = Field(min_length=1, max_length=120)


class RecommendationCreate(BaseModel):
    relationship_context: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=10, max_length=3000)


class BarVerificationCreate(BaseModel):
    enrollment_number: str = Field(min_length=1, max_length=80)
    bar_council: str = Field(min_length=1, max_length=150)
    document_url: str | None = Field(default=None, max_length=500)


class BarVerificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    enrollment_number: str
    bar_council: str
    status: VerificationStatus
    reviewer_notes: str | None
    reviewed_at: datetime | None
    created_at: datetime
