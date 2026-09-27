"""Professional profile service — business logic."""

from __future__ import annotations

import io
import uuid

import segno
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.identity.repository import UserRepository
from app.modules.network.repository import IdentityRepository
from app.modules.notifications.models import NotificationType
from app.modules.notifications.service import create_notification
from app.modules.profile.models import (
    BarVerificationRequest,
    Endorsement,
    ProfessionalProfile,
    Recommendation,
    VerificationStatus,
)
from app.modules.profile.repository import ProfileRepository
from app.modules.profile.schemas import (
    BarVerificationCreate,
    EndorsementCreate,
    ProfileUpdate,
    RecommendationCreate,
)


def _vcard_escape(value: str) -> str:
    """Escape a value for a vCard text field (RFC 6350)."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


class ProfileService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.repo = ProfileRepository(session)

    async def get_or_create(self, user_id: uuid.UUID) -> ProfessionalProfile:
        """A profile is auto-provisioned on first access (lazy 1:1 with user)."""
        profile = await self.repo.get_by_user(user_id)
        if profile is None:
            profile = ProfessionalProfile(tenant_id=self.tenant_id, user_id=user_id)
            self.repo.add(profile)
            await self.repo.flush()
        return profile

    async def get_for_user(self, user_id: uuid.UUID) -> ProfessionalProfile:
        profile = await self.repo.get_by_user(user_id)
        if profile is None:
            raise NotFoundError("This user does not have a profile yet.")
        return profile

    async def update(self, user_id: uuid.UUID, data: ProfileUpdate) -> ProfessionalProfile:
        profile = await self.get_or_create(user_id)
        payload = data.model_dump(exclude_unset=True)
        # Education & publications are lists of pydantic models — normalise to
        # plain dicts for JSON storage.
        for list_field in ("education", "publications"):
            if payload.get(list_field) is not None:
                payload[list_field] = [
                    item if isinstance(item, dict) else item.model_dump()
                    for item in payload[list_field]
                ]
        for field, value in payload.items():
            setattr(profile, field, value)
        return profile

    async def endorsement_summary(self, profile_id: uuid.UUID) -> dict[str, int]:
        return await self.repo.endorsement_summary(profile_id)

    # ── Digital visiting card ───────────────────────────────────────
    async def build_vcard(self, user_id: uuid.UUID) -> tuple[str, str]:
        """Compose a vCard 3.0 for the user's digital visiting card.

        Returns ``(display_name, vcard_text)``.
        """
        user = await UserRepository(self.session).get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        profile = await self.get_or_create(user_id)
        name = user.display_name or user.full_name

        lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"FN:{_vcard_escape(name)}",
            f"N:{_vcard_escape(name)};;;;",
        ]
        if profile.headline:
            lines.append(f"TITLE:{_vcard_escape(profile.headline)}")
        if profile.bar_council:
            lines.append(f"ORG:{_vcard_escape(profile.bar_council)}")
        lines.append(f"EMAIL;TYPE=INTERNET:{user.email}")
        if profile.website:
            lines.append(f"URL:{_vcard_escape(profile.website)}")
        if profile.city or profile.state or profile.office_address:
            adr = (
                f";;{_vcard_escape(profile.office_address or '')}"
                f";{_vcard_escape(profile.city or '')}"
                f";{_vcard_escape(profile.state or '')};;"
            )
            lines.append(f"ADR;TYPE=WORK:{adr}")
        if profile.bio:
            lines.append(f"NOTE:{_vcard_escape(profile.bio)}")
        lines.append("END:VCARD")
        return name, "\r\n".join(lines) + "\r\n"

    def build_qr_svg(self, payload: str) -> bytes:
        """Render ``payload`` (a vCard) as an SVG QR code."""
        qr = segno.make(payload, error="m")
        buf = io.BytesIO()
        qr.save(buf, kind="svg", scale=5, border=2)
        return buf.getvalue()

    async def endorse(
        self, target_user_id: uuid.UUID, endorser_user_id: uuid.UUID, data: EndorsementCreate
    ) -> Endorsement:
        if target_user_id == endorser_user_id:
            raise ValidationError("You cannot endorse your own profile.")
        profile = await self.get_for_user(target_user_id)
        existing = await self.repo.get_endorsement(
            profile.id, endorser_user_id, data.skill
        )
        if existing is not None:
            raise ConflictError("You have already endorsed this skill.")
        endorsement = Endorsement(
            tenant_id=self.tenant_id,
            profile_id=profile.id,
            endorser_user_id=endorser_user_id,
            skill=data.skill,
        )
        self.repo.add_endorsement(endorsement)
        actor = await IdentityRepository(self.session).get(endorser_user_id)
        actor_name = actor.display_name if actor else "A colleague"
        await create_notification(
            self.session,
            user_id=target_user_id,
            type=NotificationType.ENDORSEMENT,
            actor_id=endorser_user_id,
            actor_name=actor_name,
            message=f"{actor_name} endorsed you for {data.skill}",
            link="/app/profile",
        )
        await self.repo.flush()
        return endorsement

    async def recommend(
        self, target_user_id: uuid.UUID, author_user_id: uuid.UUID, data: RecommendationCreate
    ) -> Recommendation:
        if target_user_id == author_user_id:
            raise ValidationError("You cannot recommend yourself.")
        profile = await self.get_for_user(target_user_id)
        rec = Recommendation(
            tenant_id=self.tenant_id,
            profile_id=profile.id,
            author_user_id=author_user_id,
            relationship_context=data.relationship_context,
            body=data.body,
        )
        self.repo.add_recommendation(rec)
        actor = await IdentityRepository(self.session).get(author_user_id)
        actor_name = actor.display_name if actor else "A colleague"
        await create_notification(
            self.session,
            user_id=target_user_id,
            type=NotificationType.RECOMMENDATION,
            actor_id=author_user_id,
            actor_name=actor_name,
            message=f"{actor_name} wrote you a recommendation",
            link="/app/profile",
        )
        await self.repo.flush()
        return rec

    async def request_verification(
        self, user_id: uuid.UUID, data: BarVerificationCreate
    ) -> BarVerificationRequest:
        latest = await self.repo.latest_verification(user_id)
        if latest is not None and latest.status == VerificationStatus.PENDING:
            raise ConflictError("A verification request is already pending review.")
        req = BarVerificationRequest(
            tenant_id=self.tenant_id,
            user_id=user_id,
            enrollment_number=data.enrollment_number,
            bar_council=data.bar_council,
            document_url=data.document_url,
            status=VerificationStatus.PENDING,
        )
        self.repo.add_verification(req)
        # Reflect pending state on the profile and copy enrolment details.
        profile = await self.get_or_create(user_id)
        profile.verification_status = VerificationStatus.PENDING
        profile.enrollment_number = data.enrollment_number
        profile.bar_council = data.bar_council
        await self.repo.flush()
        return req
