"""The Supreme Court digest on WhatsApp: one approved template per member per day.

Follows the email digest (``daily_orders.send_digests``): a member gets the
WhatsApp message for a day only after their email digest for that day was
sent, and it describes the same orders (count, the leading case and its
result), so the two never disagree. Who qualifies: an enabled Supreme Court
subscription, a verified number, and a "yes" to WhatsApp updates (the consent
ledger in ``notifications/whatsapp_updates``). Marketing template
``sc_daily_orders`` (Meta, 2 Nov 2026; en + hi), five body parameters:
first name, number of orders, date, leading case, result. Sends are claimed in
``whatsapp_campaign_sends`` under campaign ``sc-daily-<date>`` before the
API call, so a rerun never sends twice. The number is stored as an HMAC only.
"""

from __future__ import annotations

import re
import uuid
from datetime import date

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.whatsapp import WhatsAppError, WhatsAppSender
from app.modules.identity.models import User
from app.modules.notifications.models import WhatsAppCampaignSend
from app.modules.notifications.whatsapp_updates import (
    first_name,
    language_for,
    latest_choices,
    phone_hash,
)
from app.modules.profile.models import ProfessionalProfile
from app.modules.research.daily_models import DailyOrderEmail, DailyOrderSubscription
from app.modules.research.models import Judgment
from app.modules.research.schemas import AiHeadnoteContent

log = structlog.get_logger("app.sc_daily_whatsapp")

TEMPLATE = "sc_daily_orders"
CASE_MAX, RESULT_MAX = 120, 150
HINDI_MONTHS = ("जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर")


def campaign_name(day: date) -> str:
    return f"sc-daily-{day.isoformat()}"


def clean(value: str | None, limit: int) -> str:
    """Template parameters may not hold new lines or tabs; keep them short enough to read on a phone."""
    text = re.sub(r"\s+", " ", value or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def date_text(day: date, language: str) -> str:
    if language == "hi":
        return f"{day.day} {HINDI_MONTHS[day.month - 1]} {day.year}"
    return f"{day.day} {day:%B %Y}"


def parameters(*, name: str, count: int, day: date, leading: Judgment, language: str) -> list[str]:
    headnote = AiHeadnoteContent.model_validate(leading.ai_headnote)
    return [name, str(count), date_text(day, language), clean(leading.case_name, CASE_MAX), clean(headnote.result, RESULT_MAX)]


async def send_whatsapp_digests(
    session: AsyncSession, sender: WhatsAppSender, day: date, *, dry_run: bool = False,
) -> dict[str, int]:
    """Send the day's digest message to every member whose email digest for `day` went out and who
    said yes to WhatsApp updates. Needs RLS bypass. Commits after every message."""
    report = {"sent": 0, "already": 0, "failed": 0, "eligible": 0, "no_consent": 0, "no_number": 0}
    campaign = campaign_name(day)
    rows = (await session.execute(
        select(DailyOrderEmail, User)
        .join(DailyOrderSubscription, DailyOrderSubscription.id == DailyOrderEmail.subscription_id)
        .join(User, User.id == DailyOrderSubscription.user_id)
        .where(
            DailyOrderEmail.for_date == day, DailyOrderEmail.status == "sent", DailyOrderEmail.deleted_at.is_(None),
            DailyOrderSubscription.enabled.is_(True), DailyOrderSubscription.deleted_at.is_(None),
            User.is_active.is_(True), User.deleted_at.is_(None),
        )
        .order_by(DailyOrderEmail.created_at)
    )).all()
    if not rows:
        return report
    user_ids = [user.id for _, user in rows]
    choices = await latest_choices(session, user_ids)
    profiles = {p.user_id: p for p in await session.scalars(
        select(ProfessionalProfile).where(ProfessionalProfile.user_id.in_(user_ids))
    )}
    for email_row, user in rows:
        if not user.phone or not user.is_phone_verified:
            report["no_number"] += 1
            continue
        if choices.get(user.id) is not True:
            report["no_consent"] += 1
            continue
        ids = [uuid.UUID(str(i)) for i in (email_row.judgment_ids or [])]
        if not ids:
            continue
        leading = await session.scalar(select(Judgment).where(Judgment.id == ids[0], Judgment.ai_headnote.is_not(None)))
        if leading is None:
            continue
        profile = profiles.get(user.id)
        language = language_for(profile.languages if profile else None)
        body = parameters(name=first_name(user.full_name, language), count=len(ids), day=day, leading=leading, language=language)
        key = phone_hash(user.phone)
        if await session.scalar(select(WhatsAppCampaignSend.id).where(
            WhatsAppCampaignSend.campaign == campaign, WhatsAppCampaignSend.phone_hash == key,
        )):
            report["already"] += 1
            continue
        report["eligible"] += 1
        if dry_run:
            continue
        row = WhatsAppCampaignSend(
            campaign=campaign, user_id=user.id, phone_hash=key, template=TEMPLATE,
            language=language, basis="consent", status="sending",
        )
        session.add(row)
        await session.commit()  # claimed before sending: a rerun never sends twice
        try:
            await sender.send_template(user.phone, TEMPLATE, language, body)
            row.status, row.detail = "sent", None
            report["sent"] += 1
        except WhatsAppError as exc:
            row.status, row.detail = "failed", str(exc)[:200]
            report["failed"] += 1
            log.warning("sc_daily_whatsapp_failed", campaign=campaign, error=str(exc))
        await session.commit()
    log.info("sc_daily_whatsapp", campaign=campaign, **report)
    return report
