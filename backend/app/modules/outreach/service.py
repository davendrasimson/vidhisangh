"""Outreach: import contacts, send the daily invitations, unsubscribe, conversions."""

from __future__ import annotations

import csv
import io
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.outreach_mail import OutreachMessage, OutreachSender, RecipientRefused
from app.modules.identity.models import User
from app.modules.outreach import email as invitation
from app.modules.outreach.models import (
    OutreachContact,
    OutreachSettings,
    OutreachStatus,
    OutreachSuppression,
)

log = structlog.get_logger("app.outreach")
IST = ZoneInfo("Asia/Kolkata")
MAX_IMPORT_ROWS = 20_000


def email_hash(email: str) -> str:
    return security.hash_link_token("outreach:" + email.strip().lower())


def _normalise(raw: str) -> str | None:
    try:
        return validate_email(raw.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        return None


async def get_settings(session: AsyncSession) -> OutreachSettings:
    row = await session.scalar(select(OutreachSettings).limit(1))
    if row is None:
        row = OutreachSettings(paused=True, daily_limit=settings.OUTREACH_DAILY_LIMIT)
        session.add(row)
        await session.flush()
    return row


async def update_settings(session: AsyncSession, *, paused: bool | None, daily_limit: int | None) -> OutreachSettings:
    row = await get_settings(session)
    if paused is not None:
        row.paused = paused
    if daily_limit is not None:
        row.daily_limit = max(0, min(daily_limit, settings.OUTREACH_DAILY_LIMIT))
    await session.flush()
    return row


async def _suppressed(session: AsyncSession, email: str) -> bool:
    return await session.scalar(
        select(func.count()).select_from(OutreachSuppression).where(OutreachSuppression.email_hash == email_hash(email))
    ) > 0


async def _suppress(session: AsyncSession, email: str, reason: str) -> None:
    if not await _suppressed(session, email):
        session.add(OutreachSuppression(email_hash=email_hash(email), reason=reason))


async def _member_id(session: AsyncSession, email: str) -> uuid.UUID | None:
    return await session.scalar(
        select(User.id).where(func.lower(User.email) == email.lower(), User.deleted_at.is_(None))
    )


async def import_contacts(session: AsyncSession, data: bytes, default_source: str | None) -> dict[str, int]:
    """CSV with a header row: email (required), name, city, court, source.

    `source` (where the address was found) is required per row or as the
    default for the file: it is printed in the email. Duplicates, members and
    suppressed addresses are counted and not added.
    """
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    fields = {f.strip().lower(): f for f in (reader.fieldnames or [])}
    if "email" not in fields:
        raise ValueError("The file needs a header row with an 'email' column.")
    report = {"added": 0, "duplicate": 0, "member": 0, "unsubscribed": 0, "invalid": 0, "no_source": 0}
    seen: set[str] = set()
    existing = set(await session.scalars(select(OutreachContact.email)))
    # Rows of one file share a timestamp; a microsecond step keeps file order
    # as the sending order.
    stamp = datetime.now(UTC)
    for i, row in enumerate(reader):
        if i >= MAX_IMPORT_ROWS:
            break
        get = lambda key: (row.get(fields[key]) or "").strip() if key in fields else ""  # noqa: E731
        email = _normalise(get("email"))
        if not email:
            report["invalid"] += 1
            continue
        if email in seen or email in existing:
            report["duplicate"] += 1
            continue
        seen.add(email)
        source = (get("source") or (default_source or "").strip())[:300]
        if not source:
            report["no_source"] += 1
            continue
        if await _suppressed(session, email):
            report["unsubscribed"] += 1
            continue
        if await _member_id(session, email):
            report["member"] += 1
            continue
        session.add(OutreachContact(
            email=email, name=get("name")[:200] or None, city=get("city")[:120] or None,
            court=get("court")[:200] or None, source=source, status=OutreachStatus.QUEUED,
            token=secrets.token_urlsafe(32), created_at=stamp + timedelta(microseconds=i),
        ))
        report["added"] += 1
    await session.flush()
    return report


def _today_ist_start(now: datetime) -> datetime:
    local = now.astimezone(IST)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


async def sent_today(session: AsyncSession, now: datetime | None = None) -> int:
    start = _today_ist_start(now or datetime.now(UTC))
    return int(await session.scalar(
        select(func.count()).select_from(OutreachContact).where(OutreachContact.sent_at >= start)
    ) or 0)


def message_for(contact: OutreachContact) -> OutreachMessage:
    subject, text, html = invitation.build(name=contact.name, source=contact.source, token=contact.token)
    return OutreachMessage(
        to=contact.email, subject=subject, text=text, html=html,
        one_click_url=invitation.one_click_url(contact.token),
        unsubscribe_page=invitation.unsubscribe_url(contact.token),
    )


async def budget_today(session: AsyncSession, now: datetime | None = None) -> int:
    """How many more invitations may go out today: the daily number minus those sent (IST)."""
    cfg = await get_settings(session)
    return max(0, min(cfg.daily_limit, settings.OUTREACH_DAILY_LIMIT) - await sent_today(session, now))


async def queued_count(session: AsyncSession) -> int:
    return int(await session.scalar(
        select(func.count()).select_from(OutreachContact)
        .where(OutreachContact.status == OutreachStatus.QUEUED, OutreachContact.deleted_at.is_(None))
    ) or 0)


async def send_batch(
    session: AsyncSession, sender: OutreachSender, *, now: datetime | None = None, pause=None, force: bool = False,
) -> dict[str, int]:
    """Send today's invitations: up to the daily limit minus what went out today (IST).

    `pause` is awaited between messages (the job spaces them out). Commits
    after every contact, so a crash never re-sends. `force` sends even while
    scheduled sending is paused (the admin's "Send now"); the daily number
    still holds, and is re-checked before every message so two runs at once
    (two API workers, or the timer and the admin) cannot exceed it together.
    """
    report = {"sent": 0, "skipped": 0, "bounced": 0, "failed": 0}
    cfg = await get_settings(session)
    if cfg.paused and not force:
        return report
    while (budget := await budget_today(session, now)) > 0:
        contact = await session.scalar(
            select(OutreachContact).where(OutreachContact.status == OutreachStatus.QUEUED, OutreachContact.deleted_at.is_(None))
            .order_by(OutreachContact.created_at, OutreachContact.id).limit(1).with_for_update(skip_locked=True)
        )
        if contact is None:
            break
        if await _suppressed(session, contact.email):
            contact.status = OutreachStatus.SKIPPED
            report["skipped"] += 1
        elif member := await _member_id(session, contact.email):
            contact.status, contact.joined_user_id = OutreachStatus.JOINED, member
            report["skipped"] += 1
        else:
            try:
                await sender.send(message_for(contact))
            except RecipientRefused as exc:
                contact.status, contact.last_error = OutreachStatus.BOUNCED, str(exc)[:500]
                await _suppress(session, contact.email, "bounced")
                report["bounced"] += 1
            except Exception as exc:  # noqa: BLE001 - the provider is down: stop, try tomorrow
                contact.last_error = f"{type(exc).__name__}: {exc}"[:500]
                await session.commit()
                log.warning("outreach_send_failed", error=type(exc).__name__)
                report["failed"] += 1
                break
            else:
                contact.status, contact.sent_at = OutreachStatus.SENT, now or datetime.now(UTC)
                report["sent"] += 1
                budget -= 1
        await session.commit()
        if pause and budget > 0 and contact.status == OutreachStatus.SENT:
            await pause()
    log.info("outreach_batch", **report)
    return report


async def unsubscribe(session: AsyncSession, token: str) -> bool:
    """Idempotent. True when the token belonged to a contact."""
    contact = await session.scalar(select(OutreachContact).where(OutreachContact.token == token))
    if contact is None:
        return False
    if contact.status != OutreachStatus.UNSUBSCRIBED:
        contact.status = OutreachStatus.UNSUBSCRIBED
        contact.unsubscribed_at = datetime.now(UTC)
    await _suppress(session, contact.email, "unsubscribed")
    await session.flush()
    log.info("outreach_unsubscribed")
    return True


async def mark_joined(session: AsyncSession, email: str | None, user_id: uuid.UUID) -> None:
    """Called at sign-up: an invited (or queued) address became a member."""
    if not email:
        return
    contact = await session.scalar(select(OutreachContact).where(OutreachContact.email == email.lower()))
    if contact is not None and contact.status in (OutreachStatus.QUEUED, OutreachStatus.SENT):
        contact.status, contact.joined_user_id = OutreachStatus.JOINED, user_id


async def overview(session: AsyncSession) -> dict:
    counts = dict((await session.execute(
        select(OutreachContact.status, func.count()).group_by(OutreachContact.status)
    )).all())
    cfg = await get_settings(session)
    recent = (await session.scalars(
        select(OutreachContact).where(OutreachContact.status != OutreachStatus.QUEUED)
        .order_by(OutreachContact.updated_at.desc()).limit(25)
    )).all()
    week_ago = datetime.now(UTC) - timedelta(days=7)
    return {
        "paused": cfg.paused,
        "daily_limit": cfg.daily_limit,
        "max_daily_limit": settings.OUTREACH_DAILY_LIMIT,
        "sender_configured": bool(settings.OUTREACH_SMTP_HOST),
        "from_address": settings.OUTREACH_FROM,
        "sent_today": await sent_today(session),
        "sent_last_7_days": int(await session.scalar(
            select(func.count()).select_from(OutreachContact).where(OutreachContact.sent_at >= week_ago)) or 0),
        "counts": {s.value: int(counts.get(s.value, counts.get(s, 0))) for s in OutreachStatus},
        "suppressed_total": int(await session.scalar(select(func.count()).select_from(OutreachSuppression)) or 0),
        "recent": [
            {"email": c.email, "name": c.name, "status": c.status, "source": c.source,
             "sent_at": c.sent_at, "updated_at": c.updated_at}
            for c in recent
        ],
    }
