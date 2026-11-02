"""Bounded retrieval from SCI's public latest-order/judgment listings.

This feed is discovery, not an assertion of complete archive coverage. No
CAPTCHA is bypassed. Explicit empty feeds and broken markup are distinguished.
"""

from __future__ import annotations

import asyncio
import io
import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from pypdf import PdfReader

PAGES = ("https://www.sci.gov.in/latest-orders/", "https://www.sci.gov.in/")
HOSTS = {
    "www.sci.gov.in",
    "sci.gov.in",
    "api.sci.gov.in",
    "main.sci.gov.in",
    "cdnbbsr.s3waas.gov.in",
}
MAX_BYTES = 20 * 1024 * 1024


def official_url(url: str) -> str:
    p = urlsplit(url)
    if (
        p.scheme != "https"
        or p.hostname not in HOSTS
        or p.username
        or p.password
        or p.port not in (None, 443)
    ):
        raise ValueError("Not an approved official SCI document URL")
    # Sort query parameters so markup parameter ordering cannot create duplicates.
    return urlunsplit(
        (
            p.scheme,
            p.netloc.lower(),
            p.path,
            urlencode(
                sorted(
                    (key, value) for key, values in parse_qs(p.query).items() for value in values
                )
            ),
            "",
        )
    )


@dataclass(frozen=True)
class OrderEntry:
    title: str
    day: date
    url: str


class ListingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.entries: list[OrderEntry] = []
        self.href: str | None = None
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = urljoin(PAGES[0], dict(attrs).get("href", ""))
        p = urlsplit(href)
        if p.path.rstrip("/") == "/view-pdf" and parse_qs(p.query).get("type") in (["o"], ["j"]):
            self.href, self.parts = official_url(href), []

    def handle_data(self, data):
        if self.href:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag != "a" or not self.href:
            return
        href, self.href = self.href, None
        query = parse_qs(urlsplit(href).query)
        try:
            day = date.fromisoformat(query["order_date"][0])
        except (KeyError, ValueError):
            raise ValueError("SCI order link has no valid order date") from None
        title = re.sub(r"\s+", " ", " ".join(self.parts)).split("(Uploaded On")[0].strip(" -")
        if not title:
            raise ValueError("SCI order link has no title")
        self.entries.append(OrderEntry(title[:500], day, href))


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        value = (
            a.get("src")
            if tag in {"iframe", "embed"}
            else a.get("data")
            if tag == "object"
            else a.get("href")
            if tag == "a"
            else None
        )
        if value and ".pdf" in value.lower():
            self.links.append(value)


class SupremeCourtSource:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def download(self, url: str) -> tuple[str, bytes]:
        for _ in range(6):
            url = official_url(url)
            async with self.client.stream("GET", url, follow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ValueError("SCI response exceeds size limit")
                return url, bytes(data)
        raise ValueError("Too many SCI redirects")

    async def discover(self) -> list[OrderEntry]:
        entries = {}
        for url in PAGES:
            _, body = await self.download(url)
            html = body.decode("utf-8")
            parser = ListingParser()
            parser.feed(html)
            if not parser.entries and not re.search(r"No records found", html, re.I):
                raise ValueError("SCI listing format changed; refusing to treat it as an empty day")
            for entry in parser.entries:
                entries[entry.url] = entry
        return sorted(entries.values(), key=lambda x: (x.day, x.url))

    async def document(self, url: str) -> tuple[str, bytes]:
        url, body = await self.download(url)
        if body.startswith(b"%PDF-"):
            return url, body
        parser = DocumentParser()
        parser.feed(body.decode("utf-8"))
        for link in parser.links:
            candidate = urljoin(url, link)
            try:
                official_url(candidate)
            except ValueError:
                continue
            target, pdf = await self.download(candidate)
            if pdf.startswith(b"%PDF-"):
                return target, pdf
        raise ValueError("Official order page did not yield a PDF")


def _extract(pdf: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf))
    if not 1 <= len(reader.pages) <= 400:
        raise ValueError("PDF page count requires manual review")
    pages = [page.extract_text() or "" for page in reader.pages]
    # Do not silently summarise a PDF whose scanned pages were omitted.
    if any(len(re.sub(r"\s", "", page)) < 20 for page in pages):
        raise ValueError("PDF includes blank/image-only pages; manual text review required")
    return re.sub(r"[\x00-\x08\x0b\x0e-\x1f\x7f]", "", "\n\n".join(pages)).strip()


async def extract_document(pdf: bytes) -> str:
    return await asyncio.to_thread(_extract, pdf)
