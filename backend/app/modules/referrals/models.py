"""Referral codes and the sign-ups they brought.

Global tables (no RLS): the person who shares a link and the person who joins
through it are in different organisations, and the count has to see both.
Only ids are stored; nobody can see who joined through their link, only how many.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import AuditedBase


class ReferralCode(AuditedBase):
    __tablename__ = "referral_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)


class Referral(AuditedBase):
    __tablename__ = "referrals"

    referrer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    referred_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
