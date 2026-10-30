"""Firm-wide conflict search at matter intake, with similar-spelling matches."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.modules.matters.service import _name_similarity, _party_key
from tests.test_matters import API, _user

pytestmark = pytest.mark.asyncio


async def test_name_similarity_is_forgiving_about_order_prefixes_and_spelling() -> None:
    k = _party_key
    assert _name_similarity(k("M/s Sharma Traders Pvt. Ltd."), k("Sharma Traders")) == 1.0
    assert _name_similarity(k("Ramesh Kumar Sharma"), k("Sharma Ramesh Kumar")) == 1.0      # same words
    assert _name_similarity(k("Ramesh Kumar Sharma"), k("Ramesh Sharma")) >= 0.75            # one word short
    assert _name_similarity(k("Mohd. Irfan"), k("Mohammed Irfan")) >= 0.75                   # spelling
    assert _name_similarity(k("State of Haryana"), k("Ramesh Kumar")) < 0.5


async def test_intake_conflicts_find_clients_parties_and_opposing_counsel(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Conflicts LLP", "conflicts@firm.co", strong_password)
    m1 = (await client.post(f"{API}/matters", headers=h, json={"title": "Acme v. Beta", "client_name": "Acme Industries Pvt Ltd"})).json()
    await client.post(f"{API}/matters/{m1['id']}/parties", headers=h, json={"name": "Beta Builders LLP", "role": "respondent", "side": "opposing"})
    await client.post(f"{API}/matters/{m1['id']}/advocates", headers=h, json={"name": "Adv. Rakesh Verma", "side": "opposing", "role": "arguing_counsel"})
    m2 = (await client.post(f"{API}/matters", headers=h, json={"title": "Gamma v. Delta", "client_name": "Gamma Steel"})).json()
    await client.patch(f"{API}/matters/{m2['id']}", headers=h, json={"status": "closed", "stage": "closed"})
    # Another firm's matter never shows.
    h2, _ = await _user(client, "Elsewhere LLP", "elsewhere@firm.co", strong_password)
    await client.post(f"{API}/matters", headers=h2, json={"title": "Beta v. Omega", "client_name": "Beta Builders LLP"})

    # New client would be Beta Builders — they are the other side in m1 (exact).
    resp = await client.get(f"{API}/matters/conflicts", headers=h, params=[("name", "Beta Builders"), ("name", "Acme Industries")])
    assert resp.status_code == 200, resp.text
    hits = resp.json()
    beta = [x for x in hits if x["query"] == "Beta Builders"]
    assert len(beta) == 1 and beta[0]["matter_id"] == m1["id"] and beta[0]["side"] == "opposing" and beta[0]["match"] == "exact"
    acme = [x for x in hits if x["query"] == "Acme Industries"]
    assert acme[0]["side"] == "client" and acme[0]["match"] == "exact" and acme[0]["party_name"] == "Acme Industries Pvt Ltd"

    # A similar spelling of the opposing counsel, and a closed matter's client, still surface — closed sorted last.
    resp = await client.get(f"{API}/matters/conflicts", headers=h, params=[("name", "Rakesh Varma"), ("name", "Gamma Steels")])
    hits = resp.json()
    counsel = next(x for x in hits if x["query"] == "Rakesh Varma")
    assert counsel["side"] == "counsel" and counsel["score"] >= 0.75 and counsel["party_name"] == "Adv. Rakesh Verma"
    gamma = next(x for x in hits if x["query"] == "Gamma Steels")
    assert gamma["status"] == "closed" and gamma["side"] == "client"

    # Nothing on record: empty. Short names are ignored, not matched everywhere.
    assert (await client.get(f"{API}/matters/conflicts", headers=h, params=[("name", "Zeta Corp"), ("name", "Mr")])).json() == []
    # The matter being edited can be left out.
    resp = await client.get(f"{API}/matters/conflicts", headers=h, params=[("name", "Beta Builders"), ("exclude_matter", m1["id"])])
    assert resp.json() == []
