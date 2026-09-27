"""Client master — individuals & businesses, tax defaults, validation, and the
tokenised KYC flow (send → client submits → initiator notified → apply)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.modules.clients.kyc import gstin_check_digit, gstin_is_valid, validate_client

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _user(client: AsyncClient, org: str, email: str, pw: str) -> dict:
    resp = await client.post(f"{API}/auth/register", json={
        "organisation_name": org, "full_name": "Adv. Owner", "email": email, "password": pw, "accept_terms": True,
    })
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _gstin(state: str, pan: str) -> str:
    base = f"{state}{pan}1Z"
    return base + gstin_check_digit(base)


async def test_validation_rules() -> None:
    good = _gstin("07", "AAACR5055K")
    assert gstin_is_valid(good) and not gstin_is_valid(good[:-1] + "X")
    # A business with a consistent PAN/GSTIN/state and TDS config: clean.
    assert validate_client("business", {
        "legal_name": "Reliance Legal LLP", "pan": "AAACR5055K", "gstin": good, "state": "Delhi",
        "gst_applicable": True, "tds_applicable": True, "tds_section": "194J", "tds_rate": 10,
        "email": "a@b.co", "mobile": "9876543210", "pincode": "110001",
    }) == []
    # Mismatches are named, field by field.
    issues = validate_client("business", {
        "legal_name": "X", "pan": "AAACR5055K", "gstin": _gstin("27", "AAAAA0000A"), "state": "Delhi",
        "gst_applicable": True, "tds_applicable": True, "tds_section": "999", "email": "nope", "pincode": "12",
    })
    fields = {i.field for i in issues}
    assert {"gstin", "tds_section", "tds_rate", "email", "pincode"} <= fields
    assert any("does not contain this PAN" in i.message for i in issues)
    assert any(i.field == "state" and i.severity == "warning" for i in issues)  # GSTIN says Maharashtra


async def test_business_client_defaults_and_individual(client: AsyncClient, strong_password: str) -> None:
    h = await _user(client, "Tax LLP", "tax@firm.co", strong_password)
    gstin = _gstin("07", "AAACR5055K")
    biz = await client.post(f"{API}/clients", headers=h, json={
        "kind": "business", "display_name": "Reliance Legal LLP", "legal_name": "Reliance Legal LLP",
        "business_type": "llp", "pan": "aaacr5055k", "gstin": gstin.lower(), "state": "Delhi",
        "city": "New Delhi", "pincode": "110001", "email": "Accounts@Reliance.co", "mobile": "9876543210",
        "tds_applicable": True, "tds_section": "194J", "tds_rate": 10,
        "contact_person_name": "Meera Iyer", "consent_email": True,
    })
    assert biz.status_code == 201, biz.text
    b = biz.json()
    # Normalised and derived: upper-cased identifiers, GST applies with a GSTIN,
    # reverse charge defaults on for a business, state/place-of-supply codes.
    assert b["pan"] == "AAACR5055K" and b["gstin"] == gstin and b["email"] == "accounts@reliance.co"
    assert b["gst_applicable"] is True and b["gst_treatment"] == "registered_regular" and b["reverse_charge"] is True
    assert b["state_code"] == "07" and b["place_of_supply_code"] == "07"
    assert b["consent_source"] == "staff" and b["consent_recorded_at"]
    assert b["kyc_status"] == "not_started" and b["issues"] == []

    ind = await client.post(f"{API}/clients", headers=h, json={
        "kind": "individual", "display_name": "Sunita Verma", "first_name": "Sunita", "last_name": "Verma",
        "pan": "ABCPV1234K", "mobile": "98765 43210", "date_of_birth": "1980-05-12", "city": "Jaipur", "state": "Rajasthan",
    })
    assert ind.status_code == 201, ind.text
    assert ind.json()["state_code"] == "08" and ind.json()["gst_applicable"] is False

    listed = (await client.get(f"{API}/clients", headers=h, params={"q": "reliance"})).json()
    assert [c["display_name"] for c in listed] == ["Reliance Legal LLP"]
    by_kind = (await client.get(f"{API}/clients", headers=h, params={"kind": "individual"})).json()
    assert [c["display_name"] for c in by_kind] == ["Sunita Verma"]

    # Findings are reported, not blocked: a wrong GSTIN shows as an issue.
    bad = await client.patch(f"{API}/clients/{b['id']}", headers=h, json={"gstin": "07AAACR5055K1ZX"})
    assert bad.status_code == 200 and any(i["field"] == "gstin" for i in bad.json()["issues"])

    ref = (await client.get(f"{API}/clients/reference", headers=h)).json()
    assert any(s["section"] == "194J" for s in ref["tds_sections"]) and {"code": "07", "name": "Delhi"} in ref["states"]


async def test_kyc_form_flow(client: AsyncClient, strong_password: str) -> None:
    h = await _user(client, "KYC LLP", "kyc@firm.co", strong_password)
    c = (await client.post(f"{API}/clients", headers=h, json={
        "kind": "business", "display_name": "Kumar Traders", "email": "kumar@traders.in", "state": "Uttar Pradesh",
    })).json()

    sent = await client.post(f"{API}/clients/{c['id']}/kyc", headers=h, json={"message": "Please confirm your GST details."})
    assert sent.status_code == 201, sent.text
    req = sent.json()
    assert req["status"] == "sent" and req["sent_to_email"] == "kumar@traders.in" and "/kyc/" in req["url"]
    token = req["url"].rsplit("/", 1)[-1]
    assert (await client.get(f"{API}/clients/{c['id']}", headers=h)).json()["kyc_status"] == "pending"

    # The client opens the form without logging in: prefilled, with reference lists.
    view = await client.get(f"{API}/kyc/{token}")
    assert view.status_code == 200, view.text
    v = view.json()
    assert v["client_kind"] == "business" and v["prefill"]["state"] == "Uttar Pradesh" and v["firm_name"] == "KYC LLP"
    assert any(s["section"] == "194J" for s in v["tds_sections"])

    gstin = _gstin("09", "AAACK1234A")
    submitted = await client.post(f"{API}/kyc/{token}", json={
        "legal_name": "Kumar Traders Pvt Ltd", "pan": "AAACK1234A", "gstin": gstin, "gst_applicable": True,
        "tds_applicable": True, "tds_section": "194J", "tds_rate": 10, "mobile": "9123456789",
        "address_line1": "12 Civil Lines", "city": "Lucknow", "state": "Uttar Pradesh", "pincode": "226001",
        "consent_email": True, "consent_whatsapp": True, "declaration_accepted": True,
        # Reverse charge is the firm's call (RCM on legal services), so a client's tick is ignored.
        "reverse_charge": False,
    })
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted" and submitted.json()["issues"] == []
    # Submitting twice is refused; the record is untouched until the initiator applies.
    assert (await client.post(f"{API}/kyc/{token}", json={"declaration_accepted": True})).status_code == 422
    assert (await client.get(f"{API}/clients/{c['id']}", headers=h)).json()["gstin"] is None

    # The initiator is told, in-app, with a link to the client.
    notes = (await client.get(f"{API}/notifications", headers=h)).json()
    kyc_notes = [n for n in notes if n["type"] == "kyc_submitted"]
    assert kyc_notes and "Kumar Traders" in kyc_notes[0]["message"] and f"/app/clients/{c['id']}" in kyc_notes[0]["link"]

    # Review: a field-by-field diff of what the client sent.
    detail = (await client.get(f"{API}/clients/{c['id']}/kyc/{req['id']}", headers=h)).json()
    assert detail["status"] == "submitted"
    changed = {ch["field"]: ch for ch in detail["changes"]}
    assert changed["gstin"]["current"] is None and changed["gstin"]["submitted"] == gstin
    assert changed["legal_name"]["submitted"] == "Kumar Traders Pvt Ltd"

    # Apply: the client record takes the submission; KYC is verified; consent came from the form.
    applied = await client.post(f"{API}/clients/{c['id']}/kyc/{req['id']}/apply", headers=h, json={})
    assert applied.status_code == 200, applied.text
    a = applied.json()
    assert a["gstin"] == gstin and a["pan"] == "AAACK1234A" and a["tds_section"] == "194J" and a["reverse_charge"] is True
    assert a["kyc_status"] == "verified" and a["kyc_verified_at"] and a["consent_source"] == "kyc_form"
    assert a["consent_email"] is True and a["consent_whatsapp"] is True and a["consent_mobile"] is False
    assert a["state_code"] == "09" and a["place_of_supply_code"] == "09"
    assert (await client.get(f"{API}/clients/{c['id']}/kyc", headers=h)).json()[0]["status"] == "applied"

    # A used link is dead; an unknown one is 404.
    assert (await client.get(f"{API}/kyc/{token}")).json()["status"] == "applied"
    assert (await client.get(f"{API}/kyc/not-a-real-token")).status_code == 404


async def test_kyc_submission_flags_problems_for_the_initiator(client: AsyncClient, strong_password: str) -> None:
    h = await _user(client, "Check LLP", "chk@firm.co", strong_password)
    c = (await client.post(f"{API}/clients", headers=h, json={"kind": "individual", "display_name": "Rahul"})).json()
    token = (await client.post(f"{API}/clients/{c['id']}/kyc", headers=h, json={})).json()["url"].rsplit("/", 1)[-1]
    res = await client.post(f"{API}/kyc/{token}", json={
        "first_name": "Rahul", "pan": "BAD", "email": "not-an-email", "mobile": "12345", "declaration_accepted": True,
    })
    assert res.status_code == 200
    fields = {i["field"] for i in res.json()["issues"]}
    assert {"pan", "email", "mobile"} <= fields and "need a look" in (await client.get(f"{API}/notifications", headers=h)).json()[0]["message"]
    # Without the declaration nothing is recorded.
    token2 = (await client.post(f"{API}/clients/{c['id']}/kyc", headers=h, json={})).json()["url"].rsplit("/", 1)[-1]
    assert (await client.post(f"{API}/kyc/{token2}", json={"first_name": "R", "declaration_accepted": False})).status_code == 422


async def test_clients_are_tenant_isolated(client: AsyncClient, strong_password: str) -> None:
    a = await _user(client, "Firm A", "ca@firma.co", strong_password)
    b = await _user(client, "Firm B", "cb@firmb.co", strong_password)
    c = (await client.post(f"{API}/clients", headers=a, json={"kind": "individual", "display_name": "Private"})).json()
    assert (await client.get(f"{API}/clients/{c['id']}", headers=b)).status_code == 404
    assert (await client.post(f"{API}/clients/{c['id']}/kyc", headers=b, json={})).status_code == 404
    assert (await client.get(f"{API}/clients", headers=b)).json() == []
