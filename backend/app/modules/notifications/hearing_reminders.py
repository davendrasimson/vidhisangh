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
from app.core.push import PushMessage, PushSender
from app.core.whatsapp import WhatsAppError, WhatsAppSender
from app.modules.identity.models import User
from app.modules.matters.models import Hearing, HearingStatus, Matter, MatterStatus, MatterTeamMember
from app.modules.notifications.models import (
    HearingReminderSend,
    NotificationChannel,
    NotificationPreference,
    PushDevice,
)

log = structlog.get_logger("app.hearing_reminders")
IST = ZoneInfo("Asia/Kolkata")
# The template's list parameter: WhatsApp allows ~1,000 characters; leave room.
LIST_LIMIT = 700


@dataclass
class Reminder:
    user_id: uuid.UUID
    name: str
    phone: str | None  # set when the member turned WhatsApp reminders on (verified number)
    hearings: list[str] = field(default_factory=list)
    push: bool = False  # the member has the app with push allowed


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
    room = _clean(hearing.court_room)
    if room:
        parts.append(room if room.lower().startswith(("court", "room", "hall")) else f"Court {room}")
    item = _clean(hearing.item_number)
    if item:
        parts.append(item if item.lower().startswith("item") else f"item {item}")
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
    """Members with hearings on ``day`` (India time) who will hear about them:
    WhatsApp turned on, or the app with push allowed. Needs RLS bypass."""
    whatsapp = set(await session.scalars(
        select(NotificationPreference.user_id).where(
            NotificationPreference.channel == NotificationChannel.WHATSAPP,
            NotificationPreference.enabled.is_(True),
            NotificationPreference.deleted_at.is_(None),
        )
    ))
    push_off = set(await session.scalars(
        select(NotificationPreference.user_id).where(
            NotificationPreference.channel == NotificationChannel.PUSH,
            NotificationPreference.enabled.is_(False),
        )
    ))
    push = set(await session.scalars(select(PushDevice.user_id).distinct())) - push_off
    opted = whatsapp | push
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
        select(User).where(User.id.in_(per_user), User.deleted_at.is_(None), User.is_active.is_(True))
    )}
    reminders = []
    for user_id, items in per_user.items():
        user = users.get(user_id)
        if user is None:
            continue
        phone = user.phone if user_id in whatsapp and user.is_phone_verified and user.phone else None
        if phone is None and user_id not in push:
            continue
        reminders.append(Reminder(
            user_id=user_id, name=_clean(user.full_name) or "Counsel", phone=phone,
            hearings=[describe(i, m, h) for i, (m, h) in enumerate(items, start=1)], push=user_id in push,
        ))
    return reminders


async def send_reminders(
    session: AsyncSession, sender: WhatsAppSender | None, day: date, reminders: list[Reminder],
    *, push: PushSender | None = None,
) -> dict[str, int]:
    """Sends each reminder once per day (WhatsApp and/or push); commits after every member."""
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
        delivered, problems = [], []
        if r.phone and sender is not None:
            try:
                await sender.send_template(
                    r.phone, settings.WA_REMINDER_TEMPLATE, settings.WA_REMINDER_TEMPLATE_LANG,
                    [r.name, when, hearing_list(r.hearings)],
                )
                delivered.append("whatsapp")
            except WhatsAppError as exc:
                problems.append(f"whatsapp: {exc}")
        if r.push and push is not None:
            count = len(r.hearings)
            first = re.sub(r"^1\. ", "", r.hearings[0]) if r.hearings else ""
            body = f"{count} hearing{'s' if count != 1 else ''} tomorrow, {when}: {first}" + (f" (+{count - 1} more)" if count > 1 else "")
            sent = 0
            for device in (await session.scalars(select(PushDevice).where(PushDevice.user_id == r.user_id))).all():
                result = await push.send(device.token, PushMessage(title="Tomorrow's hearings", body=body, link="/app/calendar"))
                if result == "sent":
                    sent += 1
                elif result == "unregistered":
                    await session.delete(device)
            (delivered if sent else problems).append("push" if sent else "push: not delivered")
        row.status = "sent" if delivered else "failed"
        row.detail = (", ".join(delivered) + ("; " if delivered and problems else "") + "; ".join(problems))[:200] or None
        report["sent" if delivered else "failed"] += 1
        await session.commit()
    log.info("hearing_reminders", day=day.isoformat(), **report)
    return report
