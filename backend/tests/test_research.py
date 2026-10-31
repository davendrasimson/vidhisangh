"""Legal research tests — shared corpus, search/filters, citation graph."""

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


async def _add(client: AsyncClient, h: dict, **overrides) -> dict:
    body = {
        "case_name": "Kesavananda Bharati v. State of Kerala",
        "citation": "(1973) 4 SCC 225",
        "court": "Supreme Court of India",
        "court_level": "supreme_court",
        "judges": ["Sikri CJ"],
        "judgment_date": "1973-04-24",
        "acts": ["Constitution of India"],
        "sections": ["Article 368"],
        "keywords": ["basic structure"],
        "headnote": "The basic structure doctrine limits amending power.",
        "outcome": "Petition partly allowed",
    }
    body.update(overrides)
    resp = await client.post(f"{API}/research/judgments", headers=h, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_add_search_and_filters(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Research LLP", "res@firm.co", strong_password)
    sc = await _add(client, h)
    await _add(
        client, h,
        case_name="ABC Arbitration Ltd v. XYZ",
        citation="(2021) 5 SCC 1",
        court="Delhi High Court",
        court_level="high_court",
        judges=["Rao J"],
        judgment_date="2021-03-10",
        acts=["Arbitration and Conciliation Act, 1996"],
        keywords=["arbitration", "section 34"],
        headnote="Scope of interference under section 34.",
    )

    # Duplicate citation rejected.
    dup = await client.post(f"{API}/research/judgments", headers=h, json={
        "case_name": "Dup", "citation": "(1973) 4 SCC 225", "court": "SC"})
    assert dup.status_code == 409

    # Keyword search hits case name / keywords / headnote. Results come back as
    # a page ({items, total, …}) since 0036, so the list is under "items".
    hits = (await client.get(f"{API}/research/judgments?q=basic structure", headers=h)).json()
    assert any(j["id"] == sc["id"] for j in hits["items"])
    arb = (await client.get(f"{API}/research/judgments?q=arbitration", headers=h)).json()
    assert arb["total"] == 1 and arb["items"][0]["court_level"] == "high_court"

    # Filters.
    sc_only = (await client.get(f"{API}/research/judgments?court_level=supreme_court", headers=h)).json()
    assert [j["id"] for j in sc_only["items"]] == [sc["id"]]
    by_judge = (await client.get(f"{API}/research/judgments?judge=Rao", headers=h)).json()
    assert by_judge["total"] == 1
    by_act = (await client.get(f"{API}/research/judgments?act=Arbitration", headers=h)).json()
    assert by_act["total"] == 1
    by_year = (await client.get(f"{API}/research/judgments?year_from=2020&year_to=2022", headers=h)).json()
    assert by_year["total"] == 1


async def test_citation_graph(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Cite LLP", "cite@firm.co", strong_password)
    landmark = await _add(client, h)
    recent = await _add(
        client, h, case_name="Recent Case", citation="(2022) 1 SCC 100", court_level="supreme_court"
    )

    # Recent case follows the landmark, and refers to an external cite.
    add = await client.post(
        f"{API}/research/judgments/{recent['id']}/citations", headers=h,
        json={"to_judgment_id": landmark["id"], "relationship_type": "followed"},
    )
    assert add.status_code == 201
    await client.post(
        f"{API}/research/judgments/{recent['id']}/citations", headers=h,
        json={"external_citation": "AIR 1950 SC 27", "relationship_type": "referred"},
    )

    # The recent case cites the landmark (+ external); the landmark is cited-by the recent case.
    recent_graph = (await client.get(f"{API}/research/judgments/{recent['id']}/citations", headers=h)).json()
    assert {e["citation"] for e in recent_graph["cites"]} == {"(1973) 4 SCC 225", "AIR 1950 SC 27"}
    assert recent_graph["cited_by"] == []

    landmark_graph = (await client.get(f"{API}/research/judgments/{landmark['id']}/citations", headers=h)).json()
    assert len(landmark_graph["cited_by"]) == 1
    assert landmark_graph["cited_by"][0]["case_name"] == "Recent Case"
    assert landmark_graph["cited_by"][0]["relationship_type"] == "followed"


async def test_corpus_is_shared_across_tenants(client: AsyncClient, strong_password: str) -> None:
    a_h, _ = await _user(client, "Firm A", "ra@firma.co", strong_password)
    b_h, _ = await _user(client, "Firm B", "rb@firmb.co", strong_password)
    added = await _add(client, a_h)

    # The research library is a shared corpus — firm B sees firm A's judgment.
    seen = (await client.get(f"{API}/research/judgments?q=Kesavananda", headers=b_h)).json()
    assert any(j["id"] == added["id"] for j in seen["items"])


async def test_citation_less_records_are_searchable(
    client: AsyncClient, session_factory, strong_password: str
) -> None:
    """High Court order records have no citation (0034).

    They must round-trip through the read schemas — a `citation: str` there
    turned every search over the High Court corpus into a 500.
    """
    from sqlalchemy import select

    from app.modules.identity.models import User
    from app.modules.research.models import CourtLevel, Judgment

    headers, _ = await _user(client, "Orders LLP", "orders@firm.co", strong_password)

    async with session_factory() as session:
        user_id = (await session.execute(select(User.id).limit(1))).scalar_one()
        session.add(
            Judgment(
                case_name="CRM-M/35060/2024 of DEEPAK DUHAN Vs STATE OF HARYANA",
                citation=None,                       # the point of the test
                cnr_number="PHHC010927252024",
                source_ref="3_22:PHHC010927252024:2024-07-24",
                court="High Court of Punjab and Haryana",
                court_level=CourtLevel.HIGH_COURT,
                added_by=user_id,
            )
        )
        await session.commit()

    found = await client.get(
        f"{API}/research/judgments", params={"q": "DEEPAK DUHAN"}, headers=headers
    )
    assert found.status_code == 200, found.text
    items = found.json()
    items = items if isinstance(items, list) else items.get("items", [])
    assert items, "a citation-less judgment must be findable"
    assert items[0]["citation"] is None
    assert items[0]["cnr_number"] == "PHHC010927252024"

    detail = await client.get(
        f"{API}/research/judgments/{items[0]['id']}", headers=headers
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["citation"] is None


# ─── Structured search: page shape, facets, filters (0036) ──────────
async def test_search_returns_a_page_with_total_and_facets_agree(
    client: AsyncClient, strong_password: str
) -> None:
    h, _ = await _user(client, "Facets LLP", "facets@firm.co", strong_password)
    await _add(client, h, case_name="Alpha v. State of Punjab", citation="(2020) 1 SCC 1",
               court="Supreme Court of India", judgment_date="2020-03-01")
    await _add(client, h, case_name="Beta v. State of Punjab", citation="(2021) 2 SCC 2",
               court="Supreme Court of India", judgment_date="2021-03-01")
    await _add(client, h, case_name="Gamma v. Union of India", citation="(2021) 3 SCC 3",
               court="Delhi High Court", court_level="high_court", judgment_date="2021-06-01")

    page = await client.get(f"{API}/research/judgments", params={"q": "Punjab"}, headers=h)
    assert page.status_code == 200, page.text
    body = page.json()
    assert {"items", "total", "page", "size"} <= body.keys()
    assert body["total"] == 2 and len(body["items"]) == 2
    assert all("judge_names" in i and "cause_title" in i for i in body["items"])

    facets = await client.get(
        f"{API}/research/judgments/facets", params={"q": "Punjab"}, headers=h
    )
    assert facets.status_code == 200, facets.text
    fc = facets.json()
    # The sidebar must describe exactly the result set the user is looking at.
    assert fc["total"] == body["total"]
    assert fc["courts"] == [{"value": "Supreme Court of India", "count": 2}]
    assert sorted(b["value"] for b in fc["years"]) == ["2020", "2021"]


async def test_facets_route_is_not_swallowed_by_the_id_route(
    client: AsyncClient, strong_password: str
) -> None:
    """`/judgments/facets` must resolve before `/judgments/{judgment_id}`."""
    h, _ = await _user(client, "Route LLP", "route@firm.co", strong_password)
    resp = await client.get(f"{API}/research/judgments/facets", headers=h)
    assert resp.status_code == 200, resp.text          # not 422 "invalid uuid"
    assert resp.json()["total"] == 0


async def test_court_and_year_filters_narrow_results(
    client: AsyncClient, strong_password: str
) -> None:
    h, _ = await _user(client, "Narrow LLP", "narrow@firm.co", strong_password)
    await _add(client, h, case_name="One v. Two", citation="(2019) 9 SCC 9",
               court="Supreme Court of India", judgment_date="2019-01-01")
    await _add(client, h, case_name="Three v. Four", citation="(2022) 4 SCC 4",
               court="Bombay High Court", court_level="high_court", judgment_date="2022-01-01")

    by_court = await client.get(
        f"{API}/research/judgments", params={"court": "Bombay High Court"}, headers=h
    )
    assert [i["case_name"] for i in by_court.json()["items"]] == ["Three v. Four"]

    by_year = await client.get(
        f"{API}/research/judgments", params={"year_from": 2019, "year_to": 2019}, headers=h
    )
    assert [i["case_name"] for i in by_year.json()["items"]] == ["One v. Two"]


async def test_page_reports_count_kind_and_ranking(
    client: AsyncClient, strong_password: str
) -> None:
    """Small sets are counted exactly and ranked; the flags say so."""
    h, _ = await _user(client, "Flags LLP", "flags@firm.co", strong_password)
    await _add(client, h, case_name="Flag Case v. State", citation="(2018) 1 SCC 18")
    body = (await client.get(f"{API}/research/judgments", params={"q": "Flag"}, headers=h)).json()
    assert body["total"] == 1
    assert body["total_is_estimate"] is False
    assert body["ranked"] is True


async def test_registry_placeholders_are_not_treated_as_judges() -> None:
    """Status text in the judge field must not become a facet value."""
    from app.modules.research.normalise import normalise_judges

    assert normalise_judges(["Case is not allocated to court."]) is None
    assert normalise_judges(["HON'BLE MR. JUSTICE A.K. SIKRI"]) == "A.K. Sikri"
    # A real judge alongside a placeholder keeps only the judge.
    assert normalise_judges(["Not Allocated", "MR. JUSTICE RAJIV SHARMA"]) == "Rajiv Sharma"


async def test_parties_and_counsel_parse_from_each_registry_format() -> None:
    """The three High Court registries print counsel differently; all three parse."""
    from app.modules.research.normalise import (
        advocate_text, parse_counsel, parse_neutral_citation, split_parties,
    )

    assert split_parties("PRAMOD SINGH Vs RAVI KUMAR & ORS.") == ("PRAMOD SINGH", "RAVI KUMAR & ORS")
    assert split_parties("Kesavananda Bharati v. State of Kerala") == ("Kesavananda Bharati", "State of Kerala")
    assert split_parties("Untitled") == (None, None)

    delhi = ("X ..... Petitioner Through: Mr. Sanjeev Sagar and Ms. Nazia Parveen, Advocates. "
             "versus Y ..... Respondents Through: Mr. Anurag Ahluwalia, CGSC with Mr. Abhigyan "
             "Siddhant, Adv. for UOI. Mr. Rahul Sharma, Sr. Advocate with Ms. Riya, Advocate for R-2 "
             "CORAM: HON'BLE MR. JUSTICE ...")
    assert parse_counsel(delhi) == (
        ["Sanjeev Sagar", "Nazia Parveen"],
        ["Anurag Ahluwalia", "Abhigyan Siddhant", "Rahul Sharma", "Riya"],
    )
    # A parenthetical ("(thru VC)") is not a second advocate.
    assert parse_counsel("A .....Petitioner Through: Mr. Brijesh Kumar Singh, Adv. (thru VC) versus B "
                         ".....Respondents Through: Mr. Shafiq Khan, Adv. CORAM:") == (
        ["Brijesh Kumar Singh"], ["Shafiq Khan"])
    # Unspaced honorific; absent petitioner counsel ("None") is not a name.
    assert parse_counsel("A .....Appellant Through: None versus B .....Respondents Through: "
                         "Mr.A.K. Soni, Advocate for R-3 CORAM: X") == ([], ["A.K. Soni"])

    allahabad = ("No. - 2023:AHC:117096 Court No. - 38 Case :- WRIT - A No. - 9342 of 2023 "
                 "Petitioner :- Ramakant Yadav Respondent :- Union Of India And 4 Others "
                 "Counsel for Petitioner :- Sanjay Singh,Prabhakar Dwivedi "
                 "Counsel for Respondent :- A.S.G.I.,Santosh Kumar Mishra Hon'ble Saurabh Srivastava,J. 1.")
    assert parse_counsel(allahabad) == (["Sanjay Singh", "Prabhakar Dwivedi"], ["Santosh Kumar Mishra"])
    assert parse_neutral_citation(allahabad) == "2023:AHC:117096"

    ph = ("... CORAM: HON'BLE MR. JUSTICE NAMIT KUMAR Present: Mr. Gurmeet Singh, Advocate for the "
          "petitioners. Mr. Rana Harjasdeep Singh, DAG, Punjab for the respondents. NAMIT KUMAR, J. 1.")
    assert parse_counsel(ph) == (["Gurmeet Singh"], ["Rana Harjasdeep Singh"])

    # Registry junk (an e-sign footer) yields nothing rather than garbage.
    assert parse_counsel("mohit@example.com 2024-04-24T18:10:46+0530 MOHIT I attest") == ([], [])
    # Ordinary prose containing "through" (a Supreme Court disposal) is not counsel.
    assert parse_counsel("Sripati Singh (since deceased) through his son Gaurav Singh appealed; "
                         "when his father had come forward to see what had happened") == ([], [])
    assert advocate_text(["A"], ["B", "A"]) == "A | B"


async def test_case_view_groups_orders_by_cnr(client: AsyncClient, strong_password: str) -> None:
    """Two orders on one CNR become one case: parties, counsel union, timeline."""
    h, _ = await _user(client, "Case LLP", "case@firm.co", strong_password)
    cnr = "DLHC010189442023"
    first = await _add(
        client, h,
        case_name="MAC.APP./263/2023 of PRAMOD SINGH Vs RAVI KUMAR & ORS.",
        citation="ORD-2024-07-31", court="High Court of Delhi", court_level="high_court",
        judges=["HON'BLE MR. JUSTICE CHANDRA DHARI SINGH"], judgment_date="2024-07-31",
        cnr_number=cnr, acts=[], sections=[], keywords=[], outcome=None,
        headnote=("PRAMOD SINGH .....Appellant Through: None versus RAVI KUMAR & ORS. "
                  ".....Respondents Through: Mr.A.K. Soni, Advocate for R-3 CORAM: X O R D E R"),
    )
    second = await _add(
        client, h,
        case_name="MAC.APP./263/2023 of PRAMOD SINGH Vs RAVI KUMAR & ORS.",
        citation="ORD-2025-01-15", court="High Court of Delhi", court_level="high_court",
        judges=["HON'BLE MR. JUSTICE CHANDRA DHARI SINGH"], judgment_date="2025-01-15",
        cnr_number=cnr.lower(), acts=[], sections=[], keywords=[], outcome="Disposed of",
        headnote=("PRAMOD SINGH .....Appellant Through: Ms. Riya, Advocate versus RAVI KUMAR "
                  ".....Respondents Through: Mr. A.K. Soni, Advocate CORAM: X O R D E R"),
    )
    # The order record itself carries the derived parties and counsel.
    assert first["petitioner"] == "PRAMOD SINGH"
    assert first["respondent"] == "RAVI KUMAR & ORS"
    assert first["respondent_advocates"] == ["A.K. Soni"]
    assert second["cnr_number"] == cnr  # normalised to upper case

    case = (await client.get(f"{API}/research/cases/{cnr.lower()}", headers=h))
    assert case.status_code == 200, case.text
    body = case.json()
    assert body["cnr_number"] == cnr
    assert body["case_type"] == "MAC.APP." and body["case_number"] == "263" and body["case_year"] == 2023
    assert [o["id"] for o in body["orders"]] == [first["id"], second["id"]]  # oldest first
    assert body["first_order_on"] == "2024-07-31" and body["latest_order_on"] == "2025-01-15"
    assert body["latest_outcome"] == "Disposed of"
    assert body["petitioner_advocates"] == ["Riya"]           # union across orders
    assert body["respondent_advocates"] == ["A.K. Soni"]      # de-duplicated
    assert body["judge_names"] == ["Chandra Dhari Singh"]

    unknown = await client.get(f"{API}/research/cases/XXXX000000000000", headers=h)
    assert unknown.status_code == 404

    # Search by advocate, and each result knows how many orders its case has.
    page = (await client.get(f"{API}/research/judgments", headers=h,
                             params={"advocate": "soni"})).json()
    assert page["total"] == 2
    assert {item["order_count"] for item in page["items"]} == {2}
    facets = (await client.get(f"{API}/research/judgments/facets", headers=h,
                               params={"advocate": "soni"})).json()
    # Postgres facets per advocate (unnest); the SQLite fallback groups the
    # whole "A | B" string — either way both names must be represented.
    values = " || ".join(b["value"] for b in facets["advocates"])
    assert "A.K. Soni" in values and "Riya" in values


async def test_full_text_is_searchable_and_returned(client: AsyncClient, strong_password: str) -> None:
    """A phrase that appears only in the order's full text finds the order."""
    h, _ = await _user(client, "Text LLP", "text@firm.co", strong_password)
    j = await _add(
        client, h,
        case_name="CRM-M/1/2024 of A Vs B", citation="ORD-FT-1", court="High Court of Punjab and Haryana",
        court_level="high_court", judges=[], acts=[], sections=[], keywords=[], headnote=None,
        full_text="ORDER\n\nThe petitioner seeks anticipatory bail under xyzzyphrase of the Code.",
    )
    page = (await client.get(f"{API}/research/judgments", headers=h, params={"q": "xyzzyphrase"})).json()
    assert [i["id"] for i in page["items"]] == [j["id"]]
    detail = (await client.get(f"{API}/research/judgments/{j['id']}", headers=h)).json()
    assert "xyzzyphrase" in detail["full_text"] and detail["text_extracted_at"] is not None


async def test_acts_sections_and_sc_body_parsers() -> None:
    from app.modules.research.normalise import parse_acts_sections, parse_sc_counsel, sc_judgment_body

    text = ("The petitioner seeks anticipatory bail under Section 438 of the Code of Criminal Procedure, 1973 "
            "for offences under Sections 302, 34 IPC. Article 226 of the Constitution of India is invoked. "
            "Section 12(1) of the Arbitration and Conciliation Act, 1996 is also cited, as is the Act. "
            "The Kerala Forest Act applies; Section 12A of the Kerala Forest Act, 1961 in particular.")
    acts, sections = parse_acts_sections(text)
    assert "Code of Criminal Procedure, 1973" in acts and "Indian Penal Code, 1860" in acts
    assert "Constitution of India" in acts and "Arbitration and Conciliation Act, 1996" in acts
    assert "Kerala Forest Act, 1961" in acts and "Kerala Forest Act" not in acts   # year variants merged
    assert not any(a in ("Act", "Act, 1996", "Conciliation Act, 1996") for a in acts)  # no junk
    assert "Section 438 (Code of Criminal Procedure, 1973)" in sections
    assert "Section 302 (Indian Penal Code, 1860)" in sections and "Section 34 (Indian Penal Code, 1860)" in sections
    assert "Article 226 (Constitution of India)" in sections
    assert "Section 12A (Kerala Forest Act, 1961)" in sections

    # SCR volume: everything before the jurisdiction line is the reporter's headnote — dropped.
    scr = ("[2025] 12 S.C.R. 498 Sithara v. Sai Ram Headnotes Motor Vehicles Act – s.166 – Held: … "
           "Case Arising From CIVIL APPELLATE JURISDICTION: Civil Appeal No. 14718 of 2025 "
           "Appearances for Parties Advs. for the Appellant: Shekhar G Devasa, Manish Tiwari, Sr. Advs., "
           "Thashmitha\nMuthanna. Advs. for the Respondent: Kshitij Mittal, Anand Sukumar. "
           "Judgment / Order of the Supreme Court Order Vikram Nath, J. 1. The instant appeal …")
    body = sc_judgment_body(scr)
    assert body.startswith("Case Arising From") and "Headnotes" not in body
    assert parse_sc_counsel(body) == (["Shekhar G Devasa", "Manish Tiwari", "Thashmitha Muthanna"],
                                      ["Kshitij Mittal", "Anand Sukumar"])
    # Older layout: "X and Y for the Appellant." after the From-the-judgment sentence.
    old = ("CIVIL APPELLATE JURISDICTION : Civil Appeal No. 587 of 2010. From the Judgment & Order dated "
           "06.02.2009 of the High Court of Punjab in LPA No. 4 of 2008. H 514 SUPREME COURT REPORTS [2011] 11 "
           "S.C.R A S.K. Dholakia, S.K. Chachra and Dr. Kailash Chand for the Appellant. B Bhaskar Bhattacharjee "
           "for the Respondent. The Judgment of the Court was delivered by H.L. GOKHALE J. 1. This appeal …")
    assert parse_sc_counsel(old) == (["S.K. Dholakia", "S.K. Chachra", "Kailash Chand"], ["Bhaskar Bhattacharjee"])
    # No boundary found -> nothing stored (never the headnote).
    assert sc_judgment_body("[2010] 1 S.C.R. 1 Headnote only, no jurisdiction line") is None


async def test_counsel_parse_uttarakhand_and_delhi_judgment_formats() -> None:
    """Uttarakhand's "Presence:-" judgments and order sheets, and Delhi's judgment header
    ("For the Petitioner : …") — the formats behind 232,000 High Court texts without counsel."""
    from app.modules.research.normalise import parse_counsel

    presence = ("2026:UHC:3285\n1\nHIGH COURT OF UTTARAKHAND AT NAINITAL\n1. Writ Petition Misc. Single No.1164 of 2026\n"
                "Rahul Joshi --Petitioner\nVersus\nG.B. Pant University Of Agriculture And Technology\nPantnagar and Another --Respondents\n"
                "----------\nPresence:-\nMr. D.C.S. Rawat, Mr. Hemant Singh Mahra and Mr.\nKetan Joshi, learned counsel for petitioner(s).\n"
                "Mr. S.S. Lingwal, learned counsel for respondents-\nUniversity, through V.C.\n\nHon’ble Pankaj Purohit, J. (Oral)\n\nSince all the writ petitions")
    assert parse_counsel(presence) == (["D.C.S. Rawat", "Hemant Singh Mahra", "Ketan Joshi"], ["S.S. Lingwal"])

    sheet = ("SL.\nNo Date\nCOURT’S OR JUDGES’S ORDERS\n42\n\nBCA No. 21 of 2025\nHon’ble Ravindra Maithani, J.\n"
             "Ms. Stuti Pandey , Advocate for the\napplicant.\nMr. Rakesh Negi , Brief Holder for the\nState.\n"
             "Learned counsel for the applicant submits\nthat proclamation has already been issued")
    assert parse_counsel(sheet) == (["Stuti Pandey"], ["Rakesh Negi"])

    numbered = ("2026:UHC:3202\nWPSS/ 1134 / 2022\nHon’ble Manoj Kumar Tiwari, J.\n\nMr. M.C. Kandpal, Senior Advocate, assisted\n"
                "by Mr. Devesh Kandpal, Mr. Vinod Tiwari, Mr. Atul\nTripathi, Mr. Vinay Bhushan Pathak and Mr.\nDevendra Singh Negi, Advocates for the\n"
                "petitioners.\n2. Mr. Sushil Vashistha, Standing Counsel for\nthe State of Uttarakhand.\n3. Since common questions of law and fact\nare involved")
    assert parse_counsel(numbered) == (
        ["M.C. Kandpal", "Devesh Kandpal", "Vinod Tiwari", "Atul Tripathi", "Vinay Bhushan Pathak", "Devendra Singh Negi"],
        ["Sushil Vashistha"],
    )

    judgment = ("* IN THE HIGH COURT OF DELHI AT NEW DELHI\n+ W.P.(C) 15970/2023\nM/S HUAWEI TELECOMMUNICATIONS\n(INDIA) COMPANY PVT. LTD. .....Petitioner\n"
                "versus\nASSISTANT COMMISSIONER OF INCOME\nTAX, CENTRAL CIRCLE-2, DELHI & ANR .....Respondents\n\nAdvocates who appeared in this case\n\n"
                "For the Petitioner : Mr. Arvind Datar and Mr. Tarun Gulati,\nSenior Advocates with Mr. Kishore Kunal,\nMs. Ankita Prakash and Mr. Anuj Kumar,\nAdvocates.\n\n"
                "For the Respondents : Mr. Indruj Singh Rai SSC, Mr.Sanjeev\nMenon, Mr. Rahul Singh JSCs and Mr.\nGaurav Kumar, Mr.Siddharth Burman,\nAdvocates.\n\n"
                "CORAM:\nHON'BLE MR. JUSTICE V. KAMESWAR RAO\nJUDGMENT\nFor the Petitioner : nothing after the coram counts")
    assert parse_counsel(judgment) == (
        ["Arvind Datar", "Tarun Gulati", "Kishore Kunal", "Ankita Prakash", "Anuj Kumar"],
        ["Indruj Singh Rai", "Sanjeev Menon", "Rahul Singh", "Gaurav Kumar", "Siddharth Burman"],
    )
    # An order with nobody appearing stays empty; prose "Hon'ble" lines are not appearances.
    assert parse_counsel("Through: None\nversus\nX .....Respondent\nThrough: None\nCORAM:\nHON'BLE MS. JUSTICE N\nO R D E R") == ([], [])
