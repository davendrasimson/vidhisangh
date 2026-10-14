"""Public, indexable pages for Supreme Court judgments that have an AI headnote.

Served as plain HTML at the site root (nginx proxies `/judgments/` and
`/sitemap-judgments.xml` here), so search engines and people without an account
can read them. Rendered on request rather than as static files because new
headnotes are imported every day. Only the headnote and the case details are
public; the full text stays in the app, behind "Read the full judgment".

Every page shows the AI-generated label. Pages exist only for judgments with an
AI headnote; anything else is a 404.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_auth_session
from app.modules.research.models import CourtLevel, Judgment
from app.modules.research.schemas import AI_HEADNOTE_LABEL, AiHeadnoteContent

router = APIRouter(tags=["Public judgments"], include_in_schema=False)

SITE = "https://vidhisangh.com"
JOIN = "/auth/register?utm_source=judgments"
LATEST = 30
# The bare-act stylesheet is shared; bump the query when acts.css changes
# (nginx caches .css for a year).
CSS_URL = "/acts/acts.css?v=j1"
# These pages carry their own policy: the API default (`default-src 'none'`)
# would block the stylesheet, fonts and logo.
CSP = (
    "default-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
EXTRA_CSS = """
.ai-flag { margin-top: 1.25rem; padding: .75rem 1rem; border-radius: 12px; font-size: .92rem;
  background: color-mix(in srgb, var(--gold) 22%, var(--card)); border: 1px solid color-mix(in srgb, var(--gold) 60%, var(--line)); }
.facts { margin: .75rem 0 0; color: var(--muted); font-size: .95rem; }
.hn h2 { margin: 1.4rem 0 .4rem; font-size: 1.05rem; } .hn h2:first-child { margin-top: 0; }
.hn ol, .hn ul { margin: 0; padding-left: 1.3rem; } .hn li { margin-bottom: .55rem; }
.para { color: var(--muted); font-family: Inter, system-ui, sans-serif; font-size: .82rem; white-space: nowrap; }
.prov b { display: block; }
.list { list-style: none; padding: 0; margin: 1rem 0 0; }
.list li { padding: .9rem 1rem; margin-bottom: .6rem; background: var(--card); border: 1px solid var(--line); border-radius: 14px; }
.list a { font-weight: 600; text-decoration: none; } .list p { margin: .3rem 0 0; color: var(--muted); font-size: .93rem; }
.years { display: flex; flex-wrap: wrap; gap: .5rem; margin-top: 1rem; }
.years a { padding: .4rem .9rem; border-radius: 999px; border: 1px solid var(--line); background: var(--card); text-decoration: none; }
"""


def _published():
    return (Judgment.court_level == CourtLevel.SUPREME_COURT, Judgment.ai_headnote.is_not(None))


def slug(text: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return words[:80].rstrip("-") or "judgment"


def _title(j: Judgment) -> str:
    return re.sub(r"\s+", " ", j.cause_title or j.case_name).strip()


def judgment_path(j: Judgment) -> str:
    return f"/judgments/{j.id}/{slug(_title(j))}/"


def _day(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _paras(paras: list[str]) -> str:
    if not paras:
        return ""
    mark = "¶" if len(paras) == 1 else "¶¶"
    return f' <span class="para">({mark} {escape(", ".join(paras))})</span>'


def _page(*, title: str, description: str, path: str, body: str, json_ld: dict, status: int = 200) -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="en-IN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{escape(title)}</title>
<meta name="description" content="{escape(description)}" />
<meta name="robots" content="index, follow" />
<link rel="canonical" href="{SITE}{path}" />
<meta property="og:type" content="article" />
<meta property="og:site_name" content="VidhiSangh" />
<meta property="og:title" content="{escape(title)}" />
<meta property="og:description" content="{escape(description)}" />
<meta property="og:url" content="{SITE}{path}" />
<meta property="og:image" content="{SITE}/images/landing/og-feature.png" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="theme-color" content="#215dcc" />
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<link rel="stylesheet" href="{CSS_URL}" />
<style>{EXTRA_CSS}</style>
<script type="application/ld+json">{json.dumps(json_ld, ensure_ascii=False).replace("</", "<\\/")}</script>
</head>
<body>
<header class="top">
  <a class="brand" href="/"><img src="/brand-mark.svg" alt="" width="30" height="30" /><span>VidhiSangh</span></a>
  <nav><a class="join" href="{JOIN}">Join now</a><a class="signin" href="/auth/login">Sign in</a></nav>
</header>
<main>
{body}
</main>
<footer>
  <p><a href="/judgments/">Supreme Court headnotes</a> · <a href="/acts/">Bare Acts</a> · <a href="/">VidhiSangh</a> · <a href="/privacy">Privacy</a> · <a href="/terms">Terms</a></p>
  <p>Headnotes on these pages are AI-generated from the judgment text and are not legal advice. Read the judgment itself before relying on any point.</p>
</footer>
</body>
</html>
"""
    response = HTMLResponse(html, status_code=status)
    response.headers["Content-Security-Policy"] = CSP
    response.headers["Cache-Control"] = "public, max-age=900"
    return response


def _cta(j: Judgment | None = None) -> str:
    app_link = f'<a class="ghost" href="/app/research/{j.id}">Open in the app</a>' if j else ""
    return f"""<aside class="cta">
  <div><strong>Read the full judgment free on VidhiSangh</strong>
  <span>5.9 million Supreme Court and High Court judgments, BNS, BNSS and BSA, and a professional network for India's legal fraternity.</span></div>
  <div class="cta-buttons"><a class="primary" href="{JOIN}">Join VidhiSangh free</a>{app_link}</div>
</aside>"""


def _list_item(j: Judgment) -> str:
    summary = (j.ai_headnote or {}).get("summary", "")
    facts = " · ".join(x for x in (_day(j.judgment_date), j.citation or j.neutral_citation or "") if x)
    return (f'<li><a href="{judgment_path(j)}">{escape(_title(j))}</a>'
            f'<p>{escape(facts)}</p><p>{escape(summary)}</p></li>')


@router.get("/judgments/{key}/", response_class=HTMLResponse)
async def year_or_judgment(key: str, session: AsyncSession = Depends(get_auth_session)) -> Response:
    """`/judgments/2025/` is a year; `/judgments/<id>/` redirects to the judgment's full address."""
    if key.isdigit() and len(key) == 4:
        return await _year_page(int(key), session)
    try:
        judgment_id = uuid.UUID(key)
    except ValueError:
        raise HTTPException(status_code=404) from None
    return await judgment_page(judgment_id, None, session)


@router.get("/judgments/{judgment_id}/{name}/", response_class=HTMLResponse)
async def judgment_page(
    judgment_id: uuid.UUID, name: str | None, session: AsyncSession = Depends(get_auth_session)
) -> Response:
    j = (await session.execute(select(Judgment).where(Judgment.id == judgment_id, *_published()))).scalar_one_or_none()
    if j is None:
        raise HTTPException(status_code=404)
    path = judgment_path(j)
    if name != path.split("/")[3]:
        return RedirectResponse(path, status_code=301)

    hn = AiHeadnoteContent.model_validate(j.ai_headnote)
    title = _title(j)
    cites = " · ".join(escape(c) for c in (j.citation, j.neutral_citation) if c)
    issues = "".join(f"<li>{escape(i)}</li>" for i in hn.issues)
    held = "".join(f"<li>{escape(h.point)}{_paras(h.paragraphs)}</li>" for h in hn.held)
    provisions = "".join(
        f'<li class="prov"><b>{escape(p.provision)}, {escape(p.act)}</b>{escape(p.how_applied)}{_paras(p.paragraphs)}</li>'
        for p in hn.provisions
    )
    year = j.judgment_date.year if j.judgment_date else None
    crumbs = f' › <a href="/judgments/{year}/">{year}</a>' if year else ""
    source = (f'<p class="source">Judgment PDF: <a href="{escape(j.url)}" rel="nofollow noopener" target="_blank">'
              f"Supreme Court of India, {escape(j.citation or title)}</a>.</p>") if j.url else ""
    body = f"""<nav class="crumbs" aria-label="Breadcrumb"><a href="/judgments/">Supreme Court headnotes</a>{crumbs}</nav>
<p class="eyebrow">Supreme Court of India{' · ' + _day(j.judgment_date) if j.judgment_date else ''}</p>
<h1>{escape(title)}</h1>
{f'<p class="facts">{cites}</p>' if cites else ''}
<p class="ai-flag"><strong>AI-generated headnote.</strong> {escape(AI_HEADNOTE_LABEL.split('. ', 1)[1])}
Paragraph numbers refer to the judgment.</p>
<article class="text hn">
<h2>Summary</h2><p>{escape(hn.summary)}</p>
<h2>Issues</h2><ol>{issues}</ol>
{f'<h2>Provisions considered</h2><ul>{provisions}</ul>' if provisions else ''}
<h2>Held</h2><ul>{held}</ul>
<h2>Result</h2><p>{escape(hn.result)}</p>
</article>
{_cta(j)}
{source}"""
    breadcrumbs = [{"@type": "ListItem", "position": 1, "name": "Supreme Court headnotes", "item": f"{SITE}/judgments/"}]
    if year:
        breadcrumbs.append({"@type": "ListItem", "position": 2, "name": str(year), "item": f"{SITE}/judgments/{year}/"})
    json_ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "Article", "headline": title[:110], "description": hn.summary, "inLanguage": "en-IN",
         "url": f"{SITE}{path}", "about": [{"@type": "Legislation", "name": f"{p.provision}, {p.act}"} for p in hn.provisions],
         "datePublished": j.ai_headnote_generated_at.date().isoformat() if j.ai_headnote_generated_at else None,
         "publisher": {"@type": "Organization", "name": "VidhiSangh", "url": SITE}},
        {"@type": "BreadcrumbList", "itemListElement": breadcrumbs},
    ]}
    description = hn.summary if len(hn.summary) <= 160 else hn.summary[:157].rsplit(" ", 1)[0] + "…"
    return _page(title=f"{title} ({_day(j.judgment_date)}) — Supreme Court headnote | VidhiSangh",
                 description=description, path=path, body=body, json_ld=json_ld)


async def _year_counts(session: AsyncSession) -> list[tuple[int, int]]:
    year = extract("year", Judgment.judgment_date)
    rows = await session.execute(
        select(year, func.count()).where(*_published(), Judgment.judgment_date.is_not(None))
        .group_by(year).order_by(year.desc())
    )
    return [(int(y), n) for y, n in rows.all()]


@router.get("/judgments/", response_class=HTMLResponse)
async def judgments_index(session: AsyncSession = Depends(get_auth_session)) -> Response:
    latest = (await session.execute(
        select(Judgment).where(*_published())
        .order_by(Judgment.judgment_date.desc().nulls_last(), Judgment.id).limit(LATEST)
    )).scalars().all()
    years = "".join(f'<a href="/judgments/{y}/">{y} <small>({n})</small></a>' for y, n in await _year_counts(session))
    body = f"""<p class="eyebrow">Supreme Court of India</p>
<h1>Supreme Court judgments, in short</h1>
<p class="lede">Headnotes of recent Supreme Court judgments: the issues, the provisions the Court applied, what it held and
the result, each point tied to the judgment's paragraph numbers. The headnotes are AI-generated; read the judgment
before relying on them.</p>
<nav class="years" aria-label="By year">{years}</nav>
{_cta()}
<h2>Latest judgments</h2>
<ul class="list">{''.join(_list_item(j) for j in latest)}</ul>"""
    json_ld = {"@context": "https://schema.org", "@type": "CollectionPage",
               "name": "Supreme Court judgment headnotes", "url": f"{SITE}/judgments/"}
    return _page(title="Supreme Court judgments with headnotes | VidhiSangh",
                 description="Short headnotes of recent Supreme Court of India judgments: issues, provisions, holdings "
                             "and result, with paragraph references. Free on VidhiSangh.",
                 path="/judgments/", body=body, json_ld=json_ld)


async def _year_page(year: int, session: AsyncSession) -> Response:
    rows = (await session.execute(
        select(Judgment).where(*_published(), extract("year", Judgment.judgment_date) == year)
        .order_by(Judgment.judgment_date.desc(), Judgment.id)
    )).scalars().all()
    if not rows:
        raise HTTPException(status_code=404)
    body = f"""<nav class="crumbs" aria-label="Breadcrumb"><a href="/judgments/">Supreme Court headnotes</a> › <span>{year}</span></nav>
<p class="eyebrow">Supreme Court of India</p>
<h1>Supreme Court judgments of {year}</h1>
<p class="lede">{len(rows)} judgments with AI-generated headnotes, newest first.</p>
<ul class="list">{''.join(_list_item(j) for j in rows)}</ul>
{_cta()}"""
    json_ld = {"@context": "https://schema.org", "@type": "CollectionPage",
               "name": f"Supreme Court judgments of {year}", "url": f"{SITE}/judgments/{year}/"}
    return _page(title=f"Supreme Court judgments of {year} with headnotes | VidhiSangh",
                 description=f"Headnotes of {len(rows)} Supreme Court of India judgments delivered in {year}: issues, "
                             "provisions, holdings and result.",
                 path=f"/judgments/{year}/", body=body, json_ld=json_ld)


@router.get("/sitemap-judgments.xml")
async def judgments_sitemap(session: AsyncSession = Depends(get_auth_session)) -> Response:
    rows = (await session.execute(
        select(Judgment.id, Judgment.case_name, Judgment.cause_title, Judgment.ai_headnote_generated_at)
        .where(*_published()).order_by(Judgment.judgment_date.desc().nulls_last(), Judgment.id)
    )).all()
    urls = [f"<url><loc>{SITE}/judgments/</loc><changefreq>daily</changefreq></url>"]
    urls += [f"<url><loc>{SITE}/judgments/{y}/</loc><changefreq>weekly</changefreq></url>"
             for y, _ in await _year_counts(session)]
    for jid, case_name, cause_title, generated in rows:
        name = slug(re.sub(r"\s+", " ", cause_title or case_name).strip())
        lastmod = f"<lastmod>{generated.date().isoformat()}</lastmod>" if generated else ""
        urls.append(f"<url><loc>{SITE}/judgments/{jid}/{name}/</loc>{lastmod}</url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n")
    return Response(xml, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})
