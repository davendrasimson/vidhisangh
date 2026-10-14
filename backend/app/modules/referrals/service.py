"""Personal invite links ("Tell a friend") and credit for the sign-ups they bring."""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.referrals.models import Referral, ReferralCode
from app.modules.referrals.repository import ReferralRepository
from app.modules.referrals.schemas import MyReferral

log = get_logger("app.referrals")

SITE = "https://vidhisangh.com"
# No 0/O/1/I/L: codes get read aloud and retyped from WhatsApp screenshots.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 7


def normalise_code(code: str | None) -> str | None:
    code = (code or "").strip().upper()
    return code if 4 <= len(code) <= 16 and all(c in ALPHABET for c in code) else None


class ReferralService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = ReferralRepository(session)

    async def my_code(self, user_id: uuid.UUID) -> ReferralCode:
        existing = await self.repo.code_for(user_id)
        if existing:
            return existing
        while True:
            code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
            if not await self.repo.code_exists(code):
                break
        row = ReferralCode(user_id=user_id, code=code)
        self.repo.add(row)
        await self.repo.session.flush()
        return row

    async def mine(self, user_id: uuid.UUID) -> MyReferral:
        row = await self.my_code(user_id)
        return MyReferral(
            code=row.code,
            link=f"{SITE}/?ref={row.code}&utm_source=tell_a_friend",
            joined=await self.repo.joined_count(user_id),
        )

    async def record_signup(self, code: str | None, new_user_id: uuid.UUID) -> None:
        """Credit the owner of `code` with this sign-up. A bad or unknown code is
        ignored: it must never stop someone from registering."""
        code = normalise_code(code)
        if not code:
            return
        owner = await self.repo.by_code(code)
        if owner is None or owner.user_id == new_user_id:
            return
        self.repo.add(Referral(referrer_user_id=owner.user_id, referred_user_id=new_user_id))
        await self.repo.session.flush()
        log.info("referral_recorded", referrer_user_id=str(owner.user_id), user_id=str(new_user_id))
