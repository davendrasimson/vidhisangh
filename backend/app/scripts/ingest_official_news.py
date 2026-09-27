"""Import legal updates from verified Indian court and government sources.

Each run makes one bounded request per configured page, follows no article links,
deduplicates by the official document URL, and leaves the database unchanged if
every live source fails or its markup no longer yields entries.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from sqlalchemy import select, update

import app.db.base  # noqa: F401
from app.core.database import session_scope
from app.modules.news.models import NewsItem
from app.modules.news.repository import permitted_source

SCI = "https://www.sci.gov.in/"
DHC = "https://delhihighcourt.nic.in/web/announcements"
SCI_IMAGE = "/images/news/justice-editorial.webp"
HIGH_COURT_IMAGE = "/images/news/state-high-court-editorial.webp"
LEGISLATION_IMAGE = "/images/news/legislation-editorial.webp"
NOTICE_IMAGE = "/images/news/official-notice-editorial.webp"


@dataclass(frozen=True)
class Entry:
    title: str
    source: str
    category: str
    url: str
    published_at: datetime
    summary: str
    tags: list[str]


def clean(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def date_from_cdn(url: str) -> datetime | None:
    match = re.search(r"/uploads/(\d{4})/(\d{2})/(\d{8})", url)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(3), "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def classify(title: str, label: str = "") -> str:
    value = f"{label} {title}".lower()
    if "notification" in value:
        return "notification"
    if "circular" in value or "listing notice" in value or "notice" in value:
        return "circular"
    return "news"


def image_for(entry: Entry) -> str:
    return image_path(entry.source, entry.category)


def image_path(source: str, category: str) -> str:
    if category == "legislation":
        return LEGISLATION_IMAGE
    if category in {"notification", "circular"}:
        return NOTICE_IMAGE
    if "high court" in source.lower():
        return HIGH_COURT_IMAGE
    return SCI_IMAGE


class SupremeCourtParser(HTMLParser):
    """Read judgment and homepage update anchors from sci.gov.in."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.entries: list[Entry] = []
        self.href: str | None = None
        self.kind: str | None = None
        self.parts: list[str] = []
        self.spans: list[str] = []
        self.in_span = False
        self.span_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            href = urljoin(SCI, attrs.get("href", ""))
            parsed = urlparse(href)
            query = parse_qs(parsed.query)
            if parsed.hostname == "www.sci.gov.in" and parsed.path == "/view-pdf/" and query.get("type") == ["j"]:
                self.href, self.kind = href, "judgment"
            elif "content-view-sci" in attrs.get("class", "") and href.startswith("https://cdnbbsr.s3waas.gov.in/"):
                self.href, self.kind = href, "update"
            else:
                return
            self.parts, self.spans = [], []
        elif tag == "span" and self.href:
            self.in_span, self.span_parts = True, []

    def handle_data(self, data):
        if self.href:
            self.parts.append(data)
            if self.in_span:
                self.span_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "span" and self.in_span:
            self.in_span = False
            self.spans.append(clean(self.span_parts))
        if tag != "a" or not self.href:
            return
        href, kind, self.href = self.href, self.kind, None
        if kind == "judgment":
            query = parse_qs(urlparse(href).query)
            try:
                published = datetime.strptime(query["order_date"][0], "%Y-%m-%d").replace(tzinfo=UTC)
            except (KeyError, ValueError):
                return
            title = clean(self.parts).split("(Uploaded On")[0].strip(" -")[:400]
            if title:
                self.entries.append(Entry(title, "Supreme Court of India", "judgment", href, published,
                    f"The Supreme Court lists this judgment dated {published:%d %B %Y}. Open the official document to read the decision and its reasons.", ["Official source", "Supreme Court", "Judgment"]))
        else:
            published = date_from_cdn(href)
            if not published:
                return
            label = self.spans[0] if len(self.spans) > 1 else "Latest update"
            title = (self.spans[-1] if self.spans else clean(self.parts))[:400]
            category = classify(title, label)
            if title and title.lower() != "view all":
                self.entries.append(Entry(title, "Supreme Court of India", category, href, published,
                    f"Official {label.lower()} published by the Supreme Court of India. Open the source document for the complete text.", ["Official source", "Supreme Court", label]))


class SupremeCourtNoticesParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.entries: list[Entry] = []
        self.href: str | None = None
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        href = attrs.get("href", "")
        if tag == "a" and attrs.get("title") == "Click here to view" and href.startswith("https://cdnbbsr.s3waas.gov.in/"):
            self.href, self.parts = href, []

    def handle_data(self, data):
        if self.href:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag != "a" or not self.href:
            return
        href, self.href = self.href, None
        title, published = clean(self.parts)[:400], date_from_cdn(href)
        if title and published:
            category = classify(title)
            self.entries.append(Entry(title, "Supreme Court of India", category, href, published,
                "Official notice or circular published by the Supreme Court of India. Open the source document for the complete text.", ["Official source", "Supreme Court", category.title()]))


class DelhiHighCourtParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.entries: list[Entry] = []
        self.in_row = self.in_cell = False
        self.cells: list[str] = []
        self.cell_parts: list[str] = []
        self.href: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_row, self.cells, self.href = True, [], None
        elif tag == "td" and self.in_row:
            self.in_cell, self.cell_parts = True, []
        elif tag == "a" and self.in_row:
            href = dict(attrs).get("href", "")
            if href.lower().endswith(".pdf"):
                self.href = urljoin(DHC, href)

    def handle_data(self, data):
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.in_cell:
            self.in_cell = False
            self.cells.append(clean(self.cell_parts))
        if tag != "tr" or not self.in_row:
            return
        self.in_row = False
        if len(self.cells) < 3 or not self.href:
            return
        try:
            published = datetime.strptime(self.cells[2], "%d/%m/%Y").replace(tzinfo=UTC)
        except ValueError:
            return
        title = self.cells[1][:400]
        self.entries.append(Entry(title, "High Court of Delhi", "judgment", self.href, published,
            f"The High Court of Delhi lists this judgment pronouncement dated {published:%d %B %Y}. Open the official document for details.", ["Official source", "Delhi High Court", "Judgment pronouncement"]))


def legislation_entries() -> list[Entry]:
    """Verified recent official texts; update this list when India Code publishes newer Acts."""
    return [
        Entry("The Supreme Court (Number of Judges) Amendment Ordinance, 2026", "Legislative Department", "legislation",
            "https://www.legislative.gov.in/static/uploads/2026/05/61eb3f0307259c025404ddeaa563b08e.pdf",
            datetime(2026, 5, 16, tzinfo=UTC), "Official text of Ordinance No. 1 of 2026, published by the Ministry of Law and Justice.", ["Official source", "Ordinance", "2026"]),
        Entry("The Repealing and Amending Act, 2025", "India Code", "legislation",
            "https://www.indiacode.nic.in/bitstream/123456789/22046/1/a2025-37.pdf",
            datetime(2025, 12, 20, tzinfo=UTC), "Official text of Act No. 37 of 2025 from India Code.", ["Official source", "Central Act", "2025"]),
        Entry("The Promotion and Regulation of Online Gaming Act, 2025", "India Code", "legislation",
            "https://www.indiacode.nic.in/handle/123456789/1362/browse?type=shorttitle&value=The+Promotion+and+Regulation+of+Online+Gaming+Act%2C+2025",
            datetime(2025, 8, 22, tzinfo=UTC), "Official India Code record for Central Act No. 32 of 2025.", ["Official source", "Central Act", "2025"]),
    ]


async def ingest(*, dry_run: bool = False, archive_competitor: bool = False) -> None:
    specs = [(SCI, SupremeCourtParser), (f"{SCI}notices-and-circulars/", SupremeCourtNoticesParser), (DHC, DelhiHighCourtParser)]
    entries, errors = legislation_entries(), []
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        for url, parser_type in specs:
            try:
                response = await client.get(url)
                response.raise_for_status()
                parser = parser_type()
                parser.feed(response.text)
                if not parser.entries:
                    raise RuntimeError("page returned no recognised entries")
                entries.extend(parser.entries[:30])
            except Exception as exc:
                errors.append(f"{url}: {exc}")
    if len(entries) == len(legislation_entries()):
        raise RuntimeError("All live official sources failed; no records changed. " + "; ".join(errors))
    unique = {entry.url: entry for entry in entries}
    if dry_run:
        for entry in unique.values():
            print(f"{entry.published_at.date()} | {entry.category:12} | {entry.source} | {entry.title}")
        if errors:
            print("source warnings: " + "; ".join(errors))
        return
    added = updated = archived = 0
    async with session_scope() as session:
        for entry in unique.values():
            existing = await session.scalar(select(NewsItem).where(NewsItem.url == entry.url))
            expected_image = image_for(entry)
            if existing:
                if existing.deleted_at is not None:
                    existing.deleted_at = None
                    updated += 1
                if existing.image_url != expected_image:
                    existing.image_url = expected_image
                    updated += 1
                continue
            session.add(NewsItem(title=entry.title, source=entry.source, category=entry.category,
                url=entry.url, summary=entry.summary, image_url=expected_image,
                published_at=entry.published_at, tags=entry.tags, added_by=uuid.UUID(int=0)))
            added += 1
        # Re-map older visible records too, including entries no longer present
        # on a source's first page.
        visible = (await session.scalars(select(NewsItem).where(NewsItem.deleted_at.is_(None), permitted_source()))).all()
        for item in visible:
            expected_image = image_path(item.source, item.category.value if hasattr(item.category, "value") else str(item.category))
            if item.image_url != expected_image:
                item.image_url = expected_image
                updated += 1
        if archive_competitor:
            result = await session.execute(update(NewsItem).where(~permitted_source(), NewsItem.deleted_at.is_(None)).values(deleted_at=datetime.now(UTC)))
            archived = result.rowcount
    print(f"official news: {added} added, {updated} updated, {archived} competitor items archived")
    if errors:
        print("source warnings: " + "; ".join(errors))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--archive-competitor", action="store_true")
    args = parser.parse_args()
    asyncio.run(ingest(dry_run=args.dry_run, archive_competitor=args.archive_competitor))
