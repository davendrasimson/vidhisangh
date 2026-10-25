"""Product updates on WhatsApp: the member's consent and campaign sends.

Consent is an append-only ledger (``WhatsAppUpdatesConsent``): the latest row
per member is their choice; no row means "not asked yet". A member gives or
withdraws it on the Home card or in Settings → Notifications.

A campaign sends one approved marketing template per verified number:
``judicial_officer_update`` to judicial officers (and, by the owner's choice of
25 Oct 2026, to members who have not picked a profession), ``product_update``
to everyone else, in Hindi when the profile lists Hindi but not English. Only
members who said yes are sent to, unless the run is ``owner_approved`` (the
one-off launch send authorised before the opt-in existed); a "no" is always
respected. The send log keeps an HMAC of the number, never the number.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.whatsapp import WhatsAppError, WhatsAppSender
from app.modules.identity.models import User
from app.modules.notifications.models import WhatsAppCampaignSend, WhatsAppUpdatesConsent
from app.modules.privacy.config import privacy_setting
from app.modules.privacy.consent import coarse_ip
from app.modules.profile.models import ProfessionalProfile

log = structlog.get_logger("app.whatsapp_updates")

JUDICIAL_TEMPLATE = "judicial_officer_update"
GENERAL_TEMPLATE = "product_update"
# Professions sent the judicial template; "" stands for "not picked yet".
JUDICIAL_AUDIENCE = {"judicial_officer", ""}

Choice = Literal["granted", "refused", "unasked"]
Basis = Literal["consent", "owner_approved"]


# ─── Consent ────────────────────────────────────────────────────────
async def latest_choices(session: AsyncSession, user_ids: list[uuid.UUID] | None = None) -> dict[uuid.UUID, bool]:
    """Each member's current choice (True yes / False no); absent = not asked."""
    query = select(WhatsAppUpdatesConsent).where(WhatsAppUpdatesConsent.deleted_at.is_(None)).order_by(
        WhatsAppUpdatesConsent.recorded_at
    )
    if user_ids is not None:
        query = query.where(WhatsAppUpdatesConsent.user_id.in_(user_ids))
    choices: dict[uuid.UUID, bool] = {}
    for row in await session.scalars(query):
        choices[row.user_id] = row.granted  # later rows win
    return choices


async def choice_of(session: AsyncSession, user_id: uuid.UUID) -> Choice:
    granted = (await latest_choices(session, [user_id])).get(user_id)
    return "unasked" if granted is None else "granted" if granted else "refused"


async def record_choice(
    session: AsyncSession, user_id: uuid.UUID, granted: bool, source: str, ip: str | None,
) -> None:
    session.add(WhatsAppUpdatesConsent(
        user_id=user_id, granted=granted, source=source,
        notice_version=str(privacy_setting("CURRENT_PRIVACY_NOTICE_VERSION")), ip_coarse=coarse_ip(ip),
        recorded_at=datetime.now(UTC),
    ))
    await session.flush()


# ─── Campaigns ──────────────────────────────────────────────────────
@dataclass
class Recipient:
    user_id: uuid.UUID
    phone: str
    first_name: str
    template: str
    language: str
    basis: Basis


def phone_hash(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return hmac.new(settings.SECRET_KEY.encode(), digits.encode(), hashlib.sha256).hexdigest()


_HONORIFIC = re.compile(r"^(adv\.?|advocate|hon'?ble|justice|dr\.?|mr\.?|ms\.?|mrs\.?|shri|smt\.?|sh\.?)\s+", re.I)


def first_name(full_name: str | None, language: str) -> str:
    """The {{1}} greeting. Template parameters may not hold new lines or tabs."""
    name = re.sub(r"\s+", " ", full_name or "").strip()
    while (stripped := _HONORIFIC.sub("", name)) != name:  # "Hon'ble Justice …"
        name = stripped
    first = name.split(" ")[0] if name else ""
    if len(first) < 2:
        return "जी" if language == "hi" else "there"
    return first[:40]


def language_for(languages: list | None) -> str:
    spoken = {str(item).strip().lower() for item in (languages or [])}
    return "hi" if "hindi" in spoken and "english" not in spoken else "en"


async def collect(session: AsyncSession, *, owner_approved: bool) -> tuple[list[Recipient], dict[str, int]]:
    """Who gets this campaign. Needs RLS bypass (users and profiles are tenant
    rows). One message per number: a number shared by several accounts gets
    the judicial template if any of them qualifies for it."""
    users = list(await session.scalars(select(User).where(
        User.deleted_at.is_(None), User.is_active.is_(True), User.phone.is_not(None),
    )))
    skipped = {"unverified_number": 0, "said_no": 0, "not_asked": 0}
    profiles = {p.user_id: p for p in await session.scalars(
        select(ProfessionalProfile).where(ProfessionalProfile.user_id.in_([u.id for u in users]))
    )} if users else {}
    choices = await latest_choices(session, [u.id for u in users]) if users else {}
    by_number: dict[str, Recipient] = {}
    for user in sorted(users, key=lambda u: u.created_at):
        if not user.is_phone_verified:
            skipped["unverified_number"] += 1
            continue
        choice = choices.get(user.id)
        if choice is False:
            skipped["said_no"] += 1
            continue
        if choice is None and not owner_approved:
            skipped["not_asked"] += 1
            continue
        profile = profiles.get(user.id)
        role = (profile.professional_role or "") if profile else ""
        language = language_for(profile.languages if profile else None)
        recipient = Recipient(
            user_id=user.id, phone=user.phone, first_name=first_name(user.full_name, language),
            template=JUDICIAL_TEMPLATE if role in JUDICIAL_AUDIENCE else GENERAL_TEMPLATE,
            language=language, basis="consent" if choice else "owner_approved",
        )
        key = phone_hash(user.phone)
        current = by_number.get(key)
        if current is None or (current.template != JUDICIAL_TEMPLATE and recipient.template == JUDICIAL_TEMPLATE):
            by_number[key] = recipient
    return list(by_number.values()), skipped


async def send_campaign(
    session: AsyncSession, sender: WhatsAppSender, campaign: str, recipients: list[Recipient],
) -> dict[str, int]:
    """Sends each number the campaign once; commits after every message."""
    report = {"sent": 0, "already": 0, "failed": 0}
    for r in recipients:
        key = phone_hash(r.phone)
        if await session.scalar(select(WhatsAppCampaignSend.id).where(
            WhatsAppCampaignSend.campaign == campaign, WhatsAppCampaignSend.phone_hash == key,
        )):
            report["already"] += 1
            continue
        row = WhatsAppCampaignSend(
            campaign=campaign, user_id=r.user_id, phone_hash=key, template=r.template,
            language=r.language, basis=r.basis, status="sending",
        )
        session.add(row)
        await session.commit()  # claimed before sending: a rerun never sends twice
        try:
            await sender.send_template(r.phone, r.template, r.language, [r.first_name])
            row.status, row.detail = "sent", None
            report["sent"] += 1
        except WhatsAppError as exc:
            row.status, row.detail = "failed", str(exc)[:200]
            report["failed"] += 1
            log.warning("whatsapp_update_failed", campaign=campaign, template=r.template, error=str(exc))
        await session.commit()
    return report
