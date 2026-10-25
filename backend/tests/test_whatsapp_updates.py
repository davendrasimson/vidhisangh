"""Product updates on WhatsApp: the member's consent ledger and campaign sends."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.whatsapp import WhatsAppError
from app.modules.identity.models import User
from app.modules.notifications import whatsapp_updates as updates
from app.modules.notifications.models import WhatsAppCampaignSend, WhatsAppUpdatesConsent
from app.modules.profile.models import ProfessionalProfile

pytestmark = pytest.mark.asyncio

API = "/api/v1"


class Recorder:
    def __init__(self, fail_for: str | None = None) -> None:
        self.sent: list[tuple[str, str, str, list[str]]] = []
        self.fail_for = fail_for

    async def send_template(self, phone, template, lang, body):
        if phone == self.fail_for:
            raise WhatsAppError("HTTP 400 code 131026")
        self.sent.append((phone, template, lang, body))
        return "wamid.test"


async def _member(client: AsyncClient, email: str, pw: str, name: str, role: str | None = None) -> dict:
    resp = await client.post(f"{API}/auth/register", json={
        "organisation_name": f"{name} chambers", "full_name": name, "email": email,
        "password": pw, "accept_terms": True, "professional_role": role,
    })
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _phone(session_factory, email: str, phone: str, verified: bool = True, languages: list | None = None) -> None:
    async with session_factory() as s:
        await s.execute(update(User).where(User.email == email).values(phone=phone, is_phone_verified=verified))
        if languages is not None:
            uid = await s.scalar(select(User.id).where(User.email == email))
            await s.execute(update(ProfessionalProfile).where(ProfessionalProfile.user_id == uid).values(languages=languages))
        await s.commit()


async def test_consent_is_a_ledger_of_yes_and_no(client: AsyncClient, strong_password: str, session_factory) -> None:
    h = await _member(client, "c@example.com", strong_password, "Asha Rao", "advocate")
    got = (await client.get(f"{API}/notifications/whatsapp-updates", headers=h)).json()
    assert got == {"status": "unasked", "phone_verified": False}

    yes = await client.put(f"{API}/notifications/whatsapp-updates", headers=h, json={"granted": True, "source": "home"})
    assert yes.status_code == 200 and yes.json()["status"] == "granted"
    no = await client.put(f"{API}/notifications/whatsapp-updates", headers=h, json={"granted": False})
    assert no.json()["status"] == "refused"
    assert (await client.put(f"{API}/notifications/whatsapp-updates", headers=h,
                             json={"granted": True, "source": "banner"})).status_code == 422

    async with session_factory() as s:
        rows = list(await s.scalars(select(WhatsAppUpdatesConsent).order_by(WhatsAppUpdatesConsent.recorded_at)))
    # Withdrawal adds a row; the earlier grant stays as evidence.
    assert [(r.granted, r.source) for r in rows] == [(True, "home"), (False, "settings")]
    assert rows[0].notice_version == "2026-10-25"


async def test_campaign_audience_templates_and_consent(client: AsyncClient, strong_password: str, session_factory) -> None:
    judge = await _member(client, "judge@example.com", strong_password, "Hon'ble Muneer Khan", "judicial_officer")
    await _member(client, "norole@example.com", strong_password, "Ravi Kumar")
    adv = await _member(client, "adv@example.com", strong_password, "Adv. Neha Gupta", "advocate")
    await _member(client, "no@example.com", strong_password, "Sunil Jain", "advocate")
    await _member(client, "unverified@example.com", strong_password, "Pooja", "advocate")
    await _member(client, "nophone@example.com", strong_password, "Karan", "advocate")
    await _member(client, "retd@example.com", strong_password, "Retd Judge", "retired_judicial_officer")
    await _phone(session_factory, "judge@example.com", "+919800000001", languages=["Hindi"])
    await _phone(session_factory, "norole@example.com", "+919800000002")
    await _phone(session_factory, "adv@example.com", "+919800000003", languages=["English", "Hindi"])
    await _phone(session_factory, "no@example.com", "+919800000004")
    await _phone(session_factory, "unverified@example.com", "+919800000005", verified=False)
    await _phone(session_factory, "retd@example.com", "+919800000006")
    for h, granted in ((judge, True), (adv, True)):
        await client.put(f"{API}/notifications/whatsapp-updates", headers=h, json={"granted": granted})
    no_h = await _member(client, "no2@example.com", strong_password, "Dummy", "advocate")  # unrelated member
    del no_h
    async with session_factory() as s:
        uid = await s.scalar(select(User.id).where(User.email == "no@example.com"))
        s.add(WhatsAppUpdatesConsent(user_id=uid, granted=False, source="settings", recorded_at=datetime.now(UTC)))
        await s.commit()

    # Normal run: only those who said yes.
    async with session_factory() as s:
        recipients, skipped = await updates.collect(s, owner_approved=False)
    assert {(r.phone, r.template, r.language, r.basis) for r in recipients} == {
        ("+919800000001", "judicial_officer_update", "hi", "consent"),
        ("+919800000003", "product_update", "en", "consent"),
    }
    assert skipped == {"unverified_number": 1, "said_no": 1, "not_asked": 2}
    assert next(r for r in recipients if r.template == "judicial_officer_update").first_name == "Muneer"

    # Owner-approved launch: also the never-asked, never the "no" or unverified.
    async with session_factory() as s:
        recipients, skipped = await updates.collect(s, owner_approved=True)
    by_phone = {r.phone: r for r in recipients}
    assert set(by_phone) == {"+919800000001", "+919800000002", "+919800000003", "+919800000006"}
    assert by_phone["+919800000002"].template == "judicial_officer_update"  # no profession picked
    assert by_phone["+919800000002"].basis == "owner_approved"
    assert by_phone["+919800000006"].template == "product_update"  # retired judges get the general update
    assert skipped["said_no"] == 1 and skipped["unverified_number"] == 1


async def test_a_shared_number_gets_one_message_the_judicial_one(client: AsyncClient, strong_password: str, session_factory) -> None:
    await _member(client, "admin@example.com", strong_password, "Davendra Singh", "advocate")
    await _member(client, "bench@example.com", strong_password, "Sushma Singh", "judicial_officer")
    # The same number, written two ways on two accounts.
    await _phone(session_factory, "admin@example.com", "+919811111111")
    await _phone(session_factory, "bench@example.com", "919811111111")
    async with session_factory() as s:
        recipients, _ = await updates.collect(s, owner_approved=True)
    assert [(r.template, r.first_name) for r in recipients] == [("judicial_officer_update", "Sushma")]


async def test_sending_once_per_number_and_logging_failures(client: AsyncClient, strong_password: str, session_factory) -> None:
    await _member(client, "a@example.com", strong_password, "Anil Verma", "judicial_officer")
    await _member(client, "b@example.com", strong_password, "Bina Das", "advocate")
    await _phone(session_factory, "a@example.com", "+919822222221")
    await _phone(session_factory, "b@example.com", "+919822222222")
    sender = Recorder(fail_for="+919822222222")
    async with session_factory() as s:
        recipients, _ = await updates.collect(s, owner_approved=True)
        report = await updates.send_campaign(s, sender, "launch-test", recipients)
    assert report == {"sent": 1, "already": 0, "failed": 1}
    assert sender.sent == [("+919822222221", "judicial_officer_update", "en", ["Anil"])]

    async with session_factory() as s:
        rows = {r.template: r for r in await s.scalars(select(WhatsAppCampaignSend))}
        assert rows["judicial_officer_update"].status == "sent"
        assert rows["product_update"].status == "failed" and "131026" in rows["product_update"].detail
        assert all("9822" not in r.phone_hash for r in rows.values())  # never the number itself
        # A rerun sends nothing again, to anyone.
        again = await updates.send_campaign(s, Recorder(), "launch-test", recipients)
    assert again == {"sent": 0, "already": 2, "failed": 0}


def test_greeting_and_language() -> None:
    assert updates.first_name("Adv. Neha Gupta", "en") == "Neha"
    assert updates.first_name("Hon'ble Justice  R. K. Mehta", "en") == "R."
    assert updates.first_name("", "hi") == "जी"
    assert updates.first_name(None, "en") == "there"
    assert updates.language_for(["Hindi"]) == "hi"
    assert updates.language_for(["Hindi", "English"]) == "en"
    assert updates.language_for([]) == "en"


def test_the_script_only_sends_when_told_to() -> None:
    from app.scripts.whatsapp_updates import parse

    assert parse(["--campaign", "x"]).dry_run is True
    assert parse(["--campaign", "x", "--owner-approved"]).dry_run is True
    assert parse(["--campaign", "x", "--send", "--dry-run"]).dry_run is True
    assert parse(["--campaign", "x", "--send"]).dry_run is False
