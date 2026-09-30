"""WhatsApp authentication: expiring, hashed, single-use codes and bounded retries."""

from __future__ import annotations

import asyncio
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.exceptions import AuthenticationError, ServiceUnavailableError
from app.modules.identity.models import PhoneOtpChallenge, User


def normalize_phone(value: str) -> str:
    value = re.sub(r"[\s()\-]", "", value)
    if re.fullmatch(r"[6-9][0-9]{9}", value):
        value = "+91" + value
    elif re.fullmatch(r"91[6-9][0-9]{9}", value):
        value = "+" + value
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", value):
        raise ValueError("Enter a valid mobile number with country code, e.g. +91 9876543210.")
    return value


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _hash(challenge_id: uuid.UUID, code: str) -> str:
    return security.hash_link_token(f"whatsapp:{challenge_id}:{code}")


async def send_whatsapp_code(phone: str, code: str) -> None:
    token = settings.WA_ACCESS_TOKEN
    if not token and settings.WA_ACCESS_TOKEN_FILE:
        try:
            token = (await asyncio.to_thread(Path(settings.WA_ACCESS_TOKEN_FILE).read_text)).strip()
        except OSError as exc:
            raise ServiceUnavailableError("WhatsApp sign-in is temporarily unavailable.") from exc
    if not token or not settings.WA_PHONE_NUMBER_ID or not settings.WA_OTP_TEMPLATE:
        raise ServiceUnavailableError("WhatsApp sign-in is temporarily unavailable.")
    # Same approved Simsondesk template, including its four body parameters
    # and Copy-code button. Never log codes, tokens, payloads or provider bodies.
    values = [code, "VidhiSangh", "5 minutes", settings.WA_OTP_CALL_NUMBER, settings.WA_OTP_CONTACT]
    payload = {
        "messaging_product": "whatsapp",
        "to": phone.lstrip("+"),
        "type": "template",
        "template": {
            "name": settings.WA_OTP_TEMPLATE,
            "language": {"code": settings.WA_OTP_TEMPLATE_LANG},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": value[:15]} for value in values],
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": code}],
                },
            ],
        },
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://graph.facebook.com/{settings.WA_API_VERSION}/"
                f"{settings.WA_PHONE_NUMBER_ID}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            response.raise_for_status()
            if not response.json().get("messages"):
                raise ValueError("No message accepted")
    except (httpx.HTTPError, ValueError) as exc:
        raise ServiceUnavailableError(
            "Unable to send the WhatsApp code. Try again shortly."
        ) from exc


async def phone_user(session: AsyncSession, phone: str) -> User | None:
    user: User | None = await session.scalar(
        select(User).where(
            User.phone == phone, User.is_phone_verified.is_(True), User.deleted_at.is_(None)
        )
    )

    return user


async def request_code(session: AsyncSession, phone: str, purpose: str) -> PhoneOtpChallenge:
    from app.core.ratelimit import RateLimiter

    subject = security.hash_link_token(phone)
    await RateLimiter(times=1, window_seconds=60, scope="wa-cooldown", fail_closed=True).check(
        subject
    )
    await RateLimiter(times=5, window_seconds=3600, scope="wa-phone", fail_closed=True).check(
        subject
    )
    user = await phone_user(session, phone)
    eligible = (purpose == "register" and user is None) or (
        purpose == "login" and user is not None and user.is_active
    )
    await session.execute(
        update(PhoneOtpChallenge)
        .where(
            PhoneOtpChallenge.phone == phone,
            PhoneOtpChallenge.purpose == purpose,
            PhoneOtpChallenge.consumed.is_(False),
        )
        .values(consumed=True)
    )
    code = f"{secrets.randbelow(1000000):06d}"
    challenge_id = uuid.uuid4()
    row = PhoneOtpChallenge(
        id=challenge_id,
        phone=phone,
        purpose=purpose,
        code_hash=_hash(challenge_id, code),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        user_id=user.id if purpose == "login" and user else None,
        # Ineligible requests look identical but can never authenticate.
        consumed=not eligible,
    )
    session.add(row)
    await session.flush()
    if eligible:
        await send_whatsapp_code(phone, code)
    return row


async def consume_code(
    session: AsyncSession,
    challenge_id: uuid.UUID | None,
    code: str | None,
    *,
    purpose: str,
    phone: str | None = None,
) -> PhoneOtpChallenge:
    row = await session.scalar(
        select(PhoneOtpChallenge)
        .where(
            PhoneOtpChallenge.id == challenge_id,
        )
        .with_for_update()
    )
    if (
        row is None
        or row.consumed
        or row.purpose != purpose
        or (phone is not None and row.phone != phone)
        or _utc(row.expires_at) <= datetime.now(UTC)
        or row.attempts >= 5
    ):
        raise AuthenticationError("This WhatsApp code is invalid or expired. Request a new code.")
    row.attempts += 1
    if not secrets.compare_digest(row.code_hash, _hash(row.id, code or "")):
        if row.attempts >= 5:
            row.consumed = True
        # Persist failed guesses even though the endpoint returns an error.
        await session.commit()
        raise AuthenticationError("Incorrect WhatsApp code. Please try again.")
    row.consumed = True
    await session.flush()
    return row
