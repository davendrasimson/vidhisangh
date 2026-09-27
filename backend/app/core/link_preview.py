"""Link preview (Open Graph "unfurl") — fetch a URL's social preview metadata.

Follows the pluggable-seam pattern used elsewhere (storage, payments, channels):
a real HTTP fetcher by default, overridable via :func:`set_link_preview_fetcher`
so tests inject a deterministic result without network access.

Security: outbound fetches are a classic SSRF vector, so the default fetcher
validates the scheme and refuses hosts that resolve to private / loopback /
link-local / reserved addresses, caps the response size, and uses a short
timeout. (Production hardening — pinning the resolved IP through redirects to
defeat DNS-rebinding — is noted in FUTURE_DELIVERABLES.)
"""

from __future__ import annotations

import asyncio
import html
import ipaddress
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
import structlog

log = structlog.get_logger("app.link_preview")

_MAX_BYTES = 512 * 1024  # only need the <head>; never slurp whole pages
_TIMEOUT = 5.0
_USER_AGENT = "VidhiSanghBot/1.0 (+link-preview)"


@dataclass(slots=True)
class LinkPreview:
    url: str
    title: str | None = None
    description: str | None = None
    image: str | None = None
    site_name: str | None = None

    def is_empty(self) -> bool:
        return not (self.title or self.description or self.image)


Fetcher = Callable[[str], Awaitable[LinkPreview | None]]


# ─── SSRF guard ──────────────────────────────────────────────────────
async def _host_is_public(host: str) -> bool:
    try:
        infos = await asyncio.get_event_loop().getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


async def is_fetchable(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    return await _host_is_public(parsed.hostname)


# ─── HTML parsing (best-effort, no bs4 dependency) ───────────────────
_META_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r"""([\w:-]+)\s*=\s*("([^"]*)"|'([^']*)')""")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _meta_map(head: str) -> dict[str, str]:
    """Map og:* / twitter:* / name-based meta keys → content."""
    out: dict[str, str] = {}
    for tag in _META_RE.findall(head):
        attrs: dict[str, str] = {}
        for m in _ATTR_RE.finditer(tag):
            attrs[m.group(1).lower()] = html.unescape(m.group(3) or m.group(4) or "")
        key = attrs.get("property") or attrs.get("name")
        content = attrs.get("content")
        if key and content:
            out.setdefault(key.lower(), content.strip())
    return out


def parse_preview(url: str, body: str) -> LinkPreview:
    meta = _meta_map(body)
    title = meta.get("og:title") or meta.get("twitter:title")
    if not title:
        m = _TITLE_RE.search(body)
        if m:
            title = html.unescape(re.sub(r"\s+", " ", m.group(1)).strip())
    description = (
        meta.get("og:description")
        or meta.get("twitter:description")
        or meta.get("description")
    )
    image = meta.get("og:image") or meta.get("og:image:url") or meta.get("twitter:image")
    if image:
        image = urljoin(url, image)  # resolve protocol-relative / relative image URLs
    return LinkPreview(
        url=url,
        title=(title or None),
        description=(description or None),
        image=(image or None),
        site_name=meta.get("og:site_name"),
    )


# ─── Default HTTP fetcher ────────────────────────────────────────────
async def _http_fetch(url: str) -> LinkPreview | None:
    if not await is_fetchable(url):
        log.info("link_preview_blocked", url=url)
        return None
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, follow_redirects=True, max_redirects=5, headers=headers
        ) as client:
            async with client.stream("GET", url) as resp:
                ctype = resp.headers.get("content-type", "")
                if "html" not in ctype:
                    return LinkPreview(url=url)  # not an HTML page → no metadata
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= _MAX_BYTES:
                        break
        body = b"".join(chunks).decode("utf-8", errors="replace")
        return parse_preview(str(resp.url), body)
    except (httpx.HTTPError, ValueError) as exc:
        log.info("link_preview_fetch_failed", url=url, error=str(exc))
        return None


_fetcher: Fetcher = _http_fetch


def set_link_preview_fetcher(fetcher: Fetcher | None) -> None:
    """Test hook: override the fetcher (pass None to restore the HTTP default)."""
    global _fetcher
    _fetcher = fetcher or _http_fetch


async def fetch_link_preview(url: str) -> LinkPreview | None:
    return await _fetcher(url)
