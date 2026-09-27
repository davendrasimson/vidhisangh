"""Data-access layer for professional profiles."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.profile.models import (
    BarVerificationRequest,
    Endorsement,
    ProfessionalProfile,
    Recommendation,
)


class ProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user(self, user_id: uuid.UUID) -> ProfessionalProfile | None:
        result = await self.session.execute(
            select(ProfessionalProfile)
            .where(
                ProfessionalProfile.user_id == user_id,
                ProfessionalProfile.deleted_at.is_(None),
            )
            .options(selectinload(ProfessionalProfile.recommendations))
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, profile_id: uuid.UUID) -> ProfessionalProfile | None:
        result = await self.session.execute(
            select(ProfessionalProfile).where(ProfessionalProfile.id == profile_id)
        )
        return result.scalar_one_or_none()

    def add(self, profile: ProfessionalProfile) -> None:
        self.session.add(profile)

    async def flush(self) -> None:
        await self.session.flush()

    # ── Endorsements ────────────────────────────────────────────────
    async def get_endorsement(
        self, profile_id: uuid.UUID, endorser_user_id: uuid.UUID, skill: str
    ) -> Endorsement | None:
        result = await self.session.execute(
            select(Endorsement).where(
                Endorsement.profile_id == profile_id,
                Endorsement.endorser_user_id == endorser_user_id,
                Endorsement.skill == skill,
            )
        )
        return result.scalar_one_or_none()

    async def endorsement_summary(self, profile_id: uuid.UUID) -> dict[str, int]:
        result = await self.session.execute(
            select(Endorsement.skill, func.count())
            .where(Endorsement.profile_id == profile_id)
            .group_by(Endorsement.skill)
        )
        return {skill: count for skill, count in result.all()}

    def add_endorsement(self, endorsement: Endorsement) -> None:
        self.session.add(endorsement)

    # ── Recommendations ─────────────────────────────────────────────
    def add_recommendation(self, rec: Recommendation) -> None:
        self.session.add(rec)

    # ── Verification ────────────────────────────────────────────────
    def add_verification(self, req: BarVerificationRequest) -> None:
        self.session.add(req)

    async def latest_verification(
        self, user_id: uuid.UUID
    ) -> BarVerificationRequest | None:
        result = await self.session.execute(
            select(BarVerificationRequest)
            .where(BarVerificationRequest.user_id == user_id)
            .order_by(BarVerificationRequest.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
