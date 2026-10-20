"""Public profile pages (/in/<handle>/): a separate opt-in that shows only what the member set to everyone."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio
API = "/api/v1"


async def _member(client: AsyncClient, pw: str, email: str, name: str) -> dict:
    r = await client.post(f"{API}/auth/register", json={"organisation_name": name, "full_name": name,
                                                         "email": email, "password": pw, "accept_terms": True})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_public_page_is_opt_in_and_shows_only_public_sections(client: AsyncClient, strong_password: str) -> None:
    h = await _member(client, strong_password, "rao@example.com", "Adv. Asha Rao")
    prof = await client.put(f"{API}/profiles/me", headers=h, json={
        "headline": "Criminal law, Delhi High Court", "bio": "Twenty years at the criminal bar.",
        "practice_areas": ["Criminal law", "Bail"], "courts": ["Delhi High Court"], "city": "New Delhi",
        "professional_phone": "+919876543210", "professional_email": "asha@chambers.in", "years_of_experience": 20,
    })
    assert prof.status_code in (200, 201), prof.text

    # Off by default: nothing on the open web.
    assert (await client.get(f"{API}/network/me/public-page", headers=h)).json() == {"enabled": False, "handle": None, "url": None}
    assert (await client.get("/in/asha-rao/")).status_code == 404

    on = (await client.put(f"{API}/network/me/public-page", headers=h, json={"enabled": True})).json()
    assert on == {"enabled": True, "handle": "asha-rao", "url": "https://vidhisangh.com/in/asha-rao/"}
    page = await client.get("/in/asha-rao/")
    assert page.status_code == 200
    html = page.text
    assert "<h1>Adv. Asha Rao</h1>" in html and "Twenty years at the criminal bar." in html and "Bail" in html
    assert "+919876543210" not in html and "asha@chambers.in" not in html  # contact never shown
    assert "New Delhi" not in html  # location defaults to connections only
    assert 'href="https://wa.me/?text=' in html and '"@type": "ProfilePage"' in html
    assert "https://vidhisangh.com/in/asha-rao/" in (await client.get("/sitemap-profiles.xml")).text

    # A second member with the same name gets the next free address; a taken or reserved one is refused.
    h2 = await _member(client, strong_password, "rao2@example.com", "Asha Rao")
    assert (await client.put(f"{API}/network/me/public-page", headers=h2, json={"enabled": True})).json()["handle"] == "asha-rao-2"
    assert (await client.put(f"{API}/network/me/public-page", headers=h2, json={"enabled": True, "handle": "asha-rao"})).status_code == 409
    assert (await client.put(f"{API}/network/me/public-page", headers=h2, json={"enabled": True, "handle": "admin"})).status_code == 409
    assert (await client.put(f"{API}/network/me/public-page", headers=h2, json={"enabled": True, "handle": "Bad Handle"})).status_code == 422

    # Making the profile private takes the page down at once.
    await client.put(f"{API}/profiles/me", headers=h, json={"visibility": "private"})
    assert (await client.get("/in/asha-rao/")).status_code == 404
    # Withdrawn: gone, but the address is kept for later.
    await client.put(f"{API}/profiles/me", headers=h, json={"visibility": "public"})
    off = (await client.put(f"{API}/network/me/public-page", headers=h, json={"enabled": False})).json()
    assert off["enabled"] is False and off["handle"] == "asha-rao"
    assert (await client.get("/in/asha-rao/")).status_code == 404
    assert "asha-rao/" not in (await client.get("/sitemap-profiles.xml")).text.replace("asha-rao-2/", "")
