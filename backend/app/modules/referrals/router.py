"""Invite-link endpoint: any signed-in user can see their own link and count."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentUserDep, TenantSessionDep
from app.modules.referrals.schemas import MyReferral
from app.modules.referrals.service import ReferralService

router = APIRouter(prefix="/referrals", tags=["Referrals"])


@router.get("/me", response_model=MyReferral, summary="My invite link and how many people joined through it")
async def my_referral(current: CurrentUserDep, session: TenantSessionDep) -> MyReferral:
    return await ReferralService(session).mine(current.id)
