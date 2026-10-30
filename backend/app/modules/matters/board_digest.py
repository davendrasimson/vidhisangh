"""Morning digest of the matters that need attention — the matter board's flags, pushed.

Each member who has the app with push allowed (or WhatsApp turned on, once a
digest template is approved) gets one message a day listing the matters they
are on whose board card carries an attention flag: limitation passed or within
30 days, an overdue task, a hearing today, no next step, or nothing touched for
30 days. Built from ``MatterService.board`` for that member, in their own
tenant; sent by the ``matter_board_digest`` job at about 7.30 am India time.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.push import PushMessage, PushSender
from app.core.whatsapp import WhatsAppError, WhatsAppSender
from app.modules.identity.models import User
from app.modules.matters.schemas import BoardCard
from app.modules.matters.service import MatterService
from app.modules.notifications.models import (
    BoardDigestSend,
    NotificationChannel,
    NotificationPreference,
    PushDevice,
)

log = structlog.get_logger("app.board_digest")
IST = ZoneInfo("Asia/Kolkata")
LIST_LIMIT = 700
# Flags worth a morning message, worst first; hearing_soon and on_hold are not.
ATTENTION = ["limitation_passed", "hearing_today", "overdue_task", "limitation_soon", "no_next_step", "stale"]
LABEL = {
    "limitation_passed": "limitation passed", "hearing_today": "hearing today", "overdue_task": "overdue task",
    "limitation_soon": "limitation within 30 days", "no_next_step": "no next step", "stale": "nothing for 30 days",
}


@dataclass
class Digest:
    user_id: uuid.UUID
    name: str
    phone: str | None
    push: bool
    items: list[str] = field(default_factory=list)      # "1. Title (M-0003): limitation passed, overdue task"


def today_ist(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(IST).date()


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def describe(n: int, card: BoardCard) -> str:
    flags = [LABEL[f] for f in ATTENTION if f in card.flags]
    return f"{n}. {_clean(card.title)} ({card.matter_number}): {', '.join(flags)}"


def item_list(items: list[str]) -> str:
    out: list[str] = []
    used = 0
    for item in items:
        if used + len(item) + 2 > LIST_LIMIT:
            out.append(f"… and {len(items) - len(out)} more on the board")
            break
        out.append(item)
        used += len(item) + 2
    return "; ".join(out)


async def collect(session: AsyncSession, day: date) -> list[Digest]:
    """Members who will hear about their matters, with the cards needing attention today. Needs RLS bypass."""
    whatsapp = set(await session.scalars(
        select(NotificationPreference.user_id).where(
            NotificationPreference.channel == NotificationChannel.WHATSAPP,
            NotificationPreference.enabled.is_(True), NotificationPreference.deleted_at.is_(None),
        )
    )) if settings.WA_BOARD_DIGEST_TEMPLATE else set()
    push_off = set(await session.scalars(
        select(NotificationPreference.user_id).where(
            NotificationPreference.channel == NotificationChannel.PUSH, NotificationPreference.enabled.is_(False),
        )
    ))
    push = set(await session.scalars(select(PushDevice.user_id).distinct())) - push_off
    opted = whatsapp | push
    if not opted:
        return []
    users = (await session.scalars(
        select(User).where(User.id.in_(opted), User.deleted_at.is_(None), User.is_active.is_(True), User.tenant_id.is_not(None))
    )).all()
    digests: list[Digest] = []
    for user in users:
        phone = user.phone if user.id in whatsapp and user.is_phone_verified and user.phone else None
        if phone is None and user.id not in push:
            continue
        board = await MatterService(session, user.id, user.tenant_id).board(user_id=user.id)
        cards = [c for col in board.columns for c in col.matters if any(f in c.flags for f in ATTENTION)]
        if not cards:
            continue
        cards.sort(key=lambda c: min(ATTENTION.index(f) for f in c.flags if f in ATTENTION))
        digests.append(Digest(
            user_id=user.id, name=_clean(user.full_name) or "Counsel", phone=phone, push=user.id in push,
            items=[describe(i, c) for i, c in enumerate(cards, start=1)],
        ))
    return digests


async def send_digests(
    session: AsyncSession, sender: WhatsAppSender | None, day: date, digests: list[Digest],
    *, push: PushSender | None = None,
) -> dict[str, int]:
    """Sends each digest once per day; the row is claimed before sending, so a rerun never sends twice."""
    report = {"sent": 0, "already": 0, "failed": 0}
    when = f"{day.strftime('%a')} {day.strftime('%d/%m/%Y')}"
    for d in digests:
        exists = await session.scalar(select(BoardDigestSend.id).where(
            BoardDigestSend.user_id == d.user_id, BoardDigestSend.for_date == day))
        if exists:
            report["already"] += 1
            continue
        row = BoardDigestSend(user_id=d.user_id, for_date=day, matter_count=len(d.items), status="sending")
        session.add(row)
        await session.commit()
        delivered, problems = [], []
        if d.phone and sender is not None and settings.WA_BOARD_DIGEST_TEMPLATE:
            try:
                await sender.send_template(
                    d.phone, settings.WA_BOARD_DIGEST_TEMPLATE, settings.WA_BOARD_DIGEST_TEMPLATE_LANG,
                    [d.name, when, item_list(d.items)],
                )
                delivered.append("whatsapp")
            except WhatsAppError as exc:
                problems.append(f"whatsapp: {exc}")
        if d.push and push is not None:
            count = len(d.items)
            first = re.sub(r"^1\. ", "", d.items[0])
            body = f"{count} matter{'s' if count != 1 else ''} need{'s' if count == 1 else ''} attention: {first}" + (f" (+{count - 1} more)" if count > 1 else "")
            sent = 0
            for device in (await session.scalars(select(PushDevice).where(PushDevice.user_id == d.user_id))).all():
                result = await push.send(device.token, PushMessage(title="Your matter board", body=body, link="/app/matters/board"))
                if result == "sent":
                    sent += 1
                elif result == "unregistered":
                    await session.delete(device)
            (delivered if sent else problems).append("push" if sent else "push: not delivered")
        row.status = "sent" if delivered else "failed"
        row.detail = (", ".join(delivered) + ("; " if delivered and problems else "") + "; ".join(problems))[:200] or None
        report["sent" if delivered else "failed"] += 1
        await session.commit()
    log.info("board_digest", day=day.isoformat(), **report)
    return report
