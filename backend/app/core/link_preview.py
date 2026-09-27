"""Link preview (Open Graph "unfurl") + the shared outbound-URL (SSRF) guard.

Follows the pluggable-seam pattern used elsewhere (storage, payments, channels):
a real HTTP fetcher by default, overridable via :func:`set_link_preview_fetcher`
so tests inject a deterministic result without network access.

Security model (audit A-3 / A-4)
--------------------------------
Every URL the platform fetches on a user's behalf (link previews, tenant
webhooks, tenant Slack hooks) goes through :func:`assert_public_http_url`:

* scheme must be ``http``/``https`` (``https`` only in production);
* the host is resolved **once** and every address must be public — no
  private, loopback, link-local, reserved, multicast, unspecified or
  cloud-metadata (``169.254.169.254``) ranges;
* the request is then made **to the resolved IP** (URL host rewritten to the IP
  literal, original ``Host`` header + TLS SNI/certificate name preserved via the
  httpcore ``sni_hostname`` extension). Connecting to the vetted IP — instead of
  letting the HTTP client resolve the name a second time — is what defeats DNS
  rebinding (first lookup public, second lookup 127.0.0.1).
* redirects are never followed automatically; the preview fetcher walks them by
  hand (max 5 hops) and re-validates every hop with the same guard.

The resolver is injectable (:func:`set_dns_resolver`) so tests can map names to
addresses deterministically.
"""

from __future__ import annotations

import asyncio
import html
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
import structlog

from app.core.config import settings
from app.core.exceptions import ValidationError

log = structlog.get_logger("app.link_preview")

_MAX_BYTES = 512 * 1024  # only need the <head>; never slurp whole pages
_TIMEOUT = 5.0  # per hop
_TOTAL_TIMEOUT = 12.0  # whole preview (all hops)
_MAX_REDIRECTS = 5
_USER_AGENT = "VidhiSanghBot/1.0 (+link-preview)"

# Cloud instance-metadata endpoints. ``169.254.169.254`` is link-local already;
# the others are listed explicitly so the check does not depend on range math.
_METADATA_HOSTS = frozenset({"169.254.169.254", "fd00:ec2::254", "100.100.100.200", "metadata.google.internal"})


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
Resolver = Callable[[str], Awaitable[list[str]]]


class UnsafeUrlError(ValidationError):
    """The URL points somewhere the platform must not fetch (SSRF guard)."""

    code = "unsafe_url"
    message = "This URL cannot be fetched from the platform."


# ─── DNS resolution (injectable) ─────────────────────────────────────
async def _system_resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


_resolver: Resolver = _system_resolve


def set_dns_resolver(resolver: Resolver | None) -> None:
    """Test hook: map hostnames to address lists without touching DNS
    (``None`` restores the system resolver)."""
    global _resolver
    _resolver = resolver or _system_resolve


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if str(ip) in _METADATA_HOSTS:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _is_public_ip(ip.ipv4_mapped)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or getattr(ip, "is_site_local", False)  # IPv6 only
    )


@dataclass(slots=True)
class PinnedUrl:
    """A vetted URL plus the address it was vetted against."""

    url: str  # the original URL (what the receiver sees in ``Host``)
    host: str  # original hostname (SNI / Host header)
    ip: str  # the public address to connect to
    pinned_url: str  # the URL rewritten to the IP literal

    @property
    def headers(self) -> dict[str, str]:
        parsed = urlparse(self.url)
        host = parsed.hostname or self.host
        if parsed.port and parsed.port not in (80, 443):
            host = f"{host}:{parsed.port}"
        return {"Host": host}

    @property
    def extensions(self) -> dict[str, object]:
        return {"sni_hostname": self.host} if self.url.startswith("https") else {}


async def assert_public_http_url(url: str, *, require_https: bool | None = None) -> PinnedUrl:
    """Validate an outbound URL and resolve it to one vetted public address.

    Raises :class:`UnsafeUrlError` (HTTP 422) when the scheme is wrong, the host
    is missing or unresolvable, or **any** resolved address is non-public.
    ``require_https`` defaults to "only in production".
    """
    parsed = urlparse(url)
    if require_https is None:
        require_https = settings.is_production
    allowed = ("https",) if require_https else ("http", "https")
    if parsed.scheme not in allowed:
        raise UnsafeUrlError(
            "Only https:// URLs are allowed." if require_https else "Only http:// and https:// URLs are allowed."
        )
    host = parsed.hostname
    if not host or parsed.username or parsed.password:
        raise UnsafeUrlError("The URL must have a plain host name (no credentials).")
    if host.lower().rstrip(".") in _METADATA_HOSTS or host.lower().endswith(".internal"):
        raise UnsafeUrlError()
    try:
        # An IP literal is judged as-is; a name is resolved (once) and every
        # address it yields must be public.
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        try:
            addresses = await _resolver(host)
        except OSError as exc:
            raise UnsafeUrlError("The URL's host name could not be resolved.") from exc
    if not addresses:
        raise UnsafeUrlError("The URL's host name could not be resolved.")
    for raw in addresses:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise UnsafeUrlError() from exc
        if not _is_public_ip(ip):
            log.info("outbound_url_blocked", host=host, ip=str(ip))
            raise UnsafeUrlError()
    # Prefer IPv4 for the pinned connection when both families are offered.
    chosen = next((a for a in addresses if ":" not in a), addresses[0])
    ip_literal = f"[{chosen}]" if ":" in chosen else chosen
    netloc = ip_literal if parsed.port is None else f"{ip_literal}:{parsed.port}"
    pinned = urlunparse(parsed._replace(netloc=netloc))
    return PinnedUrl(url=url, host=host, ip=chosen, pinned_url=pinned)


async def is_fetchable(url: str) -> bool:
    """Boolean form of :func:`assert_public_http_url` (never requires https)."""
    try:
        await assert_public_http_url(url, require_https=False)
    except ValidationError:
        return False
    return True


# ─── HTTP client (injectable for tests) ──────────────────────────────
def _default_client(**kwargs: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(**kwargs)  # type: ignore[arg-type]


_client_factory: Callable[..., httpx.AsyncClient] = _default_client


def set_http_client_factory(factory: Callable[..., httpx.AsyncClient] | None) -> None:
    """Test hook: build the ``httpx.AsyncClient`` used for outbound fetches
    (e.g. with a ``MockTransport``). ``None`` restores the default."""
    global _client_factory
    _client_factory = factory or _default_client


def http_client(**kwargs: object) -> httpx.AsyncClient:
    """An ``AsyncClient`` that never follows redirects on its own. Callers pass
    the pinned URL and the ``Host``/SNI extras from :class:`PinnedUrl`."""
    kwargs.setdefault("follow_redirects", False)
    return _client_factory(**kwargs)


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
async def _fetch_with_redirects(url: str) -> LinkPreview | None:
    """GET ``url`` following at most ``_MAX_REDIRECTS`` hops by hand; every hop
    is re-validated and connected to by pinned IP."""
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    current = url
    async with http_client(timeout=_TIMEOUT) as client:
        for _hop in range(_MAX_REDIRECTS + 1):
            try:
                pinned = await assert_public_http_url(current, require_https=False)
            except ValidationError:
                log.info("link_preview_blocked", url=current)
                return None
            async with client.stream(
                "GET", pinned.pinned_url, headers={**headers, **pinned.headers}, extensions=pinned.extensions
            ) as resp:
                if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location")
                    if not location:
                        return None
                    current = urljoin(current, location)
                    continue
                ctype = resp.headers.get("content-type", "")
                if "html" not in ctype:
                    return LinkPreview(url=current)  # not an HTML page → no metadata
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= _MAX_BYTES:
                        break
            body = b"".join(chunks).decode("utf-8", errors="replace")
            return parse_preview(current, body)
    log.info("link_preview_too_many_redirects", url=url)
    return None


async def _http_fetch(url: str) -> LinkPreview | None:
    try:
        async with asyncio.timeout(_TOTAL_TIMEOUT):
            return await _fetch_with_redirects(url)
    except (httpx.HTTPError, ValueError, TimeoutError) as exc:
        log.info("link_preview_fetch_failed", url=url, error=str(exc))
        return None


_fetcher: Fetcher = _http_fetch


def set_link_preview_fetcher(fetcher: Fetcher | None) -> None:
    """Test hook: override the fetcher (pass None to restore the HTTP default)."""
    global _fetcher
    _fetcher = fetcher or _http_fetch


async def fetch_link_preview(url: str) -> LinkPreview | None:
    return await _fetcher(url)
