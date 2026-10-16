"""Invitation emails: import, daily limit, one-click unsubscribe, suppression, conversions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.outreach_mail import OutreachMessage, RecipientRefused, set_outreach_sender
from app.modules.identity.models import User
from app.modules.outreach import service
from app.modules.outreach.models import OutreachContact, OutreachStatus

pytestmark = pytest.mark.asyncio


class Recorder:
    def __init__(self, refuse: set[str] | None = None) -> None:
        self.sent: list[OutreachMessage] = []
        self.refuse = refuse or set()

    async def send(self, message: OutreachMessage) -> None:
        if message.to in self.refuse:
            raise RecipientRefused("550 no such user")
        self.sent.append(message)


@pytest.fixture(autouse=True)
def _no_real_mail():
    yield
    set_outreach_sender(None, active=False)


async def _admin(client: AsyncClient, session_factory, pw: str) -> dict:
    r = await client.post("/api/v1/auth/register", json={
        "organisation_name": "Ops", "full_name": "Ops Admin", "email": "ops@vidhisangh.co", "password": pw, "accept_terms": True})
    assert r.status_code == 201
    async with session_factory() as s:
        (await s.scalar(select(User).where(User.email == "ops@vidhisangh.co"))).is_superuser = True
        await s.commit()
    login = await client.post("/api/v1/auth/login", json={"email": "ops@vidhisangh.co", "password": pw})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


CSV = (
    "Email,Name,City,Court,Source\n"
    "priya@lawchambers.in,Adv. Priya Sharma,Delhi,Delhi High Court,\n"
    "PRIYA@lawchambers.in,dup,,,\n"
    "ravi@advocates.in,Adv. Ravi Kumar,Chandigarh,P&H High Court,Punjab & Haryana Bar directory\n"
    "not-an-email,x,,,\n"
    "ops@vidhisangh.co,Already a member,,,\n"
    "meera@firm.in,Meera Nair,,,\n"
)


async def test_import_send_unsubscribe_and_join(client: AsyncClient, session_factory, strong_password) -> None:
    admin = await _admin(client, session_factory, strong_password)
    member_headers = {"Authorization": admin["Authorization"]}

    # Only platform admins.
    r = await client.post("/api/v1/auth/register", json={
        "organisation_name": "Plain Co", "full_name": "Plain User", "email": "plain@x.co", "password": strong_password, "accept_terms": True})
    plain = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get("/api/v1/platform-admin/outreach", headers=plain)).status_code == 403

    imported = await client.post("/api/v1/platform-admin/outreach/contacts", headers=member_headers,
                                 files={"file": ("list.csv", CSV.encode(), "text/csv")},
                                 data={"source": "the Delhi High Court Bar Association directory"})
    assert imported.status_code == 200, imported.text
    assert imported.json() == {"added": 3, "duplicate": 1, "member": 1, "unsubscribed": 0, "invalid": 1, "no_source": 0}

    overview = (await client.get("/api/v1/platform-admin/outreach", headers=member_headers)).json()
    assert overview["paused"] is True and overview["counts"]["queued"] == 3

    recorder = Recorder(refuse={"meera@firm.in"})
    async with session_factory() as s:
        assert (await service.send_batch(s, recorder))["sent"] == 0  # starts paused
        await service.update_settings(s, paused=False, daily_limit=2)
        await s.commit()
        report = await service.send_batch(s, recorder)
    assert report == {"sent": 2, "skipped": 0, "bounced": 0, "failed": 0}
    assert [m.to for m in recorder.sent] == ["priya@lawchambers.in", "ravi@advocates.in"]
    msg = recorder.sent[0]
    assert "Dear Adv. Priya Sharma," in msg.text and "publicly listed in the Delhi High Court Bar Association directory" in msg.text
    assert "Punjab & Haryana Bar directory" in recorder.sent[1].text  # the row's own source wins
    assert "/unsubscribe/" in msg.text and "/api/v1/outreach/unsubscribe/" in msg.one_click_url
    assert "Join VidhiSangh free" in msg.html and "<script" not in msg.html
    assert "Simson" not in msg.text + msg.html and "Sent by VidhiSangh, India. Grievance officer" in msg.text

    # The daily limit holds for the rest of the (IST) day.
    async with session_factory() as s:
        assert (await service.send_batch(s, recorder))["sent"] == 0
        await service.update_settings(s, paused=False, daily_limit=50)
        await s.commit()
        third = await service.send_batch(s, recorder)
    assert third["bounced"] == 1  # meera refused → suppressed, never retried

    # One-click unsubscribe: no sign-in, no body, idempotent; unknown tokens look the same.
    token = msg.one_click_url.rsplit("/", 1)[-1]
    for _ in range(2):
        assert (await client.post(f"/api/v1/outreach/unsubscribe/{token}")).status_code == 204
    assert (await client.post("/api/v1/outreach/unsubscribe/nope")).status_code == 204
    async with session_factory() as s:
        c = await s.scalar(select(OutreachContact).where(OutreachContact.email == "priya@lawchambers.in"))
        assert c.status == OutreachStatus.UNSUBSCRIBED and c.unsubscribed_at
        await s.delete(c)  # even with the contact gone…
        await s.commit()
    again = await client.post("/api/v1/platform-admin/outreach/contacts", headers=member_headers,
                              files={"file": ("again.csv", b"email,source\npriya@lawchambers.in,Some list\nmeera@firm.in,Some list\n", "text/csv")})
    # …she is never re-added (Meera's bounced row still exists: a duplicate).
    assert (again.json()["unsubscribed"], again.json()["duplicate"], again.json()["added"]) == (1, 1, 0)

    # An invited person who signs up is counted as joined.
    await client.post("/api/v1/auth/register", json={
        "organisation_name": "Ravi", "full_name": "Ravi Kumar", "email": "ravi@advocates.in", "password": strong_password, "accept_terms": True})
    final = (await client.get("/api/v1/platform-admin/outreach", headers=member_headers)).json()
    assert final["counts"]["joined"] == 1 and final["counts"]["bounced"] == 1 and final["suppressed_total"] == 2
    assert final["sent_today"] == 1  # Ravi; Priya's row was deleted above


async def test_import_needs_a_source_and_an_email_column(client: AsyncClient, session_factory, strong_password) -> None:
    admin = await _admin(client, session_factory, strong_password)
    no_source = await client.post("/api/v1/platform-admin/outreach/contacts", headers=admin,
                                  files={"file": ("a.csv", b"email\nx@y.in\n", "text/csv")})
    assert no_source.json()["no_source"] == 1 and no_source.json()["added"] == 0
    bad = await client.post("/api/v1/platform-admin/outreach/contacts", headers=admin,
                            files={"file": ("b.csv", b"name\nx\n", "text/csv")})
    assert bad.status_code == 422
    assert (await client.post("/api/v1/platform-admin/outreach/test", headers=admin, json={})).status_code == 503
    preview = await client.get("/api/v1/platform-admin/outreach/preview", headers=admin)
    assert preview.status_code == 200 and "Unsubscribe" in preview.text


async def test_daily_limit_never_exceeds_the_configured_ceiling(session_factory) -> None:
    async with session_factory() as s:
        cfg = await service.update_settings(s, paused=False, daily_limit=500)
        assert cfg.daily_limit == 50
        assert await service.sent_today(s, datetime.now(UTC)) == 0
