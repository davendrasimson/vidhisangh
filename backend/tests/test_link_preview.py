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


# ─── SSRF guard (audit A-4) ─────────────────────────────────────────
import httpx  # noqa: E402

from app.core.link_preview import (  # noqa: E402
    UnsafeUrlError,
    assert_public_http_url,
    fetch_link_preview,
    set_http_client_factory,
)
from tests.conftest import PUBLIC_IP  # noqa: E402

_HTML = '<html><head><meta property="og:title" content="Inside"></head></html>'


@pytest.mark.parametrize(
    "url",
    [
        "http://private.test/",            # 10.0.0.5
        "http://loopback.test/",           # 127.0.0.1
        "http://linklocal.test/",          # 169.254.1.1
        "http://metadata.test/",           # 169.254.169.254
        "http://v6loopback.test/",         # ::1
        "http://mixed.test/",              # public + private A records
        "http://unresolvable.test/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::ffff:127.0.0.1]/",      # IPv4-mapped loopback
        "http://user:pw@example.com/",     # credentials in URL
        "file:///etc/passwd",
        "gopher://example.com/",
    ],
)
async def test_guard_blocks_internal_targets(client: AsyncClient, url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        await assert_public_http_url(url)


async def test_guard_pins_public_address_and_can_require_https(client: AsyncClient) -> None:
    pinned = await assert_public_http_url("https://example.com:8443/path?q=1")
    assert pinned.ip == PUBLIC_IP
    assert pinned.pinned_url == f"https://{PUBLIC_IP}:8443/path?q=1"
    assert pinned.headers == {"Host": "example.com:8443"}
    assert pinned.extensions == {"sni_hostname": "example.com"}
    with pytest.raises(UnsafeUrlError):
        await assert_public_http_url("http://example.com/", require_https=True)


async def test_fetcher_revalidates_every_redirect_hop(client: AsyncClient) -> None:
    """A public page that 302s to an internal address must not be fetched."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.headers["host"] == "public.test":
            return httpx.Response(302, headers={"location": "http://loopback.test/admin"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=_HTML)

    set_http_client_factory(lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kw))
    set_link_preview_fetcher(None)
    try:
        assert await fetch_link_preview("http://public.test/") is None
    finally:
        set_http_client_factory(None)
    # Only the first hop was requested — connected to the pinned IP, not the name.
    assert seen == [f"http://{PUBLIC_IP}/"]


async def test_fetcher_follows_public_redirects_by_hand_with_a_cap(client: AsyncClient) -> None:
    hops: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.headers["host"]
        hops.append(host)
        n = int(host.split(".")[0].removeprefix("hop") or 0)
        if n < 2:
            return httpx.Response(301, headers={"location": f"http://hop{n + 1}.test/"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=_HTML)

    set_http_client_factory(lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kw))
    set_link_preview_fetcher(None)
    try:
        preview = await fetch_link_preview("http://hop0.test/")
        assert preview is not None and preview.title == "Inside" and preview.url == "http://hop2.test/"
        assert hops == ["hop0.test", "hop1.test", "hop2.test"]

        # An endless redirect loop stops after the cap (5) and yields nothing.
        def loop(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "http://loop.test/"})

        set_http_client_factory(lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(loop), **kw))
        assert await fetch_link_preview("http://loop.test/") is None
    finally:
        set_http_client_factory(None)


async def test_link_preview_requires_composer_permission(client: AsyncClient, strong_password: str, fake_preview) -> None:
    """The unfurl endpoint is not a general fetch proxy: read-only roles get 403."""
    from tests.test_access_control import _invite

    owner_h = await _user(client, "Unfurl LLP", "owner@unfurl.co", strong_password)
    guest_h, _ = await _invite(client, owner_h, "guest@unfurl.co", ["guest"])
    resp = await client.get(f"/api/v1/network/link-preview", params={"url": "https://example.com/a"}, headers=guest_h)
    assert resp.status_code == 403
