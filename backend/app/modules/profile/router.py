"""Professional profile HTTP endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.modules.profile.schemas import (
    BarVerificationCreate,
    BarVerificationRead,
    EndorsementCreate,
    EndorsementRead,
    ProfileDetail,
    ProfileRead,
    ProfileUpdate,
    RecommendationCreate,
    RecommendationRead,
)
from app.modules.profile.service import ProfileService

router = APIRouter(prefix="/profiles", tags=["Professional Profile"])


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> ProfileService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return ProfileService(session, current.tenant_id)


async def _detail(service: ProfileService, user_id: uuid.UUID) -> ProfileDetail:
    profile = await service.get_for_user(user_id)
    summary = await service.endorsement_summary(profile.id)
    detail = ProfileDetail.model_validate(profile)
    detail.endorsement_summary = summary
    detail.recommendations = [
        RecommendationRead.model_validate(r) for r in profile.recommendations if r.is_visible
    ]
    return detail


@router.get("/me", response_model=ProfileDetail, summary="My professional profile")
async def get_my_profile(current: CurrentUserDep, session: TenantSessionDep) -> ProfileDetail:
    service = _svc(current, session)
    await service.get_or_create(current.id)  # lazily provision on first view
    return await _detail(service, current.id)


@router.put(
    "/me",
    response_model=ProfileRead,
    summary="Update my professional profile",
    dependencies=[require_permission("profile:update")],
)
async def update_my_profile(
    data: ProfileUpdate, current: CurrentUserDep, session: TenantSessionDep
) -> ProfileRead:
    profile = await _svc(current, session).update(current.id, data)
    return ProfileRead.model_validate(profile)


@router.get(
    "/me/vcard",
    summary="Download my digital visiting card (.vcf)",
    response_class=Response,
)
async def my_vcard(current: CurrentUserDep, session: TenantSessionDep) -> Response:
    _name, vcard = await _svc(current, session).build_vcard(current.id)
    return Response(
        content=vcard,
        media_type="text/vcard",
        headers={"Content-Disposition": 'attachment; filename="vidhisangh-card.vcf"'},
    )


@router.get(
    "/me/qr",
    summary="QR code (SVG) encoding my visiting card",
    response_class=Response,
)
async def my_qr(current: CurrentUserDep, session: TenantSessionDep) -> Response:
    service = _svc(current, session)
    _name, vcard = await service.build_vcard(current.id)
    return Response(content=service.build_qr_svg(vcard), media_type="image/svg+xml")


@router.get(
    "/{user_id}",
    response_model=ProfileDetail,
    summary="View another practitioner's profile",
)
async def get_profile(
    user_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> ProfileDetail:
    return await _detail(_svc(current, session), user_id)


@router.post(
    "/{user_id}/endorsements",
    response_model=EndorsementRead,
    status_code=status.HTTP_201_CREATED,
    summary="Endorse a practitioner for a skill",
)
async def endorse(
    user_id: uuid.UUID,
    data: EndorsementCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> EndorsementRead:
    endorsement = await _svc(current, session).endorse(user_id, current.id, data)
    return EndorsementRead.model_validate(endorsement)


@router.post(
    "/{user_id}/recommendations",
    response_model=RecommendationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Write a recommendation",
)
async def recommend(
    user_id: uuid.UUID,
    data: RecommendationCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> RecommendationRead:
    rec = await _svc(current, session).recommend(user_id, current.id, data)
    return RecommendationRead.model_validate(rec)


@router.post(
    "/me/verification",
    response_model=BarVerificationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Request bar-council verification",
)
async def request_verification(
    data: BarVerificationCreate, current: CurrentUserDep, session: TenantSessionDep
) -> BarVerificationRead:
    req = await _svc(current, session).request_verification(current.id, data)
    return BarVerificationRead.model_validate(req)
