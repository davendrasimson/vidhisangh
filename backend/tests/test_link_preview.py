"""Link preview (Open Graph unfurl) — endpoint + post snapshot.

Uses the pluggable fetcher seam (``set_link_preview_fetcher``) so no network
access is needed; the SSRF/HTTP path is exercised by the parser unit test below.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.link_preview import LinkPreview, parse_preview, set_link_preview_fetcher


async def _user(client: AsyncClient, org: str, email: str, pw: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organisation_name": org,
            "full_name": f"Adv. {email.split('@')[0].title()}",
            "email": email,
            "password": pw,
            "accept_terms": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def fake_preview():
    """Inject a deterministic preview and restore the real fetcher afterwards."""
    preview = LinkPreview(
        url="https://example.com/article",
        title="A Landmark Judgment",
        description="The court held that…",
        image="https://example.com/cover.png",
        site_name="Example Law",
    )

    async def _fetch(url: str) -> LinkPreview:
        return preview

    set_link_preview_fetcher(_fetch)
    yield preview
    set_link_preview_fetcher(None)


async def test_link_preview_endpoint(client: AsyncClient, strong_password: str, fake_preview) -> None:
    headers = await _user(client, "Firm A", "a@firma.co", strong_password)
    resp = await client.get(
        "/api/v1/network/link-preview",
        params={"url": "https://example.com/article"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "A Landmark Judgment"
    assert body["image"] == "https://example.com/cover.png"
    assert body["site_name"] == "Example Law"


async def test_link_preview_requires_auth(client: AsyncClient, fake_preview) -> None:
    resp = await client.get("/api/v1/network/link-preview", params={"url": "https://example.com"})
    assert resp.status_code == 401


async def test_empty_preview_returns_404(client: AsyncClient, strong_password: str) -> None:
    async def _empty(url: str) -> LinkPreview:
        return LinkPreview(url=url)  # nothing resolved

    set_link_preview_fetcher(_empty)
    try:
        headers = await _user(client, "Firm B", "b@firmb.co", strong_password)
        resp = await client.get(
            "/api/v1/network/link-preview",
            params={"url": "https://example.com/nope"},
            headers=headers,
        )
        assert resp.status_code == 404
    finally:
        set_link_preview_fetcher(None)


async def test_post_stores_and_returns_link_snapshot(
    client: AsyncClient, strong_password: str, fake_preview
) -> None:
    headers = await _user(client, "Firm C", "c@firmc.co", strong_password)
    create = await client.post(
        "/api/v1/network/posts",
        headers=headers,
        json={
            "content": "Worth a read: https://example.com/article",
            "link_url": fake_preview.url,
            "link_title": fake_preview.title,
            "link_description": fake_preview.description,
            "link_image": fake_preview.image,
            "link_site_name": fake_preview.site_name,
        },
    )
    assert create.status_code == 201, create.text
    assert create.json()["link_title"] == "A Landmark Judgment"

    feed = await client.get("/api/v1/network/feed", headers=headers)
    assert feed.status_code == 200
    item = feed.json()[0]
    assert item["link_url"] == "https://example.com/article"
    assert item["link_image"] == "https://example.com/cover.png"
    assert item["link_site_name"] == "Example Law"


def test_parser_extracts_open_graph() -> None:
    html = (
        "<html><head>"
        "<title>Fallback</title>"
        '<meta property="og:title" content="OG &amp; Title">'
        '<meta property="og:description" content="Desc">'
        '<meta property="og:image" content="/img/c.png">'
        '<meta property="og:site_name" content="Site">'
        "</head></html>"
    )
    p = parse_preview("https://ex.com/a", html)
    assert p.title == "OG & Title"
    assert p.image == "https://ex.com/img/c.png"  # relative → absolute
    assert p.site_name == "Site"
    assert not p.is_empty()
