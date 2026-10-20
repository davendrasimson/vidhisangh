"""Public profile pages: vidhisangh.com/in/<handle>/ (and /sitemap-profiles.xml).

Only for members who switched on "Public profile page" (NetworkIdentity.public_page,
a consent separate from the in-app directory) and whose professional profile
is public. A section appears only if the member set it to "everyone" in their
profile privacy settings; contact details and judicial information never do.
The page invites the visitor to connect on VidhiSangh.
"""

from __future__ import annotations

import json
from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_auth_session
from app.modules.network.models import NetworkIdentity
from app.modules.profile.models import DEFAULT_PROFILE_GROUP_VISIBILITY, ProfessionalProfile, ProfileVisibility
from app.modules.research.public_pages import CSP, CSS_URL, SITE

router = APIRouter(tags=["Public profiles"], include_in_schema=False)
JOIN = "/auth/register?utm_source=public_profile"
CSS = """
.person { display: flex; gap: 1rem; align-items: center; margin-top: 1.25rem; }
.person .face { width: 84px; height: 84px; border-radius: 50%; object-fit: cover; flex: none; background: var(--card); border: 1px solid var(--line); }
.person .initials { display: grid; place-items: center; font: 700 1.8rem 'Source Serif 4', Georgia, serif; color: var(--brand); }
.person h1 { margin: 0; } .person p { margin: .2rem 0 0; color: var(--muted); }
.verified { color: var(--brand); font-size: .85rem; font-weight: 700; }
.chips { display: flex; flex-wrap: wrap; gap: .4rem; margin: .4rem 0 0; padding: 0; list-style: none; }
.chips li { padding: .25rem .7rem; border-radius: 999px; background: var(--card); border: 1px solid var(--line); font-size: .9rem; }
.block { margin-top: 1.25rem; } .block h2 { font-size: 1.05rem; margin: 0 0 .3rem; }
.block p { margin: .2rem 0; white-space: pre-line; }
.actions { display: flex; flex-wrap: wrap; gap: .6rem; margin: 1.25rem 0; }
.actions a { padding: .6rem 1.1rem; border-radius: 999px; font-weight: 700; text-decoration: none; border: 2px solid var(--brand); }
.actions .primary { color: #fff; background: var(--brand); } .actions .wa { color: #fff; background: #1f9d55; border-color: #1f9d55; }
"""
ROLE_LABELS = {
    "advocate": "Advocate", "senior_advocate": "Senior Advocate", "law_student": "Law Student",
    "judicial_officer": "Judicial Officer", "in_house_counsel": "Corporate / In-house Counsel",
}


def profile_url(handle: str) -> str:
    return f"{SITE}/in/{handle}/"


def _groups(profile: ProfessionalProfile | None) -> set[str]:
    if profile is None:
        return set()
    settings = {**DEFAULT_PROFILE_GROUP_VISIBILITY, **(profile.visibility_settings or {})}
    return {g for g, level in settings.items() if level == "everyone" and g not in ("contact", "judicial")}


def _list(items) -> list[str]:
    out = []
    for it in items or []:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict):
            out.append(" — ".join(str(v) for k, v in it.items() if v and k in ("degree", "institution", "name", "year", "title")))
    return [x for x in out if x]


def _chips(title: str, items: list[str]) -> str:
    return f'<section class="block"><h2>{escape(title)}</h2><ul class="chips">{"".join(f"<li>{escape(i)}</li>" for i in items)}</ul></section>' if items else ""


async def _published(session: AsyncSession, handle: str) -> tuple[NetworkIdentity, ProfessionalProfile | None] | None:
    identity = await session.scalar(select(NetworkIdentity).where(
        NetworkIdentity.public_handle == handle, NetworkIdentity.public_page.is_(True), NetworkIdentity.deleted_at.is_(None)))
    if identity is None:
        return None
    profile = await session.scalar(select(ProfessionalProfile).where(
        ProfessionalProfile.user_id == identity.user_id, ProfessionalProfile.deleted_at.is_(None)))
    if profile is not None and profile.visibility != ProfileVisibility.PUBLIC:
        return None
    return identity, profile


@router.get("/in/{handle}")
async def profile_no_slash(handle: str) -> RedirectResponse:
    return RedirectResponse(f"/in/{handle}/", status_code=301)


@router.get("/in/{handle}/", response_class=HTMLResponse)
async def public_profile(handle: str, session: AsyncSession = Depends(get_auth_session)) -> HTMLResponse:
    found = await _published(session, handle.lower())
    if found is None:
        raise HTTPException(status_code=404)
    identity, profile = found
    groups = _groups(profile)
    name = identity.display_name
    role = ROLE_LABELS.get(profile.professional_role or "", (profile.professional_role or "").replace("_", " ").title()) if profile and "professional" in groups else ""
    headline = identity.headline or (profile.headline if profile else "") or role
    place = ", ".join(x for x in ((profile.city, profile.state) if profile else ()) if x) if "location" in groups else ""
    avatar = identity.avatar_url if identity.avatar_url and identity.avatar_url.startswith("/") else None
    initials = "".join(w[0] for w in name.replace("Adv.", "").split()[:2]).upper() or "V"
    face = f'<img class="face" src="{escape(avatar)}" alt="" width="84" height="84" />' if avatar else f'<span class="face initials">{escape(initials)}</span>'

    blocks = []
    if profile and "about" in groups and profile.bio:
        blocks.append(f'<section class="block"><h2>About</h2><p>{escape(profile.bio[:3000])}</p></section>')
    if profile and "professional" in groups:
        facts = []
        if profile.designation:
            facts.append(profile.designation)
        if profile.years_of_experience:
            facts.append(f"{profile.years_of_experience} years of practice")
        if profile.bar_council and profile.year_of_enrollment:
            facts.append(f"Enrolled with the {profile.bar_council}, {profile.year_of_enrollment}")
        if facts:
            blocks.append(f'<section class="block"><h2>Practice</h2><p>{escape(" · ".join(str(f) for f in facts))}</p></section>')
        blocks += [_chips("Practice areas", _list(profile.practice_areas)), _chips("Courts", _list(profile.courts)),
                   _chips("Languages", _list(profile.languages))]
    if profile and "education" in groups:
        blocks.append(_chips("Education", _list(profile.education)))

    path = f"/in/{identity.public_handle}/"
    share = escape(f"https://wa.me/?text={_quote(f'{name} on VidhiSangh: {SITE}{path}')}")
    connect = f"/app/people/{identity.user_id}"
    body = f"""<nav class="crumbs" aria-label="Breadcrumb"><a href="/">VidhiSangh</a> › <span>Members</span></nav>
<div class="person">{face}<div><h1>{escape(name)}</h1>
<p>{escape(headline or "")}</p>{f'<p>{escape(place)}</p>' if place else ''}{'<p class="verified">✓ Verified on VidhiSangh</p>' if identity.is_verified else ''}</div></div>
{''.join(b for b in blocks if b)}
<p class="actions"><a class="primary" href="{connect}">Connect on VidhiSangh</a><a class="wa" href="{share}" rel="noopener" target="_blank">Share on WhatsApp</a></p>
<aside class="cta"><div><strong>Join {escape(name)} on VidhiSangh</strong>
<span>The free professional network for India's legal fraternity: BNS, BNSS, BSA, 5.9 million judgments and practice tools.</span></div>
<div class="cta-buttons"><a class="primary" href="{JOIN}">Join VidhiSangh free</a></div></aside>"""
    title = f"{name}{f' — {headline}' if headline else ''} | VidhiSangh"
    description = f"{name}{f', {headline}' if headline else ''}{f', {place}' if place else ''}. Connect on VidhiSangh, the professional network for India's legal fraternity."
    json_ld = {"@context": "https://schema.org", "@type": "ProfilePage",
               "mainEntity": {"@type": "Person", "name": name, "jobTitle": headline or None, "url": SITE + path,
                              **({"address": {"@type": "PostalAddress", "addressLocality": place}} if place else {})}}
    html = f"""<!doctype html>
<html lang="en-IN"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{escape(title[:160])}</title><meta name="description" content="{escape(description[:300])}" />
<meta name="robots" content="index, follow" /><link rel="canonical" href="{SITE}{path}" />
<meta property="og:type" content="profile" /><meta property="og:site_name" content="VidhiSangh" />
<meta property="og:title" content="{escape(title[:160])}" /><meta property="og:description" content="{escape(description[:300])}" />
<meta property="og:url" content="{SITE}{path}" /><meta property="og:image" content="{SITE}/images/landing/og-feature.png" />
<meta name="theme-color" content="#215dcc" /><link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<link rel="stylesheet" href="{CSS_URL}" /><style>{CSS}</style>
<script type="application/ld+json">{json.dumps(json_ld, ensure_ascii=False).replace("</", "<\\/")}</script></head>
<body><header class="top"><a class="brand" href="/"><img src="/brand-mark.svg" alt="" width="30" height="30" /><span>VidhiSangh</span></a>
<nav><a class="join" href="{JOIN}">Join now</a><a class="signin" href="/auth/login">Sign in</a></nav></header>
<main>{body}</main>
<footer><p><a href="/acts/">Bare Acts</a> · <a href="/tools/">Free tools</a> · <a href="/">VidhiSangh</a> · <a href="/privacy">Privacy</a> · <a href="/terms">Terms</a></p>
<p>This page was published by the member, who can withdraw it at any time in Settings → Privacy &amp; data.</p></footer>
</body></html>"""
    response = HTMLResponse(html)
    response.headers["Content-Security-Policy"] = CSP
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


def _quote(text: str) -> str:
    from urllib.parse import quote
    return quote(text, safe="")


@router.get("/sitemap-profiles.xml")
async def profiles_sitemap(session: AsyncSession = Depends(get_auth_session)) -> Response:
    rows = (await session.execute(
        select(NetworkIdentity.public_handle, NetworkIdentity.updated_at, ProfessionalProfile.visibility)
        .outerjoin(ProfessionalProfile, (ProfessionalProfile.user_id == NetworkIdentity.user_id) & ProfessionalProfile.deleted_at.is_(None))
        .where(NetworkIdentity.public_page.is_(True), NetworkIdentity.public_handle.is_not(None), NetworkIdentity.deleted_at.is_(None))
        .order_by(NetworkIdentity.public_handle)
    )).all()
    urls = [f"<url><loc>{SITE}/in/{h}/</loc><lastmod>{u.date().isoformat()}</lastmod></url>"
            for h, u, vis in rows if vis in (None, ProfileVisibility.PUBLIC, "public")]
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(urls) + "\n</urlset>\n")
    return Response(xml, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})
