"""Public, indexable cause-list pages: vidhisangh.com/courts/<slug>/cause-list/ (and /sitemap-courts.xml).

Built 17 November 2026 to give the court desk a public face: "supreme court
cause list today" and "allahabad high court cause list" are searched every
working day by exactly the advocates VidhiSangh is for. The page shows the
lists the court published for today and the next listing day (links to the
court's own PDFs or pages, as read by ``courts/fetch.py``), the court's public
details, and a one-line invitation to join. Rendered on request (the lists
change twice a day) and cached for fifteen minutes, like the judgment pages.

Nothing on these pages concerns a member or a party: only the court's index.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape

from fastapi import APIRouter, Depends, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_auth_session
from app.modules.courts.models import CourtCauseList
from app.modules.courts.registry import BY_SLUG, COURTS, ECOURTS_HC, Court
from app.modules.courts.service import IST, SUPREME_COURT, today_ist
from app.modules.research.public_pages import SITE, _page, not_found_page, whatsapp_url

router = APIRouter(tags=["Public cause lists"], include_in_schema=False)
JOIN = "/auth/register?utm_source=cause_lists"

SC_LIST_TYPES = (
    ("Advance list", "the matters expected over the coming days, published ahead"),
    ("Court number-wise", "today's board arranged by court room"),
    ("Judge-wise", "the same board arranged by bench"),
    ("Chamber", "matters before the Chamber Judge"),
    ("Single judge", "matters before a single judge"),
    ("Review and curative", "review and curative petitions, heard in chambers"),
    ("Registrar", "matters before the Registrar (defects, office reports)"),
    ("Weekly list", "the week's regular hearing matters"),
    ("Main / supplementary", "the first list of the day, and the additions published after it"),
)


def cause_list_path(court: Court) -> str:
    return f"/courts/{court.slug}/cause-list/"


def _when(for_date: date, today: date) -> str:
    if for_date == today:
        return "today"
    if for_date == today + timedelta(days=1):
        return "tomorrow"
    return for_date.strftime("%A")


def _links(row: CourtCauseList) -> str:
    items = "".join(
        f'<li><a href="{escape(l["url"])}" target="_blank" rel="noopener">{escape(l["label"])}</a></li>'
        for l in row.lists
    )
    return f'<ul class="list">{items}</ul>'


def _ist(dt: datetime) -> str:
    return dt.astimezone(IST).strftime("%d/%m/%Y, %I:%M %p").lstrip("0")


async def _rows(session: AsyncSession, court: Court, today: date) -> tuple[CourtCauseList | None, CourtCauseList | None]:
    rows = (await session.scalars(
        select(CourtCauseList).where(CourtCauseList.court_slug == court.slug, CourtCauseList.for_date >= today)
        .order_by(CourtCauseList.for_date).limit(2)
    )).all()
    return (next((r for r in rows if r.for_date == today), None), next((r for r in rows if r.for_date > today), None))


def _details(court: Court) -> str:
    ecourts = (f'<li><a href="{ECOURTS_HC}" target="_blank" rel="noopener">eCourts High Court services</a> '
               f'(cause lists and case status for every High Court)</li>' if court.slug != SUPREME_COURT else "")
    return (f'<h2>Where the {escape(court.name)} publishes its lists</h2><ul class="list">'
            f'<li><a href="{escape(court.cause_list_url)}" target="_blank" rel="noopener">Cause lists on the court\'s website</a></li>'
            f'<li><a href="{escape(court.website)}" target="_blank" rel="noopener">{escape(court.name)} website</a></li>'
            f'{ecourts}</ul>')


def _cta(court: Court) -> str:
    return (f'<aside class="cta"><div><strong>Members of the {escape(court.name)} get this every morning</strong>'
            f'<span>The day\'s cause lists in the VidhiSangh Daily brief and in the {escape(court.name)} group, '
            f'with colleagues from your own bar. Free for India\'s legal fraternity.</span></div>'
            f'<div class="cta-buttons"><a class="primary" href="{JOIN}" rel="nofollow">Join VidhiSangh free</a></div></aside>')


@router.get("/courts/", response_class=HTMLResponse)
async def courts_index(session: AsyncSession = Depends(get_auth_session)) -> Response:
    today = today_ist()
    with_lists = set(await session.scalars(
        select(CourtCauseList.court_slug).where(CourtCauseList.for_date == today)))
    items = "".join(
        f'<li><a href="{cause_list_path(c)}">{escape(c.name)} cause list</a>'
        f'{" <span class=\"tag\">today\'s lists</span>" if c.slug in with_lists else ""}</li>'
        for c in COURTS
    )
    body = (f"<h1>Cause lists: Supreme Court and every High Court</h1>"
            f"<p class=\"lede\">Where each court publishes its daily cause list, and the lists published for "
            f"{today.strftime('%A %d/%m/%Y')} where VidhiSangh reads the court's index.</p>"
            f'<ul class="list">{items}</ul>{_cta(BY_SLUG[SUPREME_COURT])}')
    return _page(title="Cause lists of the Supreme Court and High Courts of India | VidhiSangh",
                 description="Daily cause lists of the Supreme Court of India and every High Court: where each court "
                             "publishes them, and the lists out for today.",
                 path="/courts/", body=body,
                 json_ld={"@context": "https://schema.org", "@type": "CollectionPage",
                          "name": "Cause lists of the Supreme Court and High Courts of India", "url": f"{SITE}/courts/"})


@router.get("/courts/{slug}/", response_class=HTMLResponse)
async def court_redirect(slug: str) -> Response:
    if slug not in BY_SLUG:
        return not_found_page("court")
    return RedirectResponse(cause_list_path(BY_SLUG[slug]), status_code=301)


@router.get("/courts/{slug}/cause-list/", response_class=HTMLResponse)
async def cause_list_page(slug: str, session: AsyncSession = Depends(get_auth_session)) -> Response:
    court = BY_SLUG.get(slug)
    if court is None:
        return not_found_page("court")
    today = today_ist()
    today_row, next_row = await _rows(session, court, today)
    day_text = today.strftime("%A %d/%m/%Y")
    path = cause_list_path(court)

    if today_row:
        today_html = (f"<h2>Cause lists for today, {day_text}</h2>{_links(today_row)}"
                      f"<p class=\"small\">Read from the court's index at {_ist(today_row.fetched_at)} IST. "
                      f"Supplementary lists appear during the day; open the court's page for the latest.</p>")
    elif court.fetcher:
        today_html = (f"<h2>Cause lists for today, {day_text}</h2>"
                      f"<p>No list is published for today yet, or the court is not sitting. "
                      f"The lists below are read from the court's index twice a day.</p>")
    else:
        today_html = (f"<h2>Cause list for {day_text}</h2>"
                      f"<p>The {escape(court.name)} publishes its daily cause list on its own website (links below). "
                      f"VidhiSangh does not read this court's index yet.</p>")
    next_html = (f"<h2>Cause lists for {_when(next_row.for_date, today)}, {next_row.for_date.strftime('%A %d/%m/%Y')}</h2>"
                 f"{_links(next_row)}") if next_row else ""
    types_html = ("<h2>What the Supreme Court's lists mean</h2><dl class=\"types\">" + "".join(
        f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in SC_LIST_TYPES) + "</dl>") if court.slug == SUPREME_COURT else ""
    share = whatsapp_url(f"{court.name} cause list, {day_text}", path)
    body = (f"<p class=\"crumbs\"><a href=\"/courts/\">Cause lists</a> › {escape(court.name)}</p>"
            f"<h1>{escape(court.name)} cause list, {day_text}</h1>"
            f"<p class=\"lede\">The lists the court has published, linked to the court's own PDFs and pages. "
            f"No case is looked up here; open a list to find a matter.</p>"
            f"{today_html}{next_html}{_details(court)}{types_html}"
            f"<p class=\"actions\"><a class=\"ghost\" href=\"{share}\" rel=\"nofollow\">Share on WhatsApp</a></p>"
            f"{_cta(court)}")
    lists_today = len(today_row.lists) if today_row else 0
    description = (f"{court.name} cause list for {day_text}: "
                   + (f"{lists_today} lists published, linked to the court's PDFs" if today_row
                      else "where the court publishes its daily list")
                   + ". Updated twice a day on VidhiSangh.")
    modified = (today_row or next_row).fetched_at if (today_row or next_row) else None
    json_ld = {"@context": "https://schema.org", "@type": "WebPage",
               "name": f"{court.name} cause list, {day_text}", "url": f"{SITE}{path}",
               "about": {"@type": "GovernmentOrganization", "name": court.name, "url": court.website},
               **({"dateModified": modified.isoformat()} if modified else {})}
    return _page(title=f"{court.name} cause list today, {day_text} | VidhiSangh",
                 description=description, path=path, body=body, json_ld=json_ld)


@router.get("/sitemap-courts.xml")
async def courts_sitemap(session: AsyncSession = Depends(get_auth_session)) -> Response:
    latest = dict((await session.execute(
        select(CourtCauseList.court_slug, func.max(CourtCauseList.fetched_at)).group_by(CourtCauseList.court_slug)
    )).all())
    entries = [f"<url><loc>{SITE}/courts/</loc><changefreq>daily</changefreq></url>"]
    for c in COURTS:
        mod = latest.get(c.slug)
        lastmod = f"<lastmod>{mod.astimezone(IST).date().isoformat()}</lastmod>" if mod else ""
        entries.append(f"<url><loc>{SITE}{cause_list_path(c)}</loc>{lastmod}<changefreq>daily</changefreq></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(entries) + "\n</urlset>\n")
    return Response(xml, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})
