"""Professional profile module tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.identity.models import User
from app.modules.profile.models import ProfessionalProfile

pytestmark = pytest.mark.asyncio


async def _register(client: AsyncClient, org: str, email: str, pw: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organisation_name": org,
            "full_name": "Adv. Test",
            "email": email,
            "password": pw,
            "accept_terms": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _auth(client: AsyncClient, email: str, pw: str) -> tuple[dict, dict]:
    tokens = await _register(client, "Chamber", email, pw)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    return headers, me


async def test_get_my_profile_autocreates(client: AsyncClient, strong_password: str) -> None:
    headers, me = await _auth(client, "p1@chamber.co", strong_password)
    resp = await client.get("/api/v1/profiles/me", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_id"] == me["id"]
    assert body["verification_status"] == "unverified"
    assert body["practice_areas"] == []


async def test_update_profile(client: AsyncClient, strong_password: str) -> None:
    headers, _ = await _auth(client, "p2@chamber.co", strong_password)
    payload = {
        "headline": "Criminal defence advocate",
        "bio": "15 years at the trial and appellate bar.",
        "professional_role": "judicial_officer",
        "designation": "Additional District Judge",
        "years_of_experience": 15,
        "practice_areas": ["Criminal", "Constitutional"],
        "courts": ["Delhi High Court", "Supreme Court of India"],
        "languages": ["English", "Hindi"],
        "education": [
            {
                "institution": "NLSIU",
                "degree": "ba_llb",
                "level": "undergraduate",
                "field_of_study": "Law",
                "year": 2009,
            }
        ],
        "employment_history": [
            {
                "organisation": "District Judiciary",
                "designation": "Civil Judge",
                "from_year": 2012,
                "current": True,
            }
        ],
        "memberships": [{"organisation": "Judicial Officers Association", "year": 2012}],
        "publications": [
            {
                "title": "The Evolution of Bail Jurisprudence",
                "publisher": "SCC Journal",
                "year": 2021,
            },
        ],
        "city": "New Delhi",
        "state": "Delhi",
        "judicial_court_name": "District & Sessions Court, New Delhi",
        "judicial_district": "New Delhi",
        "judicial_state": "Delhi",
        "visibility_settings": {"contact": "none", "education": "connections"},
    }
    resp = await client.put("/api/v1/profiles/me", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["headline"] == "Criminal defence advocate"

    got = (await client.get("/api/v1/profiles/me", headers=headers)).json()
    assert got["years_of_experience"] == 15
    assert "Constitutional" in got["practice_areas"]
    assert got["education"][0]["institution"] == "NLSIU"
    assert got["publications"][0]["title"] == "The Evolution of Bail Jurisprudence"
    assert got["publications"][0]["publisher"] == "SCC Journal"
    assert got["professional_role"] == "judicial_officer"
    assert got["judicial_court_name"] == "District & Sessions Court, New Delhi"
    assert got["employment_history"][0]["current"] is True


async def test_profile_masters_and_dpdp_group_masking(
    client: AsyncClient, session_factory: async_sessionmaker, strong_password: str
) -> None:
    headers, me = await _auth(client, "viewer@chamber.co", strong_password)
    masters = await client.get("/api/v1/profiles/masters", headers=headers)
    assert masters.status_code == 200, masters.text
    assert "Civil Law" in masters.json()["practice_areas"]
    assert "Bar Council of Delhi" in masters.json()["bar_councils"]
    assert set(masters.json()["states"]) == set(masters.json()["cities_by_state"])

    target_id = uuid.uuid4()
    tenant_id = uuid.UUID(me["tenant_id"])
    async with session_factory() as session:
        session.add(
            User(
                id=target_id,
                tenant_id=tenant_id,
                email="private-profile@chamber.co",
                full_name="Judicial Officer",
                hashed_password=None,
                is_active=True,
            )
        )
        await session.flush()
        session.add(
            ProfessionalProfile(
                tenant_id=tenant_id,
                user_id=target_id,
                headline="Judicial officer",
                professional_role="judicial_officer",
                enrollment_number="D/123456/2012",
                education=[{"institution": "Delhi University", "degree": "llb_3"}],
                professional_email="private@example.test",
                visibility_settings={
                    "about": "everyone",
                    "professional": "everyone",
                    "education": "connections",
                    "location": "connections",
                    "contact": "none",
                    "judicial": "connections",
                },
            )
        )
        await session.commit()

    viewed = await client.get(f"/api/v1/profiles/{target_id}", headers=headers)
    assert viewed.status_code == 200, viewed.text
    detail = viewed.json()
    assert detail["headline"] == "Judicial officer"
    assert detail["enrollment_number"] == "••••2012"
    assert detail["education"] == []
    assert detail["professional_email"] is None
    assert {"contact", "education", "judicial"}.issubset(detail["masked_groups"])


async def test_digital_visiting_card(client: AsyncClient, strong_password: str) -> None:
    headers, _ = await _auth(client, "card@chamber.co", strong_password)
    await client.put(
        "/api/v1/profiles/me",
        headers=headers,
        json={
            "headline": "Tax & GST counsel",
            "bar_council": "Bar Council of Maharashtra & Goa",
            "website": "https://example.co",
            "city": "Mumbai",
        },
    )

    vcard = await client.get("/api/v1/profiles/me/vcard", headers=headers)
    assert vcard.status_code == 200, vcard.text
    assert vcard.headers["content-type"].startswith("text/vcard")
    body = vcard.text
    assert body.startswith("BEGIN:VCARD")
    assert "TITLE:Tax & GST counsel" in body
    assert "ORG:Bar Council of Maharashtra & Goa" in body
    assert "END:VCARD" in body

    qr = await client.get("/api/v1/profiles/me/qr", headers=headers)
    assert qr.status_code == 200
    assert qr.headers["content-type"] == "image/svg+xml"
    assert b"<svg" in qr.content


async def test_self_endorse_rejected(client: AsyncClient, strong_password: str) -> None:
    headers, me = await _auth(client, "p3@chamber.co", strong_password)
    resp = await client.post(
        f"/api/v1/profiles/{me['id']}/endorsements",
        headers=headers,
        json={"skill": "Arbitration"},
    )
    assert resp.status_code == 422


async def test_verification_request_sets_pending(client: AsyncClient, strong_password: str) -> None:
    headers, _ = await _auth(client, "p4@chamber.co", strong_password)
    resp = await client.post(
        "/api/v1/profiles/me/verification",
        headers=headers,
        json={"enrollment_number": "D/1234/2010", "bar_council": "Bar Council of Delhi"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "pending"

    profile = (await client.get("/api/v1/profiles/me", headers=headers)).json()
    assert profile["verification_status"] == "pending"
    assert profile["enrollment_number"] == "D/1234/2010"


async def test_endorse_and_recommend_other_user(
    client: AsyncClient, session_factory: async_sessionmaker, strong_password: str
) -> None:
    headers, me = await _auth(client, "p5@chamber.co", strong_password)
    tenant_id = uuid.UUID(me["tenant_id"])

    # Seed a second colleague (with a profile) in the same tenant.
    colleague_id = uuid.uuid4()
    async with session_factory() as s:
        s.add(
            User(
                id=colleague_id,
                tenant_id=tenant_id,
                email="colleague@chamber.co",
                full_name="Adv. Colleague",
                hashed_password=None,
                is_active=True,
            )
        )
        await s.flush()
        s.add(ProfessionalProfile(tenant_id=tenant_id, user_id=colleague_id))
        await s.commit()

    endorse = await client.post(
        f"/api/v1/profiles/{colleague_id}/endorsements",
        headers=headers,
        json={"skill": "Mergers & Acquisitions"},
    )
    assert endorse.status_code == 201, endorse.text

    # Duplicate endorsement of the same skill is rejected.
    dup = await client.post(
        f"/api/v1/profiles/{colleague_id}/endorsements",
        headers=headers,
        json={"skill": "Mergers & Acquisitions"},
    )
    assert dup.status_code == 409

    rec = await client.post(
        f"/api/v1/profiles/{colleague_id}/recommendations",
        headers=headers,
        json={"relationship_context": "Co-counsel", "body": "Exceptional drafting and courtcraft."},
    )
    assert rec.status_code == 201, rec.text

    detail = (await client.get(f"/api/v1/profiles/{colleague_id}", headers=headers)).json()
    assert detail["endorsement_summary"].get("Mergers & Acquisitions") == 1
    assert len(detail["recommendations"]) == 1
