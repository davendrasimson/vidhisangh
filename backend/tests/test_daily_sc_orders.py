"""Daily orders: official-source restrictions, full-source writing and opt-in delivery."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.modules.identity.models import User
from app.modules.notifications.models import NotificationChannel, NotificationPreference
from app.modules.research import daily_orders as daily
from app.modules.research.ai_headnotes import apply_ai_headnote
from app.modules.research.daily_models import DailyOrder, DailyOrderEmail
from app.modules.research.daily_source import (
    ListingParser,
    OrderEntry,
    SupremeCourtSource,
    official_url,
)
from app.modules.research.models import Judgment
from tests.test_matters import API, _user

TEXT = "1. Leave granted. The appeal is allowed and the impugned order is set aside."
HEADNOTE = {
    "summary": "The Court allowed the appeal and set aside the impugned order.",
    "issues": ["What relief was ordered?"],
    "provisions": [],
    "held": [{"point": "The impugned order was set aside.", "paragraphs": ["1"]}],
    "result": "Appeal allowed.",
}
URL = "https://www.sci.gov.in/view-pdf/?type=o&order_date=2026-11-02&path=official"
NOW = datetime(2026, 11, 2, 15, tzinfo=UTC)


class MailRecorder:
    name = "email"
    configured = True

    def __init__(self, fail=False):
        self.messages = []
        self.fail = fail

    async def send(self, message):
        self.messages.append(message)
        if self.fail:
            raise TimeoutError("SMTP acceptance unknown")


@pytest.mark.parametrize(
    "url",
    [
        "http://www.sci.gov.in/a.pdf",
        "https://www.sci.gov.in.attacker.test/a.pdf",
        "https://user@www.sci.gov.in/a.pdf",
        "https://127.0.0.1/a.pdf",
    ],
)
def test_reject_unofficial_document_urls(url):
    with pytest.raises(ValueError):
        official_url(url)


def test_parse_official_order_and_judgment_dates_not_upload_date():
    p = ListingParser()
    p.feed(f'<a href="{URL.replace("&", "&amp;")}"><span>A v B</span> (Uploaded On 03-11-2026)</a>')
    assert len(p.entries) == 1
    assert p.entries[0].day == date(2026, 11, 2)
    assert p.entries[0].title == "A v B"
    assert official_url(URL) == official_url(
        URL.replace("type=o&order_date=2026-11-02", "order_date=2026-11-02&type=o")
    )


@pytest.mark.asyncio
async def test_empty_feed_and_changed_markup_are_different():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="No records found"))
    ) as client:
        assert await SupremeCourtSource(client).discover() == []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, text="<h1>Unexpected maintenance</h1>")
        )
    ) as client:
        with pytest.raises(ValueError, match="format changed"):
            await SupremeCourtSource(client).discover()


@pytest.mark.asyncio
async def test_redirect_host_checked_before_following():
    requests = []

    def respond(request):
        requests.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://attacker.test/private.pdf"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError):
            await SupremeCourtSource(client).download(URL)
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_wrapper_resolves_only_official_pdf():
    def respond(request):
        if request.url.path == "/view-pdf/":
            return httpx.Response(
                200, text='<iframe src="https://api.sci.gov.in/supremecourt/order.pdf"></iframe>'
            )
        return httpx.Response(200, content=b"%PDF-1.7 example")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        url, data = await SupremeCourtSource(client).document(URL)
        assert url == "https://api.sci.gov.in/supremecourt/order.pdf"
        assert data.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_intake_dedup_exports_complete_source_and_waits_for_import(session_factory, tmp_path):

    async with session_factory() as session:
        entries = [OrderEntry("A v B", NOW.date(), official_url(URL))]
        assert await daily.register_entries(session, entries, NOW) == 1
        assert await daily.register_entries(session, entries, NOW) == 0
        row = await session.scalar(select(DailyOrder))
        judgment = await session.get(Judgment, row.judgment_id)
        judgment.full_text = TEXT
        await session.commit()
        report = await daily.prepare_headnotes(session, None)
        assert report["pending_headnotes"] == 1 and judgment.ai_headnote is None
        assert await daily.export_pending(session, tmp_path) == 1
        assert TEXT in (tmp_path / f"{judgment.id}.txt").read_text()
        assert json.loads((tmp_path / "queue.json").read_text())[0]["id"] == str(judgment.id)
        await apply_ai_headnote(session, judgment.id, HEADNOTE, model="offline-reviewed")
        await session.commit()
        assert (await daily.prepare_headnotes(session, None))["ready"] == 1
        assert await daily.export_pending(session, tmp_path) == 0
        assert json.loads((tmp_path / "queue.json").read_text()) == []
        assert judgment.ai_headnote_model == "offline-reviewed"


@pytest.mark.asyncio
async def test_unreadable_pdf_stays_for_review_and_network_failure_is_retried(session_factory):
    class Source:
        async def document(self, url):
            if "official2" in url:
                raise httpx.ConnectError("temporary failure")
            raise ValueError("unreadable PDF")

    async with session_factory() as session:
        await daily.register_entries(
            session,
            [
                OrderEntry("A v B", NOW.date(), official_url(URL)),
                OrderEntry("C v D", NOW.date(), official_url(URL + "2")),
            ],
            NOW,
        )
        report = await daily.prepare_headnotes(session, Source())
        assert report["needs_review"] == 1 and report["retrieval_failed"] == 1
        assert all(j.ai_headnote is None for j in await session.scalars(select(Judgment)))


async def verified_user(client, session_factory, strong_password):
    headers, me = await _user(client, "Daily LLP", "daily@firm.co", strong_password)
    async with session_factory() as session:
        user = await session.get(User, uuid.UUID(me["id"]))
        user.is_email_verified = True
        await session.commit()
    return headers, uuid.UUID(me["id"])


@pytest.mark.asyncio
async def test_opt_in_verified_email_unsubscribe_and_tenant_isolation(
    client, session_factory, strong_password
):
    h, _me = await _user(client, "Unverified LLP", "unverified@firm.co", strong_password)
    assert (
        await client.put(f"{API}/notifications/daily-orders", headers=h, json={"enabled": True})
    ).status_code == 400
    h, uid = await verified_user(client, session_factory, strong_password)
    assert (await client.get(f"{API}/notifications/daily-orders", headers=h)).json()[
        "enabled"
    ] is False
    assert (
        await client.put(f"{API}/notifications/daily-orders", headers=h, json={"enabled": True})
    ).json()["enabled"] is True
    async with session_factory() as session:
        sub = await daily.subscription(session, uid)
        token = sub.token
    url = f"{API}/research/daily-orders/unsubscribe/{token}"
    assert (await client.get(url)).status_code == 200
    assert (await client.get(f"{API}/notifications/daily-orders", headers=h)).json()[
        "enabled"
    ] is True
    assert (await client.post(url)).status_code == 204
    assert (await client.get(f"{API}/notifications/daily-orders", headers=h)).json()[
        "enabled"
    ] is False
    assert (
        await client.get(f"{API}/notifications/daily-orders", headers={"Authorization": ""})
    ).status_code == 401
    # Re-subscribe rotates the token; old mail cannot cancel the new choice.
    await client.put(f"{API}/notifications/daily-orders", headers=h, json={"enabled": True})
    await client.post(url)
    assert (await client.get(f"{API}/notifications/daily-orders", headers=h)).json()[
        "enabled"
    ] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_email_once_pending_catchup_and_uncertain_no_retry(
    client, session_factory, strong_password, fail
):
    h, _uid = await verified_user(client, session_factory, strong_password)
    await client.put(f"{API}/notifications/daily-orders", headers=h, json={"enabled": True})
    async with session_factory() as session:
        first_seen = datetime.now(UTC) + timedelta(seconds=1)
        await daily.register_entries(
            session, [OrderEntry("<A> v B", first_seen.date(), official_url(URL))], first_seen
        )
        j = await session.scalar(select(Judgment))
        mail = MailRecorder(fail=fail)
        assert (await daily.send_digests(session, mail, NOW.date()))["sent"] == 0
        # A raw JSON assignment without import provenance is not distributable.
        j.ai_headnote = HEADNOTE
        await session.commit()
        assert (await daily.send_digests(session, mail, NOW.date()))["sent"] == 0
        j.ai_headnote = None
        await apply_ai_headnote(session, j.id, HEADNOTE, model="offline-reviewed")
        await session.commit()
        assert (await daily.send_digests(session, mail, NOW.date(), dry_run=True))["eligible"] == 1
        assert not mail.messages and not list(await session.scalars(select(DailyOrderEmail)))
        result = await daily.send_digests(session, mail, NOW.date())
        assert result["uncertain" if fail else "sent"] == 1
        assert len(mail.messages) == 1
        assert (
            "AI-generated" in mail.messages[0].body and "Official order:" in mail.messages[0].body
        )
        assert "&lt;A&gt;" in mail.messages[0].html and "<A>" not in mail.messages[0].html
        assert "/unsubscribe/" in mail.messages[0].unsubscribe_url
        assert (await daily.send_digests(session, mail, NOW.date()))["already"] == 1
        await daily.send_digests(session, mail, NOW.date() + timedelta(days=1))
        assert len(mail.messages) == 1


@pytest.mark.asyncio
async def test_email_optout_blocks_digest(client, session_factory, strong_password):
    h, uid = await verified_user(client, session_factory, strong_password)
    await client.put(f"{API}/notifications/daily-orders", headers=h, json={"enabled": True})
    async with session_factory() as session:
        await daily.register_entries(
            session,
            [OrderEntry("A v B", NOW.date(), official_url(URL))],
            datetime.now(UTC) + timedelta(seconds=1),
        )
        j = await session.scalar(select(Judgment))
        await apply_ai_headnote(session, j.id, HEADNOTE, model="offline-reviewed")
        session.add(
            NotificationPreference(
                user_id=uid, channel=NotificationChannel.EMAIL, enabled=False, types=[]
            )
        )
        await session.commit()
        mail = MailRecorder()
        await daily.send_digests(session, mail, NOW.date())
        assert not mail.messages


@pytest.mark.asyncio
async def test_job_preview_and_offline_export_do_not_send_mail(
    session_factory, engine, tmp_path, monkeypatch
):
    from contextlib import asynccontextmanager

    from app.core.config import settings
    from app.scripts import daily_sc_orders as job

    class Source:
        def __init__(self, client):
            pass

        async def discover(self):
            return [OrderEntry("A v B", date.today(), official_url(URL))]

        async def document(self, url):
            return url, b"%PDF-complete-source"

    @asynccontextmanager
    async def sessions(**kwargs):
        async with session_factory() as session:
            yield session
            await session.commit()

    async def extract(pdf):
        return TEXT

    monkeypatch.setattr(job, "get_engine", lambda: engine)
    monkeypatch.setattr(job, "session_scope", sessions)
    monkeypatch.setattr(job, "SupremeCourtSource", Source)
    monkeypatch.setattr(daily, "extract_document", extract)
    monkeypatch.setattr(settings, "SC_DAILY_ENABLED", True)
    mail = MailRecorder()
    monkeypatch.setattr(job, "EmailSmtpProvider", lambda: mail)
    preview = await job.run()
    assert preview["database_writes"] == preview["emails_sent"] == 0
    async with session_factory() as session:
        assert not list(await session.scalars(select(DailyOrder)))
    result = await job.run(execute=True, send=True, export_dir=tmp_path)
    assert result["exported_for_writing"] == 1 and result["pending_headnotes"] == 1
    assert not mail.messages
    with pytest.raises(ValueError, match="requires --execute"):
        await job.run(send=True)


@pytest.mark.asyncio
async def test_digest_limit_carries_remaining_orders_to_next_day(
    client, session_factory, strong_password
):
    h, _uid = await verified_user(client, session_factory, strong_password)
    await client.put(f"{API}/notifications/daily-orders", headers=h, json={"enabled": True})
    async with session_factory() as session:
        first_seen = datetime.now(UTC) + timedelta(seconds=1)
        entries = [
            OrderEntry(f"Order {i}", first_seen.date(), official_url(URL + str(i)))
            for i in range(27)
        ]
        await daily.register_entries(session, entries, first_seen)
        for judgment in await session.scalars(select(Judgment)):
            await apply_ai_headnote(session, judgment.id, HEADNOTE, model="offline-reviewed")
        await session.commit()
        mail = MailRecorder()
        await daily.send_digests(session, mail, first_seen.date())
        await daily.send_digests(session, mail, first_seen.date() + timedelta(days=1))
        rows = list(
            await session.scalars(select(DailyOrderEmail).order_by(DailyOrderEmail.for_date))
        )
        assert [len(row.judgment_ids) for row in rows] == [25, 2]
        assert set(rows[0].judgment_ids).isdisjoint(rows[1].judgment_ids)
        assert len(mail.messages) == 2


def test_smtp_digest_has_plain_html_and_one_click_headers(monkeypatch):
    from app.core.channels import ChannelMessage, EmailSmtpProvider
    from app.core.config import settings

    captured = []

    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def starttls(self, **kwargs):
            pass

        def send_message(self, message):
            captured.append(message)

        def quit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_SSL", False)
    monkeypatch.setattr("app.core.channels.smtplib.SMTP", SMTP)
    EmailSmtpProvider()._send(
        ChannelMessage(
            to_email="reader@example.com",
            to_name="Reader",
            subject="Daily orders",
            body="Plain headnote",
            html="<p>Headnote</p>",
            unsubscribe_url="https://vidhisangh.com/api/v1/research/daily-orders/unsubscribe/test",
        )
    )
    (message,) = captured
    assert message["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "/unsubscribe/test" in message["List-Unsubscribe"]
    assert message.get_body(preferencelist=("plain",)).get_content().strip() == "Plain headnote"
    assert message.get_body(preferencelist=("html",)).get_content().strip() == "<p>Headnote</p>"
