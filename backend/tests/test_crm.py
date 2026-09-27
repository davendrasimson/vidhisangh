"""CRM tests — leads, activities, pipeline, convert-to-matter, source analytics."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _user(client: AsyncClient, org: str, email: str, pw: str) -> tuple[dict, dict]:
    resp = await client.post(
        f"{API}/auth/register",
        json={
            "organisation_name": org,
            "full_name": f"Adv. {email.split('@')[0].title()}",
            "email": email,
            "password": pw,
            "accept_terms": True,
        },
    )
    assert resp.status_code == 201, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = (await client.get(f"{API}/auth/me", headers=headers)).json()
    return headers, me


async def _lead(client: AsyncClient, h: dict, **overrides) -> dict:
    body = {"name": "Ravi Kumar", "source": "referral", "practice_area": "Property",
            "estimated_value": "50000.00", "referred_by": "Adv. Sharma"}
    body.update(overrides)
    resp = await client.post(f"{API}/crm/leads", headers=h, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_lead_lifecycle_and_activities(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "CRM LLP", "crm@firm.co", strong_password)
    lead = await _lead(client, h)
    assert lead["status"] == "new" and lead["source"] == "referral"
    lid = lead["id"]

    # Move the lead along the pipeline.
    upd = await client.patch(f"{API}/crm/leads/{lid}", headers=h, json={"status": "qualified"})
    assert upd.json()["status"] == "qualified"

    # Log a follow-up, then complete it.
    act = await client.post(
        f"{API}/crm/leads/{lid}/activities", headers=h,
        json={"type": "call", "subject": "Intro call", "due_on": "2026-07-20"},
    )
    assert act.status_code == 201
    aid = act.json()["id"]
    done = await client.post(f"{API}/crm/activities/{aid}/complete", headers=h)
    assert done.json()["completed"] is True and done.json()["completed_at"] is not None

    detail = (await client.get(f"{API}/crm/leads/{lid}", headers=h)).json()
    assert len(detail["activities"]) == 1


async def test_pipeline_and_source_analytics(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Pipe LLP", "pipe@firm.co", strong_password)
    a = await _lead(client, h, name="A", source="referral", estimated_value="10000.00")
    await _lead(client, h, name="B", source="website", estimated_value="20000.00")
    await client.patch(f"{API}/crm/leads/{a['id']}", headers=h, json={"status": "won"})

    pipeline = (await client.get(f"{API}/crm/pipeline", headers=h)).json()
    by_status = {c["status"]: c for c in pipeline}
    assert by_status["won"]["count"] == 1
    assert by_status["new"]["count"] == 1
    # Column carries aggregate value.
    assert float(by_status["won"]["value"]) == 10000.0

    sources = (await client.get(f"{API}/crm/analytics/sources", headers=h)).json()
    ref = next(s for s in sources if s["source"] == "referral")
    assert ref["total"] == 1 and ref["won"] == 1
    web = next(s for s in sources if s["source"] == "website")
    assert web["total"] == 1 and web["won"] == 0


async def test_convert_lead_to_matter(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Convert LLP", "conv@firm.co", strong_password)
    lead = await _lead(client, h, name="Meera Nair", practice_area="Family")

    convert = await client.post(f"{API}/crm/leads/{lead['id']}/convert", headers=h)
    assert convert.status_code == 201, convert.text
    matter_id = convert.json()["matter_id"]

    # The matter exists and the lead is marked won + linked.
    matter = await client.get(f"{API}/matters/{matter_id}", headers=h)
    assert matter.status_code == 200
    assert matter.json()["client_name"] == "Meera Nair"
    lead_after = (await client.get(f"{API}/crm/leads/{lead['id']}", headers=h)).json()
    assert lead_after["status"] == "won"
    assert lead_after["converted_matter_id"] == matter_id

    # Converting again is rejected.
    assert (await client.post(f"{API}/crm/leads/{lead['id']}/convert", headers=h)).status_code == 409


async def test_crm_tenant_isolation(client: AsyncClient, strong_password: str) -> None:
    a_h, _ = await _user(client, "Firm A", "cra@firma.co", strong_password)
    b_h, _ = await _user(client, "Firm B", "crb@firmb.co", strong_password)
    a_lead = await _lead(client, a_h, name="Private lead")
    assert (await client.get(f"{API}/crm/leads", headers=b_h)).json() == []
    assert (await client.get(f"{API}/crm/leads/{a_lead['id']}", headers=b_h)).status_code == 404
