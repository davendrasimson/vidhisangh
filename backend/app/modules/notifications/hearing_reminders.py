"""Evening WhatsApp reminder of tomorrow's hearings.

Each member who turned on WhatsApp under Settings → Notifications and has a
verified mobile number gets one message a day listing the hearings on the
matters they are on (lead counsel, assigned, or an active team member; the
matter's creator when nobody is). Sent by the ``hearing_reminders`` job at
about 7 pm India time through the approved ``hearing_reminder`` template.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.whatsapp import WhatsAppError, WhatsAppSender
from app.modules.identity.models import User
from app.modules.matters.models import Hearing, HearingStatus, Matter, MatterStatus, MatterTeamMember
from app.modules.notifications.models import (
    HearingReminderSend,
    NotificationChannel,
    NotificationPreference,
)

log = structlog.get_logger("app.hearing_reminders")
IST = ZoneInfo("Asia/Kolkata")
# The template's list parameter: WhatsApp allows ~1,000 characters; leave room.
LIST_LIMIT = 700


@dataclass
class Reminder:
    user_id: uuid.UUID
    name: str
    phone: str
    hearings: list[str] = field(default_factory=list)


def tomorrow_ist(now: datetime | None = None) -> date:
    return ((now or datetime.now(UTC)).astimezone(IST) + timedelta(days=1)).date()


def _clean(value: str | None) -> str:
    # Template parameters may not contain new lines, tabs or runs of spaces.
    return re.sub(r"\s+", " ", value or "").strip()


def describe(n: int, matter: Matter, hearing: Hearing) -> str:
    parts = [f"{n}. {_clean(matter.title)}"]
    if matter.case_number:
        parts[0] += f" ({_clean(matter.case_number)})"
    court = _clean(hearing.court or matter.court)
    if court:
        parts.append(court)
    local = hearing.scheduled_on.astimezone(IST) if hearing.scheduled_on.tzinfo else hearing.scheduled_on.replace(tzinfo=UTC).astimezone(IST)
    if local.time() != time(0, 0):
        parts.append(local.strftime("%I:%M %p").lstrip("0").lower())
    text = ", ".join(parts)
    if hearing.purpose:
        text += f", for {_clean(hearing.purpose)}"
    return text


def hearing_list(items: list[str]) -> str:
    """Joined in one line, cut with "and N more" to fit the template."""
    shown: list[str] = []
    for item in items:
        rest = len(items) - len(shown) - 1
        candidate = "; ".join([*shown, item]) + (f"; and {rest} more" if rest else "")
        if shown and len(candidate) > LIST_LIMIT:
            break
        shown.append(item[:LIST_LIMIT])
    rest = len(items) - len(shown)
    return "; ".join(shown) + (f"; and {rest} more" if rest else "")


async def collect(session: AsyncSession, day: date) -> list[Reminder]:
    """Opted-in members with hearings on ``day`` (India time). Needs RLS bypass."""
    opted = set(await session.scalars(
        select(NotificationPreference.user_id).where(
            NotificationPreference.channel == NotificationChannel.WHATSAPP,
            NotificationPreference.enabled.is_(True),
            NotificationPreference.deleted_at.is_(None),
        )
    ))
    if not opted:
        return []
    start = datetime.combine(day, time(0, 0), IST).astimezone(UTC)
    rows = (await session.execute(
        select(Hearing, Matter).join(Matter, Matter.id == Hearing.matter_id).where(
            Hearing.deleted_at.is_(None), Matter.deleted_at.is_(None),
            Hearing.status.in_([HearingStatus.SCHEDULED, HearingStatus.ADJOURNED]),
            Matter.status != MatterStatus.CLOSED,
            Hearing.scheduled_on >= start, Hearing.scheduled_on < start + timedelta(days=1),
        ).order_by(Hearing.scheduled_on)
    )).all()
    if not rows:
        return []
    matter_ids = {m.id for _, m in rows}
    team: dict[uuid.UUID, set[uuid.UUID]] = {}
    for member in await session.scalars(
        select(MatterTeamMember).where(
            MatterTeamMember.matter_id.in_(matter_ids), MatterTeamMember.deleted_at.is_(None),
            or_(MatterTeamMember.to_date.is_(None), MatterTeamMember.to_date >= day),
            or_(MatterTeamMember.from_date.is_(None), MatterTeamMember.from_date <= day),
        )
    ):
        team.setdefault(member.matter_id, set()).add(member.user_id)

    per_user: dict[uuid.UUID, list[tuple[Matter, Hearing]]] = {}
    for hearing, matter in rows:
        people = {u for u in (matter.lead_counsel_id, matter.assigned_to) if u} | team.get(matter.id, set())
        if not people and matter.created_by:
            people = {matter.created_by}
        for user_id in people & opted:
            per_user.setdefault(user_id, []).append((matter, hearing))
    if not per_user:
        return []
    users = {u.id: u for u in await session.scalars(
        select(User).where(
            User.id.in_(per_user), User.deleted_at.is_(None), User.is_active.is_(True),
            User.is_phone_verified.is_(True), User.phone.is_not(None),
        )
    )}
    reminders = []
    for user_id, items in per_user.items():
        user = users.get(user_id)
        if user is None:
            continue
        reminders.append(Reminder(
            user_id=user_id, name=_clean(user.full_name) or "Counsel", phone=user.phone,
            hearings=[describe(i, m, h) for i, (m, h) in enumerate(items, start=1)],
        ))
    return reminders


async def send_reminders(
    session: AsyncSession, sender: WhatsAppSender, day: date, reminders: list[Reminder],
) -> dict[str, int]:
    """Sends each reminder once per day; commits after every member."""
    report = {"sent": 0, "already": 0, "failed": 0}
    when = f"{day.strftime('%a')} {day.strftime('%d/%m/%Y')}"
    for r in reminders:
        exists = await session.scalar(select(HearingReminderSend.id).where(
            HearingReminderSend.user_id == r.user_id, HearingReminderSend.for_date == day))
        if exists:
            report["already"] += 1
            continue
        row = HearingReminderSend(user_id=r.user_id, for_date=day, hearing_count=len(r.hearings), status="sending")
        session.add(row)
        await session.commit()  # claimed before sending: a rerun never sends twice
        try:
            await sender.send_template(
                r.phone, settings.WA_REMINDER_TEMPLATE, settings.WA_REMINDER_TEMPLATE_LANG,
                [r.name, when, hearing_list(r.hearings)],
            )
        except WhatsAppError as exc:
            row.status, row.detail = "failed", str(exc)[:200]
            report["failed"] += 1
        else:
            row.status = "sent"
            report["sent"] += 1
        await session.commit()
    log.info("hearing_reminders", day=day.isoformat(), **report)
    return report
