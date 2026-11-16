"""Court desk: each court's cause-list index, posted to the court's group and shown to its members."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.modules.courts import fetch as fetching
from app.modules.courts import service
from app.modules.courts.models import CourtCauseList
from app.modules.courts.registry import BY_SLUG, COURTS
from app.modules.groups import official as groups_official
from app.modules.groups.models import Group, GroupPost
from app.modules.identity.models import User
from app.modules.profile.models import ProfessionalProfile

pytestmark = pytest.mark.asyncio
API = "/api/v1"
SCI = "https://api.sci.gov.in/jonew/cl/"


def _cell(day, path: str) -> str:
    if not path:
        return "<td></td>"
    return f'<td><a href="{SCI}{path}" target="_blank">{day.strftime("%d-%m-%Y")}</a></td>'


def sci_html(today, tomorrow, supplementary: bool = False) -> str:
    """The glance table as the Supreme Court site lays it out: a first row with the
    'ALL COURTS' cell and fourteen list cells, later rows with fourteen."""
    d1, d2 = today.isoformat(), tomorrow.isoformat()
    first = (f"advance/{d1}/M_J.pdf", f"{d1}/M_J_1.pdf", f"{d1}/M_J_2.pdf", "", "", f"{d1}/M_C_1.pdf", "",
             f"{d1}/M_S_1.pdf", "", "", "", f"{d1}/M_R_1.pdf", f"{d1}/M_R_2.pdf" if supplementary else "", "")
    second = (f"advance/{d2}/M_J.pdf", f"{d2}/M_J_1.pdf", "", f"{d2}/F_J_1.pdf", "", "", "", "", "", "", "", "", "",
              f"wk/{d2}_{d2}/weekly.pdf")
    later = today + timedelta(days=7)  # the Supreme Court publishes advance lists two weeks ahead
    third = (f"advance/{later.isoformat()}/M_J.pdf", *[""] * 13)
    rows = ("<tr><td>only</td><td>three</td><td>cells</td></tr>"
            "<tr><td>ALL COURTS</td>" + "".join(_cell(today, p) for p in first) + "</tr>"
            "<tr>" + "".join(_cell(tomorrow, p) for p in second) + "</tr>"
            "<tr>" + "".join(_cell(later, p) for p in third) + "</tr>")
    return f"<html><body><p>Search a case: <input name='party_name'></p><table class='causelist-glance'>{rows}</table></body></html>"


def allahabad_html(today, tomorrow) -> str:
    """As the site writes it: bare option values, newest first, one selected."""
    return (f'<select class="form-control" name="listDate"><option value={tomorrow.strftime("%d-%m-%Y")} selected>x</option>'
            f'<option value="{today.strftime("%d/%m/%Y")}">y</option><option value="">--</option></select>')


def mock_http(today, tomorrow, *, allahabad_down: bool = False, supplementary: bool = False) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://www.sci.gov.in/cause-list/"):
            assert request.method == "GET"
            return httpx.Response(200, text=sci_html(today, tomorrow, supplementary))
        if "input1A.jsp" in url or "input1L.jsp" in url:
            if allahabad_down:
                raise httpx.ConnectError("down")
            assert request.method == "POST" and request.content == b"listType=Z", "only the combined-list form, never a search"
            return httpx.Response(200, text=allahabad_html(today, tomorrow) if "input1A" in url else '<select name="listDate"></select>')
        raise AssertionError(f"unexpected request {url}")
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_every_court_has_an_official_group_and_a_checked_address() -> None:
    slugs = {g.slug for g in groups_official.GROUPS}
    assert len(COURTS) >= 25 and len({c.slug for c in COURTS}) == len(COURTS)
    for c in COURTS:
        assert c.slug in slugs, c.slug
        assert c.website.startswith("https://") and c.cause_list_url.startswith("https://")
        assert c.fetcher in (None, *fetching.FETCHERS)
    assert BY_SLUG["supreme-court-of-india"].fetcher == "sci" and BY_SLUG["allahabad-high-court"].fetcher == "allahabad"


def test_the_supreme_court_index_is_read_by_column_position() -> None:
    today = service.today_ist()
    tomorrow = today + timedelta(days=1)
    found = fetching.parse_sci(sci_html(today, tomorrow))
    assert set(found) == {today, tomorrow, today + timedelta(days=7)}
    assert found[today + timedelta(days=7)] == [{"label": "Advance list", "url": f"{SCI}advance/{(today + timedelta(days=7)).isoformat()}/M_J.pdf"}]
    assert [l["label"] for l in found[today]] == [
        "Advance list", "Court number-wise, main", "Court number-wise, supplementary",
        "Chamber, main", "Single judge, main", "Registrar, main"]
    assert found[today][1]["url"] == f"{SCI}{today.isoformat()}/M_J_1.pdf"
    assert [l["label"] for l in found[tomorrow]] == ["Advance list", "Court number-wise, main", "Judge-wise, main", "Weekly list"]
    # A table whose rows no longer have fourteen columns yields nothing rather than mislabelled links.
    assert fetching.parse_sci("<table class='causelist-glance'><tr><td><a href='x.pdf'>1</a></td></tr></table>") == {}
    assert fetching.parse_dates(allahabad_html(today, tomorrow)) == [today, tomorrow]


async def test_lists_are_recorded_once_posted_once_and_shown_to_the_courts_members(
    client: AsyncClient, session_factory, strong_password,
) -> None:
    today = service.today_ist()
    tomorrow = today + timedelta(days=1)
    async with session_factory() as s:
        await groups_official.seed(s)
        await s.commit()

    # The morning run: two courts; today's and tomorrow's lists are posted, the advance list a week out is only recorded.
    async with session_factory() as s, mock_http(today, tomorrow) as http:
        assert await service.refresh(s, http, today) == {"supreme-court-of-india": 3, "allahabad-high-court": 2}
        assert await service.post_new(s) == 4
        assert await service.post_new(s) == 0
        await s.commit()
    async with session_factory() as s:
        rows = (await s.scalars(select(CourtCauseList).order_by(CourtCauseList.court_slug, CourtCauseList.for_date))).all()
        assert [(r.court_slug, r.for_date, len(r.lists), r.group_post_id is not None) for r in rows] == [
            ("allahabad-high-court", today, 1, True), ("allahabad-high-court", tomorrow, 1, True),
            ("supreme-court-of-india", today, 6, True), ("supreme-court-of-india", tomorrow, 4, True),
            ("supreme-court-of-india", today + timedelta(days=7), 1, False)]
        sc_group = await s.scalar(select(Group).where(Group.slug == "supreme-court-of-india"))
        posts = (await s.scalars(select(GroupPost).where(GroupPost.group_id == sc_group.id).order_by(GroupPost.created_at))).all()
        assert sc_group.post_count == 3 and len(posts) == 3  # the starter post and two days
        assert posts[1].content.startswith("Cause list for today") and "Registrar, main" in posts[1].content
        assert f'href="{SCI}{today.isoformat()}/M_R_1.pdf"' in posts[1].content_html
        assert "Cause list for tomorrow" in posts[2].content

    # The evening run: a supplementary list appears; the row is updated, nothing is posted twice.
    async with session_factory() as s, mock_http(today, tomorrow, supplementary=True) as http:
        assert await service.refresh(s, http, today) == {"supreme-court-of-india": 1, "allahabad-high-court": 0}
        assert await service.post_new(s) == 0
        await s.commit()
    # A court site that is down fails alone.
    async with session_factory() as s, mock_http(today, tomorrow, supplementary=True, allahabad_down=True) as http:
        assert await service.refresh(s, http, today) == {"supreme-court-of-india": 0, "allahabad-high-court": -1}

    # Members see their own court's card, from their profile alone.
    async def member(email: str, name: str, **profile) -> dict:
        r = await client.post(f"{API}/auth/register", json={
            "organisation_name": f"{name} chambers", "full_name": name, "email": email, "password": strong_password,
            "accept_terms": True, "professional_role": "advocate", "practice_type": "individual"})
        assert r.status_code == 201, r.text
        async with session_factory() as s:
            user_id = await s.scalar(select(User.id).where(User.email == email))
            await s.execute(update(ProfessionalProfile).where(ProfessionalProfile.user_id == user_id).values(**profile))
            await s.commit()
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    sc = await member("aor@example.com", "Adv. Mehta", courts=["Supreme Court of India", "Delhi High Court"])
    brief = (await client.get(f"{API}/brief", headers=sc)).json()
    court = brief["court"]
    assert court["name"] == "Supreme Court of India" and court["ecourts_url"] is None and court["fetches"]
    assert court["group_id"] == str(sc_group.id)
    assert court["today"]["for_date"] == today.isoformat() and len(court["today"]["lists"]) == 7
    assert court["next"]["for_date"] == tomorrow.isoformat() and court["next"]["lists"][-1]["label"] == "Weekly list"

    alld = await member("alld@example.com", "Adv. Tripathi", headline="Advocate, Allahabad High Court", city="Prayagraj")
    court = (await client.get(f"{API}/brief", headers=alld)).json()["court"]
    assert court["name"] == "Allahabad High Court" and court["ecourts_url"].startswith("https://hcservices.ecourts.gov.in/")
    assert court["today"]["lists"] == [{"label": "Combined cause list, Allahabad (court-wise)",
                                        "url": "https://www.allahabadhighcourt.in/causelist/indexA.html"}]

    kerala = await member("kochi@example.com", "Adv. Nair", courts=["Kerala High Court"])
    court = (await client.get(f"{API}/brief", headers=kerala)).json()["court"]
    assert court["name"] == "Kerala High Court" and not court["fetches"] and court["today"] is None

    generic = await member("family@example.com", "Adv. Roy", courts=["Family Court", "High Court"])
    assert (await client.get(f"{API}/brief", headers=generic)).json()["court"] is None
