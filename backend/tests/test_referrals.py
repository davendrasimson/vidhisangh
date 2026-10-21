"""Invite links (migration 0065): a stable personal code, credit for sign-ups, never a blocked sign-up."""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_research import API, _user


async def _register(client: AsyncClient, email: str, pw: str, ref: str | None) -> None:
    resp = await client.post(f"{API}/auth/register", json={
        "organisation_name": f"{email.split('@')[0]} chambers", "full_name": "Adv. Invitee", "email": email,
        "password": pw, "accept_terms": True, "referral_code": ref,
    })
    assert resp.status_code == 201, resp.text


async def test_invite_link_counts_people_who_joined_through_it(client: AsyncClient, strong_password: str) -> None:
    headers, _ = await _user(client, "Inviter LLP", "inviter@firm.co", strong_password)
    first = (await client.get(f"{API}/referrals/me", headers=headers)).json()
    assert len(first["code"]) == 7 and first["joined"] == 0
    assert first["link"] == f"https://vidhisangh.com/?ref={first['code']}&utm_source=tell_a_friend"
    assert (await client.get(f"{API}/referrals/me", headers=headers)).json()["code"] == first["code"]  # stable

    await _register(client, "one@other.co", strong_password, first["code"].lower())  # case-insensitive
    await _register(client, "two@other.co", strong_password, f"  {first['code']} ")
    # Unknown, malformed and missing codes are ignored; the sign-up still succeeds.
    await _register(client, "three@other.co", strong_password, "ZZZZZZZ")
    await _register(client, "four@other.co", strong_password, "<script>")
    await _register(client, "five@other.co", strong_password, None)

    assert (await client.get(f"{API}/referrals/me", headers=headers)).json()["joined"] == 2
    assert (await client.get(f"{API}/referrals/me")).status_code == 401


async def test_three_colleagues_make_a_founding_member(client: AsyncClient, strong_password: str) -> None:
    headers, _ = await _user(client, "Inviter LLP", "inviter@firm.co", strong_password)
    mine = (await client.get(f"{API}/referrals/me", headers=headers)).json()
    assert mine["founding_goal"] == 3 and mine["founding_member"] is False
    for n in range(3):
        await _register(client, f"colleague{n}@other.co", strong_password, mine["code"])
    mine = (await client.get(f"{API}/referrals/me", headers=headers)).json()
    assert mine["joined"] == 3 and mine["founding_member"] is True

    # The badge shows on the member's public page.
    on = await client.put(f"{API}/network/me/public-page", headers=headers, json={"enabled": True})
    assert on.status_code == 200, on.text
    page = await client.get(f"/in/{on.json()['handle']}/")
    assert page.status_code == 200 and "★ Founding Member" in page.text
