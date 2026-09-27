"""Marketplace tests — listings, browse/filter, respond, poster-only responses."""

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


async def test_listing_browse_and_respond(client: AsyncClient, strong_password: str) -> None:
    poster_h, poster = await _user(client, "Firm A", "poster@firma.co", strong_password)
    resp_h, _ = await _user(client, "Firm B", "responder@firmb.co", strong_password)

    listing = await client.post(
        f"{API}/marketplace/listings", headers=poster_h,
        json={"type": "local_counsel", "title": "Need counsel in Chennai",
              "description": "Appearance in Madras HC.", "practice_area": "Civil", "location": "Chennai"},
    )
    assert listing.status_code == 201, listing.text
    lid = listing.json()["id"]
    assert listing.json()["poster_name"].startswith("Adv.")

    # Browse is cross-tenant + filterable.
    browse = (await client.get(f"{API}/marketplace/listings?type=local_counsel", headers=resp_h)).json()
    assert any(x["id"] == lid for x in browse)

    # Poster cannot respond to their own listing.
    assert (await client.post(f"{API}/marketplace/listings/{lid}/respond", headers=poster_h,
                              json={"message": "hi"})).status_code == 422

    # Another user responds; response_count increments.
    r = await client.post(f"{API}/marketplace/listings/{lid}/respond", headers=resp_h,
                          json={"message": "I can appear — available next week."})
    assert r.status_code == 201
    assert (await client.get(f"{API}/marketplace/listings/{lid}", headers=poster_h)).json()["response_count"] == 1

    # Only the poster sees responses (with responder contact).
    got = await client.get(f"{API}/marketplace/listings/{lid}/responses", headers=poster_h)
    assert got.status_code == 200
    assert got.json()[0]["responder_email"] == "responder@firmb.co"
    assert (await client.get(f"{API}/marketplace/listings/{lid}/responses", headers=resp_h)).status_code == 403


async def test_close_listing_blocks_responses(client: AsyncClient, strong_password: str) -> None:
    poster_h, _ = await _user(client, "Firm A", "p2@firma.co", strong_password)
    resp_h, _ = await _user(client, "Firm B", "r2@firmb.co", strong_password)
    lid = (
        await client.post(f"{API}/marketplace/listings", headers=poster_h,
                          json={"type": "referral", "title": "Refer out", "description": "Property matter."})
    ).json()["id"]

    assert (await client.post(f"{API}/marketplace/listings/{lid}/close", headers=poster_h)).status_code == 200
    # Non-poster cannot close.
    assert (await client.post(f"{API}/marketplace/listings/{lid}/close", headers=resp_h)).status_code == 403
    # A closed listing rejects responses, and drops out of the default (open) browse.
    assert (await client.post(f"{API}/marketplace/listings/{lid}/respond", headers=resp_h,
                              json={"message": "hi"})).status_code == 409
    assert all(x["id"] != lid for x in (await client.get(f"{API}/marketplace/listings", headers=resp_h)).json())
