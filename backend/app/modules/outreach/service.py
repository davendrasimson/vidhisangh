"""Outreach: import contacts, send the daily invitations, unsubscribe, conversions."""

from __future__ import annotations

import csv
import io
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.outreach_mail import OutreachMessage, OutreachSender, RecipientRefused
from app.modules.identity.models import User
from app.modules.outreach import email as invitation
from app.modules.outreach.models import (
    OutreachContact,
    OutreachFollowUp,
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


def normalise_mobile(raw: str | None) -> str | None:
    """An Indian mobile as 10 digits ('+91 98765-43210', '09876543210' → '9876543210'); else None."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


async def get_settings(session: AsyncSession) -> OutreachSettings:
    row = await session.scalar(select(OutreachSettings).limit(1))
    if row is None:
        row = OutreachSettings(paused=True, daily_limit=settings.OUTREACH_DAILY_LIMIT)
        session.add(row)
        await session.flush()
    return row


async def update_settings(
    session: AsyncSession, *, paused: bool | None, daily_limit: int | None, focus: str | None = None,
) -> OutreachSettings:
    row = await get_settings(session)
    if paused is not None:
        row.paused = paused
    if daily_limit is not None:
        row.daily_limit = max(0, min(daily_limit, settings.OUTREACH_DAILY_LIMIT))
    if focus is not None:
        row.focus = (RANDOM if is_random(focus) else focus.strip()[:200]) or None
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
    """CSV with a header row: email (required), name, mobile, city, court, source.

    `source` (where the address was found) is required per row or as the
    default for the file: it is printed in the email. Duplicates, members and
    suppressed addresses are counted and not added. `mobile` (or `phone`) is
    kept as 10 digits when it looks like an Indian mobile.
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
        get = lambda key: (row.get(fields[key]) or "").strip() if key in fields else ""
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
            mobile=normalise_mobile(get("mobile") or get("phone")),
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
    """Invitations plus follow-up emails sent today (IST): the daily number covers both."""
    start = _today_ist_start(now or datetime.now(UTC))
    invitations = int(await session.scalar(
        select(func.count()).select_from(OutreachContact).where(OutreachContact.sent_at >= start)
    ) or 0)
    followups = int(await session.scalar(
        select(func.count()).select_from(OutreachFollowUp).where(
            OutreachFollowUp.sent_at >= start, OutreachFollowUp.channel == "email")
    ) or 0)
    return invitations + followups


async def court_context(session: AsyncSession, court: str | None) -> dict:
    """How many invitees from the same court have joined, and the court's official group (name, url)."""
    if not court or not court.strip():
        return {}
    joined = int(await session.scalar(
        select(func.count()).select_from(OutreachContact)
        .where(OutreachContact.court == court, OutreachContact.status == OutreachStatus.JOINED)
    ) or 0)
    out: dict = {"court": court, "colleagues": joined}
    from app.modules.groups.models import Group
    from app.modules.groups.official import court_group_slug

    slug = court_group_slug(court)
    if slug:
        group = await session.scalar(select(Group).where(Group.slug == slug, Group.deleted_at.is_(None)))
        if group is not None:
            out["group_name"] = group.name
            out["group_url"] = f"{settings.PUBLIC_APP_URL.rstrip('/')}/app/groups/{group.id}"
    return out


def message_for(contact: OutreachContact, **context) -> OutreachMessage:
    subject, text, html = invitation.build(name=contact.name, source=contact.source, token=contact.token, **context)
    return OutreachMessage(
        to=contact.email, subject=subject, text=text, html=html,
        one_click_url=invitation.one_click_url(contact.token),
        unsubscribe_page=invitation.unsubscribe_url(contact.token),
    )


async def budget_today(session: AsyncSession, now: datetime | None = None) -> int:
    """How many more invitations may go out today: the daily number minus those sent (IST)."""
    cfg = await get_settings(session)
    return max(0, min(cfg.daily_limit, settings.OUTREACH_DAILY_LIMIT) - await sent_today(session, now))


RANDOM = "Random"  # the focus that means "every court, picked at random" (owner, 11 Nov 2026)


def is_random(focus: str | None) -> bool:
    return bool(focus) and focus.strip().lower() == RANDOM.lower()


def focus_clause(focus: str | None):
    """The contacts a focus covers: city or court containing the text (case-insensitive)."""
    needle = f"%{focus.strip()}%"
    return OutreachContact.city.ilike(needle) | OutreachContact.court.ilike(needle)


def focus_terms(focus: str | None) -> list[str]:
    """A focus may be a list, "Allahabad, Madhya Pradesh": courts are worked in that order."""
    return [t.strip() for t in (focus or "").split(",") if t.strip()]


def focus_where(focus: str | None) -> list:
    """The WHERE clauses a focus adds: none when it is empty or `Random`."""
    return [focus_clause(focus)] if focus and focus.strip() and not is_random(focus) else []


async def active_focus(session: AsyncSession, focus: str | None) -> str | None:
    """Of a focus list, the first term with contacts still waiting (the last term when all are
    exhausted, so the screen shows 0 waiting there). A single focus or `Random` is returned as is."""
    terms = focus_terms(focus)
    if len(terms) <= 1 or is_random(focus):
        return focus
    for term in terms:
        if await queued_count(session, focus=term):
            return term
    return terms[-1]


def pick_order(focus: str | None) -> tuple:
    """Who goes first: at random across the queue under `Random`, else the oldest rows (court by court)."""
    return (func.random(),) if is_random(focus) else (OutreachContact.created_at, OutreachContact.id)


async def queued_count(session: AsyncSession, *, focus: str | None = None) -> int:
    where = [OutreachContact.status == OutreachStatus.QUEUED, OutreachContact.deleted_at.is_(None), *focus_where(focus)]
    return int(await session.scalar(select(func.count()).select_from(OutreachContact).where(*where)) or 0)


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
    # Court by court: only the bar in focus (the first of a list with anyone waiting); `Random`: anyone, in random order.
    focus = await active_focus(session, cfg.focus)
    where = [OutreachContact.status == OutreachStatus.QUEUED, OutreachContact.deleted_at.is_(None), *focus_where(focus)]
    while (budget := await budget_today(session, now)) > 0:
        contact = await session.scalar(
            select(OutreachContact).where(*where)
            .order_by(*pick_order(focus)).limit(1).with_for_update(skip_locked=True)
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
                await sender.send(message_for(contact, **await court_context(session, contact.court)))
            except RecipientRefused as exc:
                contact.status, contact.last_error = OutreachStatus.BOUNCED, str(exc)[:500]
                await _suppress(session, contact.email, "bounced")
                report["bounced"] += 1
            except Exception as exc:
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


async def list_contacts(
    session: AsyncSession, *, q: str | None = None, status: OutreachStatus | None = None,
    limit: int = 50, offset: int = 0,
) -> tuple[list[OutreachContact], int]:
    """The admin's contacts list: newest activity first (sent/unsubscribed/flagged), then the queue.

    `q` matches email, name or mobile (case-insensitive, anywhere in the value)."""
    where = [OutreachContact.deleted_at.is_(None)]
    if status is not None:
        where.append(OutreachContact.status == status)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        where.append(OutreachContact.email.ilike(needle) | OutreachContact.name.ilike(needle) | OutreachContact.mobile.ilike(needle))
    total = int(await session.scalar(select(func.count()).select_from(OutreachContact).where(*where)) or 0)
    rows = (await session.scalars(
        select(OutreachContact).where(*where)
        .order_by(OutreachContact.updated_at.desc(), OutreachContact.created_at)
        .limit(limit).offset(offset)
    )).all()
    return list(rows), total


async def request_removal(session: AsyncSession, contact_id: uuid.UUID, note: str | None) -> OutreachContact | None:
    """Flag a contact who asked to be taken off; suppressed like an unsubscribe, so never emailed."""
    contact = await session.get(OutreachContact, contact_id)
    if contact is None or contact.deleted_at is not None:
        return None
    if contact.status != OutreachStatus.REMOVAL_REQUESTED:
        contact.status = OutreachStatus.REMOVAL_REQUESTED
        contact.removal_requested_at = datetime.now(UTC)
    if note and note.strip():
        contact.removal_note = note.strip()[:300]
    await _suppress(session, contact.email, "requested")
    await session.flush()
    await session.refresh(contact)  # server-side updated_at is read by the response schema
    log.info("outreach_removal_requested")
    return contact


async def erase_contact(session: AsyncSession, contact_id: uuid.UUID) -> bool:
    """Delete the contact's row (name, address, mobile, source) for good; the
    peppered suppression hash stays, so the address can never come back."""
    contact = await session.get(OutreachContact, contact_id)
    if contact is None:
        return False
    await _suppress(session, contact.email, "erased")
    await session.delete(contact)
    await session.flush()
    log.info("outreach_contact_erased")
    return True


async def mark_joined(session: AsyncSession, email: str | None, user_id: uuid.UUID) -> OutreachContact | None:
    """Called at sign-up: an invited (or queued) address became a member. Returns the contact, so the
    new profile can start from what the public list said (city, court)."""
    if not email:
        return None
    contact = await session.scalar(select(OutreachContact).where(OutreachContact.email == email.lower()))
    if contact is not None and contact.status in (OutreachStatus.QUEUED, OutreachStatus.SENT):
        contact.status, contact.joined_user_id = OutreachStatus.JOINED, user_id
    return contact


async def mark_joined_by_token(session: AsyncSession, token: str | None, user_id: uuid.UUID) -> OutreachContact | None:
    """Sign-up that came through the email's join link (`?invite=<token>`), possibly with another
    address than the one invited: the invitation still counts as the reason they joined."""
    if not token or len(token) > 64:
        return None
    contact = await session.scalar(select(OutreachContact).where(OutreachContact.token == token))
    if contact is not None and contact.status in (OutreachStatus.QUEUED, OutreachStatus.SENT):
        contact.status, contact.joined_user_id = OutreachStatus.JOINED, user_id
        if contact.clicked_at is None:
            contact.clicked_at = datetime.now(UTC)
    return contact


# ─── Engagement: our own click link and tracking image, and the relay's webhook ──────
async def _by_token(session: AsyncSession, token: str) -> OutreachContact | None:
    if not token or len(token) > 64:
        return None
    return await session.scalar(select(OutreachContact).where(OutreachContact.token == token))


async def contact_for_invite(session: AsyncSession, token: str) -> OutreachContact | None:
    """The invitee a join link belongs to, while the invitation is still open (sent, not unsubscribed or joined)."""
    contact = await _by_token(session, token)
    if contact is None or contact.status not in (OutreachStatus.SENT,) or contact.deleted_at is not None:
        return None
    return contact


async def record_click(session: AsyncSession, token: str, now: datetime | None = None) -> OutreachContact | None:
    """The join link in the email was followed. First time only; a click is also an open."""
    contact = await _by_token(session, token)
    if contact is not None:
        now = now or datetime.now(UTC)
        contact.clicked_at = contact.clicked_at or now
        contact.opened_at = contact.opened_at or now
        await session.flush()
    return contact


async def record_open(session: AsyncSession, token: str, now: datetime | None = None) -> bool:
    """The tracking image was fetched (mail apps that load images; Gmail and Apple fetch it for everyone,
    so this overstates reading). First time only."""
    contact = await _by_token(session, token)
    if contact is None:
        return False
    if contact.opened_at is None:
        contact.opened_at = now or datetime.now(UTC)
        await session.flush()
    return True


# Brevo transactional webhook event names → what we record.
_EVENT_DELIVERED = {"delivered"}
_EVENT_OPENED = {"opened", "unique_opened", "proxy_open", "loaded_by_proxy"}
_EVENT_CLICKED = {"click"}
_EVENT_HARD_BOUNCE = {"hard_bounce", "invalid_email", "blocked"}
_EVENT_SOFT = {"soft_bounce", "deferred", "error"}
_EVENT_COMPLAINT = {"spam", "complaint"}
_EVENT_UNSUBSCRIBED = {"unsubscribed", "unsubscribe"}


async def apply_provider_event(session: AsyncSession, event: dict, now: datetime | None = None) -> str:
    """Record one relay event (`{"event": "delivered", "email": "…", "reason": "…", …}`) against the
    contact with that address. Returns what was done ("delivered", "opened", "clicked", "bounced",
    "soft_bounce", "complained", "unsubscribed", "ignored", "unknown").

    Hard bounces and complaints suppress the address like an unsubscribe. Events for addresses
    we never invited (sign-up mail goes through another relay account) are ignored."""
    kind = str(event.get("event") or "").strip().lower()
    email = _normalise(str(event.get("email") or "")) if event.get("email") else None
    if not kind or not email:
        return "ignored"
    contact = await session.scalar(select(OutreachContact).where(OutreachContact.email == email))
    if contact is None or contact.sent_at is None:
        return "unknown"
    now = now or datetime.now(UTC)
    reason = str(event.get("reason") or event.get("error") or kind)[:500]
    if kind in _EVENT_DELIVERED:
        contact.delivered_at = contact.delivered_at or now
        result = "delivered"
    elif kind in _EVENT_OPENED:
        contact.opened_at = contact.opened_at or now
        result = "opened"
    elif kind in _EVENT_CLICKED:
        contact.clicked_at = contact.clicked_at or now
        contact.opened_at = contact.opened_at or now
        result = "clicked"
    elif kind in _EVENT_HARD_BOUNCE:
        if contact.status in (OutreachStatus.SENT, OutreachStatus.QUEUED):
            contact.status = OutreachStatus.BOUNCED
        contact.last_error = reason
        await _suppress(session, contact.email, "bounced")
        result = "bounced"
    elif kind in _EVENT_SOFT:
        contact.last_error = reason
        result = "soft_bounce"
    elif kind in _EVENT_COMPLAINT:
        contact.complained_at = contact.complained_at or now
        if contact.status in (OutreachStatus.SENT, OutreachStatus.QUEUED):
            contact.status, contact.unsubscribed_at = OutreachStatus.UNSUBSCRIBED, contact.unsubscribed_at or now
        await _suppress(session, contact.email, "complaint")
        result = "complained"
    elif kind in _EVENT_UNSUBSCRIBED:
        if contact.status in (OutreachStatus.SENT, OutreachStatus.QUEUED):
            contact.status, contact.unsubscribed_at = OutreachStatus.UNSUBSCRIBED, now
        await _suppress(session, contact.email, "unsubscribed")
        result = "unsubscribed"
    else:
        return "ignored"
    await session.flush()
    log.info("outreach_provider_event", kind=kind, result=result)
    return result


def _ist_day(moment: datetime) -> str:
    if moment.tzinfo is None:  # SQLite hands back naive UTC
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(IST).date().isoformat()


async def funnel(session: AsyncSession, *, days: int = 14, courts: int = 8) -> dict:
    """Sent → delivered → opened → clicked → joined, in total, for each of the last `days` sending days
    (by the day the email went out, so a day's figures grow as its recipients read it), and by court."""
    C = OutreachContact
    invited = [C.sent_at.isnot(None), C.deleted_at.is_(None)]
    joined = C.status == OutreachStatus.JOINED

    def n(cond):
        return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)

    totals = (await session.execute(select(
        func.count(), n(C.delivered_at.isnot(None)), n(C.opened_at.isnot(None)), n(C.clicked_at.isnot(None)),
        n(joined), n(joined & C.clicked_at.isnot(None)), n(C.status == OutreachStatus.BOUNCED),
        n(C.complained_at.isnot(None)), n(C.status == OutreachStatus.UNSUBSCRIBED),
    ).where(*invited))).one()
    keys = ("sent", "delivered", "opened", "clicked", "joined", "joined_via_email", "bounced", "complained", "unsubscribed")
    total = {k: int(v or 0) for k, v in zip(keys, totals, strict=True)}

    since = _today_ist_start(datetime.now(UTC)) - timedelta(days=days - 1)
    rows = (await session.execute(
        select(C.sent_at, C.delivered_at, C.opened_at, C.clicked_at, C.status).where(*invited, C.sent_at >= since)
    )).all()
    by_day: dict[str, dict[str, int]] = {}
    for sent_at, delivered_at, opened_at, clicked_at, status in rows:
        d = by_day.setdefault(_ist_day(sent_at), {"sent": 0, "delivered": 0, "opened": 0, "clicked": 0, "joined": 0})
        d["sent"] += 1
        d["delivered"] += delivered_at is not None
        d["opened"] += opened_at is not None
        d["clicked"] += clicked_at is not None
        d["joined"] += status == OutreachStatus.JOINED
    days_out = [{"day": day, **d} for day, d in sorted(by_day.items(), reverse=True)]

    court_rows = (await session.execute(select(
        C.court, func.count(), n(C.delivered_at.isnot(None)), n(C.opened_at.isnot(None)), n(C.clicked_at.isnot(None)), n(joined),
    ).where(*invited, C.court.isnot(None)).group_by(C.court).order_by(func.count().desc()).limit(courts))).all()
    by_court = [{"court": r[0], "sent": int(r[1]), "delivered": int(r[2] or 0), "opened": int(r[3] or 0),
                 "clicked": int(r[4] or 0), "joined": int(r[5] or 0)} for r in court_rows]
    return {"total": total, "by_day": days_out, "by_court": by_court}


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
        "focus": cfg.focus,
        "queued_in_focus": await queued_count(session, focus=await active_focus(session, cfg.focus)) if cfg.focus else None,
        "active_focus": await active_focus(session, cfg.focus) if cfg.focus else None,
        "max_daily_limit": settings.OUTREACH_DAILY_LIMIT,
        "sender_configured": bool(settings.OUTREACH_SMTP_HOST),
        "webhook_configured": bool(settings.OUTREACH_WEBHOOK_SECRET),
        "from_address": settings.OUTREACH_FROM,
        "funnel": await funnel(session),
        "sent_today": await sent_today(session),
        "sent_last_7_days": int(await session.scalar(
            select(func.count()).select_from(OutreachContact).where(OutreachContact.sent_at >= week_ago)) or 0),
        "counts": {s.value: int(counts.get(s.value, counts.get(s, 0))) for s in OutreachStatus},
        "suppressed_total": int(await session.scalar(select(func.count()).select_from(OutreachSuppression)) or 0),
        "recent": [
            {"email": c.email, "name": c.name, "mobile": c.mobile, "status": c.status, "source": c.source,
             "sent_at": c.sent_at, "updated_at": c.updated_at}
            for c in recent
        ],
    }


# ── Follow-ups (22 November 2026) ───────────────────────────────────────
REMINDER_AFTER = timedelta(days=7)
REMINDER_SHARE = 3  # at most a third of the daily number goes to reminders, so new invitations never stall


async def reminder_candidates(session: AsyncSession, now: datetime, limit: int) -> list[OutreachContact]:
    """Invited a week or more ago, opened the email, never clicked, still not a member, no reminder yet."""
    reminded = select(OutreachFollowUp.contact_id).where(OutreachFollowUp.kind == "reminder")
    return list(await session.scalars(
        select(OutreachContact).where(
            OutreachContact.status == OutreachStatus.SENT, OutreachContact.deleted_at.is_(None),
            OutreachContact.sent_at <= now - REMINDER_AFTER,
            OutreachContact.opened_at.is_not(None), OutreachContact.clicked_at.is_(None),
            OutreachContact.id.not_in(reminded),
        ).order_by(OutreachContact.opened_at).limit(limit)
    ))


async def send_reminders(
    session: AsyncSession, sender: OutreachSender, *, now: datetime | None = None, pause=None,
) -> dict[str, int]:
    """The one reminder per invitee, within today's number and at most a third of it (sent before the
    day's new invitations: an opened invitation is warmer than a cold one). Suppressed addresses and
    members are skipped."""
    report = {"sent": 0, "skipped": 0, "bounced": 0, "failed": 0}
    now = now or datetime.now(UTC)
    cfg = await get_settings(session)
    budget = min(await budget_today(session, now), max(1, min(cfg.daily_limit, settings.OUTREACH_DAILY_LIMIT) // REMINDER_SHARE))
    if budget <= 0:
        return report
    for contact in await reminder_candidates(session, now, budget):
        if await _suppressed(session, contact.email):
            report["skipped"] += 1
            continue
        if member := await _member_id(session, contact.email):
            contact.status, contact.joined_user_id = OutreachStatus.JOINED, member
            report["skipped"] += 1
            await session.commit()
            continue
        subject, text, html = invitation.build_reminder(
            name=contact.name, source=contact.source, token=contact.token, **await court_context(session, contact.court))
        row = OutreachFollowUp(contact_id=contact.id, channel="email", kind="reminder", subject=subject, body=text, sent_at=now)
        session.add(row)
        await session.flush()  # claimed before sending, so a crash never reminds twice
        try:
            await sender.send(OutreachMessage(to=contact.email, subject=subject, text=text, html=html,
                                              one_click_url=invitation.one_click_url(contact.token),
                                              unsubscribe_page=invitation.unsubscribe_url(contact.token)))
        except RecipientRefused as exc:
            contact.status, contact.last_error = OutreachStatus.BOUNCED, str(exc)[:500]
            await _suppress(session, contact.email, "bounced")
            report["bounced"] += 1
        except Exception as exc:
            await session.rollback()
            log.warning("outreach_reminder_failed", error=type(exc).__name__)
            report["failed"] += 1
            break
        else:
            report["sent"] += 1
        await session.commit()
        if pause and report["sent"]:
            await pause()
    log.info("outreach_reminders", **report)
    return report


async def warm_leads(session: AsyncSession, *, limit: int = 200) -> dict[str, list[dict]]:
    """Two lists for the admin: invitees who clicked the join link but have not joined, and invitees who
    joined. Each with the follow-ups already sent and a number for a wa.me link when one is known
    (the contact's listed mobile, or the member's verified phone)."""
    def row(c: OutreachContact, phone: str | None, followups: list[OutreachFollowUp]) -> dict:
        return {"id": c.id, "name": c.name, "email": c.email, "court": c.court, "city": c.city, "status": c.status,
                "clicked_at": c.clicked_at, "joined_at": c.updated_at if c.status == OutreachStatus.JOINED else None,
                "phone": phone, "followups": [{"channel": f.channel, "kind": f.kind, "sent_at": f.sent_at} for f in followups]}
    leads = list(await session.scalars(
        select(OutreachContact).where(OutreachContact.status == OutreachStatus.SENT, OutreachContact.clicked_at.is_not(None),
                                      OutreachContact.deleted_at.is_(None)).order_by(OutreachContact.clicked_at.desc()).limit(limit)))
    joined = list(await session.scalars(
        select(OutreachContact).where(OutreachContact.status == OutreachStatus.JOINED, OutreachContact.deleted_at.is_(None))
        .order_by(OutreachContact.updated_at.desc()).limit(limit)))
    ids = [c.id for c in leads + joined]
    fus: dict[uuid.UUID, list[OutreachFollowUp]] = {}
    if ids:
        for f in await session.scalars(select(OutreachFollowUp).where(OutreachFollowUp.contact_id.in_(ids)).order_by(OutreachFollowUp.sent_at)):
            fus.setdefault(f.contact_id, []).append(f)
    phones: dict[uuid.UUID, str] = {}
    user_ids = [c.joined_user_id for c in joined if c.joined_user_id]
    if user_ids:
        for uid, phone, verified in await session.execute(select(User.id, User.phone, User.is_phone_verified).where(User.id.in_(user_ids))):
            if phone and verified:
                phones[uid] = phone
    return {"leads": [row(c, c.mobile, fus.get(c.id, [])) for c in leads],
            "joined": [row(c, phones.get(c.joined_user_id) or c.mobile, fus.get(c.id, [])) for c in joined]}


def whatsapp_link(phone: str, text: str) -> str:
    from urllib.parse import quote
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        digits = "91" + digits
    return f"https://wa.me/{digits}?text={quote(text, safe='')}"


async def personal_followup(
    session: AsyncSession, sender: OutreachSender | None, contact_id: uuid.UUID, *, channel: str, note: str, by: uuid.UUID,
) -> dict:
    """The admin's personal note. Email: sent through the invitation mail service and recorded.
    WhatsApp: recorded, and a wa.me link is returned for the admin to send from their own phone
    (non-members are never messaged by the platform's WhatsApp number)."""
    contact = await session.get(OutreachContact, contact_id)
    if contact is None or contact.deleted_at is not None:
        raise LookupError("No such contact.")
    if contact.status not in (OutreachStatus.SENT, OutreachStatus.JOINED):
        raise ValueError("Only invitees who were approached or who joined can be written to.")
    note = note.strip()
    if not note:
        raise ValueError("The note is empty.")
    joined = contact.status == OutreachStatus.JOINED
    now = datetime.now(UTC)
    if channel == "email":
        if sender is None:
            raise ValueError("The invitation mail service is not set up (VS_OUTREACH_SMTP_HOST).")
        if await _suppressed(session, contact.email):
            raise ValueError("This address unsubscribed or bounced; it cannot be emailed.")
        subject, text, html = invitation.build_personal(name=contact.name, source=contact.source, token=contact.token, note=note, joined=joined)
        await sender.send(OutreachMessage(to=contact.email, subject=subject, text=text, html=html,
                                          one_click_url=invitation.one_click_url(contact.token),
                                          unsubscribe_page=invitation.unsubscribe_url(contact.token)))
        session.add(OutreachFollowUp(contact_id=contact.id, channel="email", kind="personal", subject=subject, body=note, sent_by=by, sent_at=now))
        await session.flush()
        return {"sent": True, "channel": "email"}
    if channel == "whatsapp":
        phone = contact.mobile
        if joined and contact.joined_user_id:
            user = await session.get(User, contact.joined_user_id)
            if user and user.phone and user.is_phone_verified:
                phone = user.phone
        if not phone:
            raise ValueError("No mobile number is known for this person.")
        session.add(OutreachFollowUp(contact_id=contact.id, channel="whatsapp", kind="personal", body=note, sent_by=by, sent_at=now))
        await session.flush()
        return {"sent": False, "channel": "whatsapp", "whatsapp_url": whatsapp_link(phone, note)}
    raise ValueError("channel must be email or whatsapp")
