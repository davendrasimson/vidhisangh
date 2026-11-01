"""Invitation emails: import, daily limit, one-click unsubscribe, suppression, conversions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.outreach_mail import OutreachMessage, RecipientRefused, set_outreach_sender
from app.modules.identity.models import User
from app.modules.outreach import runner, service
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
    assert (await client.post("/api/v1/platform-admin/outreach/send-now", headers=admin)).status_code == 503
    preview = await client.get("/api/v1/platform-admin/outreach/preview", headers=admin)
    assert preview.status_code == 200 and "Unsubscribe" in preview.text


async def test_admin_test_send_and_send_now(client: AsyncClient, session_factory, strong_password, monkeypatch) -> None:
    admin = await _admin(client, session_factory, strong_password)
    recorder = Recorder(refuse={"meera@firm.in"})
    set_outreach_sender(recorder)
    monkeypatch.setattr(runner, "SPACING_SECONDS", (0.0, 0.0))

    # "Send me a test": greets the admin by the account's name, to their own address by default.
    r = await client.post("/api/v1/platform-admin/outreach/test", headers=admin, json={})
    assert r.status_code == 200, r.text
    assert r.json() == {"sent_to": "ops@vidhisangh.co"}
    assert recorder.sent[-1].to == "ops@vidhisangh.co" and "Dear Ops Admin," in recorder.sent[-1].text
    assert recorder.sent[-1].subject.startswith("[Test] ")
    r = await client.post("/api/v1/platform-admin/outreach/test", headers=admin, json={"to": "meera@firm.in"})
    assert r.status_code == 502 and "refused" in r.json()["detail"]

    # Nothing queued yet: the button says so instead of silently doing nothing.
    r = await client.post("/api/v1/platform-admin/outreach/send-now", headers=admin)
    assert r.status_code == 409 and "upload a CSV" in r.json()["detail"]

    await client.post("/api/v1/platform-admin/outreach/contacts", headers=admin,
                      files={"file": ("list.csv", CSV.encode(), "text/csv")}, data={"source": "a bar directory"})
    async with session_factory() as s:
        await service.update_settings(s, paused=True, daily_limit=2)
        await s.commit()
    recorder.sent.clear()

    # Send now works while scheduled sending is paused, but only up to today's number.
    r = await client.post("/api/v1/platform-admin/outreach/send-now", headers=admin)
    assert r.status_code == 200 and r.json() == {"started": True, "planned": 2}
    assert await runner.wait() == {"sent": 2, "skipped": 0, "bounced": 0, "failed": 0}
    assert [m.to for m in recorder.sent] == ["priya@lawchambers.in", "ravi@advocates.in"]
    overview = (await client.get("/api/v1/platform-admin/outreach", headers=admin)).json()
    assert overview["sent_today"] == 2 and overview["counts"]["queued"] == 1 and overview["sending"] is False

    r = await client.post("/api/v1/platform-admin/outreach/send-now", headers=admin)
    assert r.status_code == 409 and "already gone out" in r.json()["detail"]


async def test_contacts_list_removal_flag_and_erasure(client: AsyncClient, session_factory, strong_password) -> None:
    admin = await _admin(client, session_factory, strong_password)
    csv_text = (
        "email,name,mobile,city,court,source\n"
        "arjun@chambers.in,Adv. Arjun Mehta,+91 98765-43210,Lucknow,Allahabad High Court,the Allahabad HC nominated counsel list\n"
        "neha@lawfirm.in,Adv. Neha Rao,0172-2740001,Chandigarh,P&H High Court,the P&H HC panel list\n"
        "kabir@adv.in,Adv. Kabir Singh,09812345678,Shimla,HP High Court,the HP HC list\n"
    )
    r = await client.post("/api/v1/platform-admin/outreach/contacts", headers=admin,
                          files={"file": ("states.csv", csv_text.encode(), "text/csv")})
    assert r.json()["added"] == 3

    # The list: mobiles normalised to 10 digits (a landline is dropped), searchable by name/email/mobile.
    page = (await client.get("/api/v1/platform-admin/outreach/contacts", headers=admin, params={"size": 2})).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    by_email = {c["email"]: c for c in (await client.get("/api/v1/platform-admin/outreach/contacts", headers=admin)).json()["items"]}
    assert by_email["arjun@chambers.in"]["mobile"] == "9876543210"
    assert by_email["neha@lawfirm.in"]["mobile"] is None
    assert by_email["kabir@adv.in"]["mobile"] == "9812345678" and by_email["kabir@adv.in"]["sent_at"] is None
    hit = (await client.get("/api/v1/platform-admin/outreach/contacts", headers=admin, params={"q": "98123"})).json()
    assert [c["email"] for c in hit["items"]] == ["kabir@adv.in"]
    assert (await client.get("/api/v1/platform-admin/outreach/contacts", headers=admin, params={"q": "neha"})).json()["total"] == 1

    # Approached: after a send, the row shows when.
    recorder = Recorder()
    async with session_factory() as s:
        await service.update_settings(s, paused=False, daily_limit=1)
        await s.commit()
        assert (await service.send_batch(s, recorder))["sent"] == 1
    sent = (await client.get("/api/v1/platform-admin/outreach/contacts", headers=admin, params={"status": "sent"})).json()
    assert sent["total"] == 1 and sent["items"][0]["email"] == recorder.sent[0].to and sent["items"][0]["sent_at"]

    # Someone asks to be removed: flagged with a note, suppressed, never sent, never re-importable.
    kabir = by_email["kabir@adv.in"]["id"]
    r = await client.post(f"/api/v1/platform-admin/outreach/contacts/{kabir}/removal-request", headers=admin,
                          json={"note": "Phoned on 31/10, asked not to be contacted"})
    assert r.status_code == 200 and r.json()["status"] == "removal_requested" and r.json()["removal_requested_at"]
    assert r.json()["removal_note"].startswith("Phoned")
    async with session_factory() as s:
        await service.update_settings(s, paused=False, daily_limit=50)
        await s.commit()
        await service.send_batch(s, recorder)
    assert "kabir@adv.in" not in [m.to for m in recorder.sent]
    flagged = (await client.get("/api/v1/platform-admin/outreach/contacts", headers=admin, params={"status": "removal_requested"})).json()
    assert [c["email"] for c in flagged["items"]] == ["kabir@adv.in"]
    overview = (await client.get("/api/v1/platform-admin/outreach", headers=admin)).json()
    assert overview["counts"]["removal_requested"] == 1 and overview["suppressed_total"] == 1

    # CSV export carries the same rows and the flag.
    export = await client.get("/api/v1/platform-admin/outreach/contacts.csv", headers=admin)
    assert export.status_code == 200 and export.headers["content-type"].startswith("text/csv")
    assert "kabir@adv.in" in export.text and "removal_requested" in export.text and "9876543210" in export.text

    # Erase: the row is gone, the suppression stays, re-import is refused.
    assert (await client.delete(f"/api/v1/platform-admin/outreach/contacts/{kabir}", headers=admin)).status_code == 204
    assert (await client.delete(f"/api/v1/platform-admin/outreach/contacts/{kabir}", headers=admin)).status_code == 404
    assert (await client.get("/api/v1/platform-admin/outreach/contacts", headers=admin)).json()["total"] == 2
    again = await client.post("/api/v1/platform-admin/outreach/contacts", headers=admin,
                              files={"file": ("again.csv", b"email,source\nkabir@adv.in,Some list\n", "text/csv")})
    assert again.json()["unsubscribed"] == 1 and again.json()["added"] == 0


async def test_daily_limit_never_exceeds_the_configured_ceiling(session_factory) -> None:
    async with session_factory() as s:
        cfg = await service.update_settings(s, paused=False, daily_limit=500)
        assert cfg.daily_limit == 100
        assert await service.sent_today(s, datetime.now(UTC)) == 0
