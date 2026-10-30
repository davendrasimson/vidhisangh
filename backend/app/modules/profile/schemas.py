"""Pydantic schemas for the professional profile module."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.profile.models import ProfileVisibility, VerificationStatus


class EducationItem(BaseModel):
    institution: str = Field(max_length=200)
    degree: str | None = Field(default=None, max_length=150)
    level: str | None = Field(default=None, max_length=40)
    field_of_study: str | None = Field(default=None, max_length=150)
    start_year: int | None = Field(default=None, ge=1900, le=2100)
    year: int | None = Field(default=None, ge=1900, le=2100)


class EmploymentItem(BaseModel):
    organisation: str = Field(min_length=1, max_length=200)
    designation: str | None = Field(default=None, max_length=160)
    from_year: int | None = Field(default=None, ge=1900, le=2100)
    to_year: int | None = Field(default=None, ge=1900, le=2100)
    current: bool = False


class MembershipItem(BaseModel):
    organisation: str = Field(min_length=1, max_length=200)
    membership_number: str | None = Field(default=None, max_length=100)
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
    professional_role: str | None = Field(default=None, max_length=80)
    designation: str | None = Field(default=None, max_length=160)
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
    employment_history: list[EmploymentItem] | None = Field(default=None, max_length=50)
    memberships: list[MembershipItem] | None = Field(default=None, max_length=50)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    office_address: str | None = Field(default=None, max_length=400)
    website: str | None = Field(default=None, max_length=300)
    linkedin_url: str | None = Field(default=None, max_length=300)
    professional_email: EmailStr | None = None
    professional_phone: str | None = Field(default=None, max_length=30)
    postal_code: str | None = Field(default=None, max_length=12)
    judicial_court_name: str | None = Field(default=None, max_length=250)
    judicial_court_address: str | None = Field(default=None, max_length=400)
    judicial_district: str | None = Field(default=None, max_length=120)
    judicial_state: str | None = Field(default=None, max_length=120)
    judicial_officer_code: str | None = Field(default=None, max_length=40)
    consultation_enabled: bool | None = None
    consultation_fee: Decimal | None = Field(default=None, ge=0)
    availability: dict | None = None
    visibility: ProfileVisibility | None = None
    visibility_settings: dict[str, str] | None = None

    @field_validator("visibility_settings")
    @classmethod
    def validate_visibility_settings(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return value
        groups = {"about", "professional", "education", "location", "contact", "judicial"}
        levels = {"everyone", "connections", "followers", "none"}
        if set(value) - groups or any(level not in levels for level in value.values()):
            raise ValueError("Invalid profile visibility setting.")
        return value


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
    professional_role: str | None
    designation: str | None
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
    employment_history: list
    memberships: list
    city: str | None
    state: str | None
    office_address: str | None
    website: str | None
    linkedin_url: str | None
    professional_email: EmailStr | None
    professional_phone: str | None
    postal_code: str | None
    judicial_court_name: str | None
    judicial_court_address: str | None
    judicial_district: str | None
    judicial_state: str | None
    judicial_officer_code: str | None
    consultation_enabled: bool
    consultation_fee: Decimal | None
    availability: dict
    verification_status: VerificationStatus
    visibility: ProfileVisibility
    visibility_settings: dict[str, str]
    masked_groups: list[str] = Field(default_factory=list)
    avg_rating: Decimal | None
    rating_count: int


class ProfileDetail(ProfileRead):
    """Full profile view including social proof."""

    endorsement_summary: dict[str, int] = Field(
        default_factory=dict, description="skill → number of endorsements"
    )
    recommendations: list[RecommendationRead] = Field(default_factory=list)


class ProfileMasters(BaseModel):
    professional_roles: list[dict[str, str]]
    degrees: list[dict[str, str]]
    education_levels: list[dict[str, str]]
    practice_areas: list[str]
    bar_councils: list[str]
    states: list[str]
    cities_by_state: dict[str, list[str]]
    courts: list[str]
    languages: list[str]
    visibility_options: list[dict[str, str]]


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
