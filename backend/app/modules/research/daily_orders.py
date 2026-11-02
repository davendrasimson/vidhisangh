"""Daily intake → offline headnote writing/import → opted-in daily email."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import uuid
from datetime import UTC, date, datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.channels import ChannelMessage, ChannelProvider
from app.core.config import settings
from app.modules.identity.models import User
from app.modules.notifications.models import NotificationChannel, NotificationPreference
from app.modules.research.ai_headnotes import FORMAT_VERSION
from app.modules.research.daily_models import DailyOrder, DailyOrderEmail, DailyOrderSubscription
from app.modules.research.daily_source import OrderEntry, SupremeCourtSource, extract_document
from app.modules.research.models import CourtLevel, Judgment
from app.modules.research.public_pages import judgment_path
from app.modules.research.schemas import AI_HEADNOTE_LABEL, AiHeadnoteContent

IST = ZoneInfo("Asia/Kolkata")
SYSTEM_ACTOR = uuid.UUID(int=0)
EMAIL_LIMIT = 25


async def subscription(session: AsyncSession, user_id: uuid.UUID) -> DailyOrderSubscription | None:
    return await session.scalar(
        select(DailyOrderSubscription).where(DailyOrderSubscription.user_id == user_id)
    )


async def subscribe(
    session: AsyncSession, user_id: uuid.UUID, enabled: bool
) -> DailyOrderSubscription:
    user = await session.get(User, user_id)
    if enabled and (
        not user
        or user.deleted_at
        or not user.is_active
        or not user.email
        or not user.is_email_verified
    ):
        raise ValueError("Verify your account email before subscribing")
    row = await subscription(session, user_id)
    if row is None:
        row = DailyOrderSubscription(
            user_id=user_id,
            enabled=enabled,
            subscribed_at=datetime.now(UTC),
            token=secrets.token_urlsafe(32),
        )
        session.add(row)
    elif row.enabled != enabled:
        row.enabled = enabled
        if enabled:
            row.subscribed_at, row.token = datetime.now(UTC), secrets.token_urlsafe(32)
    await session.flush()
    return row


async def unsubscribe(session: AsyncSession, token: str) -> None:
    if len(token) > 64:
        return
    row = await session.scalar(
        select(DailyOrderSubscription).where(DailyOrderSubscription.token == token)
    )
    if row:
        row.enabled = False
        await session.flush()


async def register_entries(session: AsyncSession, entries: list[OrderEntry], now: datetime) -> int:
    added = 0
    for entry in entries:
        if entry.day > now.astimezone(IST).date():
            continue
        ref = "sc-daily:" + hashlib.sha256(entry.url.encode()).hexdigest()
        record = await session.scalar(select(DailyOrder).where(DailyOrder.source_url == entry.url))
        if record:
            continue
        judgment = await session.scalar(select(Judgment).where(Judgment.source_ref == ref))
        if judgment is None:
            # Avoid duplicating a previously ingested order with the same official URL.
            judgment = await session.scalar(select(Judgment).where(Judgment.url == entry.url))
        if judgment and (judgment.deleted_at or judgment.court_level != CourtLevel.SUPREME_COURT):
            continue
        try:
            async with session.begin_nested():
                if judgment is None:
                    judgment = Judgment(
                        case_name=entry.title,
                        cause_title=entry.title,
                        judgment_date=entry.day,
                        court="Supreme Court of India",
                        court_level=CourtLevel.SUPREME_COURT,
                        source_ref=ref,
                        url=entry.url,
                        added_by=SYSTEM_ACTOR,
                    )
                    session.add(judgment)
                    await session.flush()
                session.add(
                    DailyOrder(
                        judgment_id=judgment.id,
                        source_url=entry.url,
                        first_seen_at=now,
                        status="ready"
                        if judgment.ai_headnote
                        else "pending_headnote"
                        if judgment.full_text
                        else "pending_text",
                    )
                )
                await session.flush()
            added += 1
        except IntegrityError:
            # Another intake won the same source/judgment unique key.
            continue
    await session.commit()
    return added


async def prepare_headnotes(
    session: AsyncSession,
    source: SupremeCourtSource,
    *,
    limit: int = 100,
) -> dict[str, int]:
    report = {"ready": 0, "pending_headnotes": 0, "needs_review": 0, "retrieval_failed": 0}
    ids = list(
        await session.scalars(
            select(DailyOrder.id)
            .where(
                DailyOrder.deleted_at.is_(None),
                DailyOrder.status.in_(["pending_text", "pending_headnote"]),
            )
            .order_by(DailyOrder.status.desc(), DailyOrder.first_seen_at, DailyOrder.id)
            .limit(limit)
        )
    )
    for record_id in ids:
        record = await session.get(DailyOrder, record_id)
        judgment = await session.get(Judgment, record.judgment_id)
        if judgment is None or judgment.deleted_at:
            continue
        if not judgment.full_text:
            try:
                _, pdf = await source.document(record.source_url)
                record.source_sha256 = hashlib.sha256(pdf).hexdigest()
                judgment.full_text = await extract_document(pdf)
                judgment.text_extracted_at = datetime.now(UTC)
            except ValueError:
                record.status, record.error = "needs_review", "PDF/text requires manual review"
                report["needs_review"] += 1
                await session.commit()
                continue
            except Exception:
                record.error = "Official retrieval failed; will retry"
                report["retrieval_failed"] += 1
                await session.commit()
                continue
        record.status = "ready" if judgment.ai_headnote else "pending_headnote"
        record.error = None
        report["ready" if judgment.ai_headnote else "pending_headnotes"] += 1
        await session.commit()
    return report


async def export_pending(session: AsyncSession, out: Path) -> int:
    """Daily intake only, in the existing no-paid-API writer/import format.

    Complete extracted source is exported, never excerpts. queue.json is the
    authoritative current manifest; prior files stay for provenance.
    """
    rows = (
        await session.execute(
            select(DailyOrder, Judgment)
            .join(
                Judgment,
                Judgment.id == DailyOrder.judgment_id,
            )
            .where(
                DailyOrder.deleted_at.is_(None),
                Judgment.deleted_at.is_(None),
                Judgment.ai_headnote.is_(None),
                Judgment.full_text.is_not(None),
            )
            .order_by(DailyOrder.first_seen_at, Judgment.id)
        )
    ).all()
    queue = []
    files = []
    for record, judgment in rows:
        header = (
            f"JUDGMENT ID: {judgment.id}\nCASE: {judgment.case_name}\n"
            f"DATE: {judgment.judgment_date}\nOFFICIAL SOURCE: {record.source_url}\n"
            f"PDF SHA256: {record.source_sha256 or 'not recorded'}\n" + "=" * 72 + "\n"
        )
        content = header + judgment.full_text + "\n"
        files.append((f"{judgment.id}.txt", content))
        queue.append(
            {
                "id": str(judgment.id),
                "date": str(judgment.judgment_date),
                "chars": len(judgment.full_text),
                "source_url": record.source_url,
                "export_sha256": hashlib.sha256(content.encode()).hexdigest(),
            }
        )
    await asyncio.to_thread(_write_exports, out, files, queue)
    return len(queue)


def _write_exports(out: Path, files: list[tuple[str, str]], queue: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, content in files:
        (out / name).write_text(content, encoding="utf-8")
    temporary = out / "queue.json.tmp"
    temporary.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    temporary.replace(out / "queue.json")


def render_digest(
    user: User, sub: DailyOrderSubscription, judgments: list[Judgment], day: date
) -> ChannelMessage:
    base = settings.PUBLIC_APP_URL.rstrip("/")
    unsub = f"{base}{settings.API_V1_PREFIX}/research/daily-orders/unsubscribe/{sub.token}"
    text = [f"Supreme Court orders — {day:%d %B %Y}", AI_HEADNOTE_LABEL]
    html = [f"<h1>Supreme Court orders — {day:%d %B %Y}</h1><p>{escape(AI_HEADNOTE_LABEL)}</p>"]
    for j in judgments:
        h = AiHeadnoteContent.model_validate(j.ai_headnote)
        link = base + judgment_path(j)
        dated = j.judgment_date.isoformat() if j.judgment_date else "Date not supplied"
        text += [
            f"\n{j.case_name} ({dated})",
            h.summary,
            "Result: " + h.result,
            link,
            "Official order: " + (j.url or ""),
        ]
        html.append(
            f"<h2><a href='{escape(link, quote=True)}'>{escape(j.case_name)}</a></h2>"
            f"<p>{dated}</p><p>{escape(h.summary)}</p>"
            f"<p><strong>Result:</strong> {escape(h.result)}</p>"
            f"<p><a href='{escape(j.url or '', quote=True)}'>Official order</a></p>"
        )
        for point in h.held:
            refs = f" (paragraphs {', '.join(point.paragraphs)})" if point.paragraphs else ""
            text.append("Held: " + point.point + refs)
            html.append(f"<p><strong>Held:</strong> {escape(point.point + refs)}</p>")
    text += [
        "\nYou subscribed to Supreme Court order emails. "
        "More pending items appear in a later digest.",
        "Unsubscribe: " + unsub,
    ]
    html.append(
        "<p>You subscribed to Supreme Court order emails. "
        "More pending items appear in a later digest.</p>"
        f"<p><a href='{escape(unsub, quote=True)}'>Unsubscribe</a></p>"
    )
    return ChannelMessage(
        to_email=user.email,
        to_name=user.full_name,
        subject=f"Supreme Court: {len(judgments)} order headnotes — {day:%d %b %Y}",
        body="\n".join(text),
        html="".join(html),
        unsubscribe_url=unsub,
    )


async def send_digests(
    session: AsyncSession, sender: ChannelProvider, day: date, *, dry_run: bool = False
) -> dict[str, int]:
    report = {"sent": 0, "already": 0, "uncertain": 0, "eligible": 0}
    if not sender.configured or sender.name != "email":
        return report
    recipients = (
        await session.execute(
            select(DailyOrderSubscription.id, User.id)
            .join(
                User,
                User.id == DailyOrderSubscription.user_id,
            )
            .where(
                DailyOrderSubscription.enabled.is_(True),
                DailyOrderSubscription.deleted_at.is_(None),
                User.is_active.is_(True),
                User.is_email_verified.is_(True),
                User.email.is_not(None),
                User.deleted_at.is_(None),
            )
        )
    ).all()
    for sub_id, user_id in recipients:
        sub = await session.get(DailyOrderSubscription, sub_id)
        user = await session.get(User, user_id)
        off = await session.scalar(
            select(NotificationPreference.id).where(
                NotificationPreference.user_id == user.id,
                NotificationPreference.channel == NotificationChannel.EMAIL,
                NotificationPreference.enabled.is_(False),
                NotificationPreference.deleted_at.is_(None),
            )
        )
        if off:
            continue
        previous = (
            await session.scalars(
                select(DailyOrderEmail).where(DailyOrderEmail.subscription_id == sub.id)
            )
        ).all()
        if any(r.for_date == day for r in previous):
            report["already"] += 1
            continue
        claimed = {key for row in previous for key in row.judgment_ids}
        due = (
            await session.scalars(
                select(Judgment)
                .join(DailyOrder, DailyOrder.judgment_id == Judgment.id)
                .where(
                    DailyOrder.first_seen_at >= sub.subscribed_at,
                    DailyOrder.deleted_at.is_(None),
                    Judgment.deleted_at.is_(None),
                    Judgment.ai_headnote.is_not(None),
                    Judgment.ai_headnote_model.is_not(None),
                    Judgment.ai_headnote_generated_at.is_not(None),
                    Judgment.ai_headnote_version == FORMAT_VERSION,
                )
                .order_by(DailyOrder.first_seen_at, Judgment.id)
            )
        ).all()
        due = [j for j in due if str(j.id) not in claimed][:EMAIL_LIMIT]
        if not due:
            continue
        message = render_digest(user, sub, due, day)  # validates content before claiming
        token = sub.token
        report["eligible"] += 1
        if dry_run:
            continue
        # Refresh consent immediately before claiming; a long run must honour opt-outs.
        await session.refresh(sub)
        await session.refresh(user)
        if (
            not sub.enabled
            or sub.deleted_at
            or not user.is_active
            or not user.is_email_verified
            or user.deleted_at
        ):
            continue
        if message.to_email != user.email or token != sub.token:
            continue
        if await session.scalar(
            select(NotificationPreference.id).where(
                NotificationPreference.user_id == user.id,
                NotificationPreference.channel == NotificationChannel.EMAIL,
                NotificationPreference.enabled.is_(False),
                NotificationPreference.deleted_at.is_(None),
            )
        ):
            continue
        row = DailyOrderEmail(
            subscription_id=sub.id,
            for_date=day,
            judgment_ids=[str(j.id) for j in due],
            status="sending",
        )
        session.add(row)
        try:
            await session.commit()  # unique daily claim is durable before SMTP
        except IntegrityError:
            await session.rollback()
            report["already"] += 1
            continue
        try:
            await sender.send(message)
            row.status = "sent"
            report["sent"] += 1
        except Exception:
            # SMTP timeout can follow acceptance. Do not automatically duplicate
            # either this digest or these orders on tomorrow's run.
            row.status = "uncertain"
            report["uncertain"] += 1
        await session.commit()
    return report
