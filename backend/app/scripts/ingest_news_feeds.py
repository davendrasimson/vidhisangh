"""Import legal-news RSS/Atom feeds into the shared news table.

The importer stores only headline metadata, a short feed summary, attribution,
the publisher URL and publication date. It never copies an article or crawls
links recursively. Configure feeds with ``VS_NEWS_FEEDS`` as a JSON array:

    Configure only approved official publisher feeds. Supreme Court judgment
    listings use the separate ``ingest_official_news`` module.

Run from a scheduled job (for example every 30 minutes):
``python -m app.scripts.ingest_news_feeds --max-items 100``
Use ``--dry-run`` to inspect candidates without writing anything.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx
from sqlalchemy import select

import app.db.base  # noqa: F401 — register models
from app.core.config import settings
from app.core.database import session_scope
from app.modules.news.models import NewsCategory, NewsItem

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_NON_NEWS_RE = re.compile(r"\b(vacanc(?:y|ies)|recruitment|career|job updates?)\b", re.I)


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    category: NewsCategory = NewsCategory.NEWS


@dataclass(frozen=True)
class Entry:
    title: str
    url: str
    summary: str | None
    published_at: datetime
    tags: list[str]


def _feeds() -> list[Feed]:
    raw = getattr(settings, "NEWS_FEEDS", None) or "[]"
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit("VS_NEWS_FEEDS must be valid JSON.") from exc
    feeds: list[Feed] = []
    for value in values:
        if not isinstance(value, dict) or not value.get("name") or not value.get("url"):
            raise SystemExit("Each news feed needs name and url.")
        parsed = urlparse(str(value["url"]))
        if "livelaw" in str(value["name"]).lower().replace(" ", "") or (parsed.hostname or "").endswith("livelaw.in"):
            raise SystemExit("LiveLaw is excluded from VidhiSangh news sources.")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise SystemExit(f"News feed URL is not http(s): {value['url']}")
        try:
            category = NewsCategory(value.get("category", "news"))
        except ValueError as exc:
            raise SystemExit(f"Unknown news category for {value['name']}") from exc
        feeds.append(Feed(str(value["name"])[:150], str(value["url"]), category))
    return feeds


def _text(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    value = html.unescape(_TAG_RE.sub(" ", value))
    value = _SPACE_RE.sub(" ", value).strip()
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    return value[:limit] or None


def _date(value: str | None) -> datetime:
    if value:
        try:
            parsed = parsedate_to_datetime(value)
            return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except (TypeError, ValueError, OverflowError):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except ValueError:
                pass
    return datetime.now(UTC)


def _entries(payload: bytes, max_items: int) -> list[Entry]:
    root = ElementTree.fromstring(payload)
    result: list[Entry] = []
    # RSS and Atom use different names; local-name matching keeps this tolerant
    # of the common content/media namespaces without accepting arbitrary HTML.
    for node in list(root.iter()):
        name = node.tag.rsplit("}", 1)[-1].lower()
        if name not in {"item", "entry"}:
            continue
        values: dict[str, str] = {}
        links: list[str] = []
        for child in list(node):
            child_name = child.tag.rsplit("}", 1)[-1].lower()
            value = (child.text or "").strip()
            if child_name == "link":
                href = child.attrib.get("href")
                if href:
                    links.append(href)
                elif value:
                    links.append(value)
            elif child_name in {"title", "description", "summary", "content", "pubdate", "published", "updated", "date"}:
                values.setdefault(child_name, value)
        url = next((link for link in links if urlparse(link).scheme in {"http", "https"}), "")
        title = _text(values.get("title"), 400)
        if not title or not url:
            continue
        result.append(Entry(title, url[:600], _text(values.get("description") or values.get("summary") or values.get("content"), 800),
                            _date(values.get("pubdate") or values.get("published") or values.get("updated") or values.get("dc:date")), []))
        if len(result) >= max_items:
            break
    return result


async def ingest(*, dry_run: bool, max_items: int) -> tuple[int, int]:
    feeds = _feeds()
    if not feeds:
        raise SystemExit("No feeds configured. Set VS_NEWS_FEEDS to a JSON array.")
    added = skipped = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(20), follow_redirects=True, headers={"User-Agent": "VidhiSangh-NewsBot/1.0 (+https://vidhisangh.com)"}) as client:
        async with session_scope(bypass_rls=True) as session:
            for feed in feeds:
                response = await client.get(feed.url)
                response.raise_for_status()
                for entry in _entries(response.content, max_items):
                    # Keep the public news page focused on legal developments;
                    # some publisher feeds also contain recruitment notices.
                    if "/job-updates/" in entry.url.lower() or _NON_NEWS_RE.search(entry.title):
                        skipped += 1
                        continue
                    exists = await session.scalar(select(NewsItem.id).where(NewsItem.url == entry.url, NewsItem.deleted_at.is_(None)))
                    if exists:
                        skipped += 1
                        continue
                    if dry_run:
                        print(f"would add [{feed.name}] {entry.title} — {entry.url}")
                        added += 1
                        continue
                    session.add(NewsItem(title=entry.title, summary=entry.summary, source=feed.name,
                                         category=feed.category, url=entry.url, published_at=entry.published_at,
                                         tags=entry.tags, added_by=uuid.UUID(int=0)))
                    added += 1
    return added, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Import configured legal RSS/Atom feeds")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-items", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.max_items <= 500:
        parser.error("--max-items must be between 1 and 500")
    added, skipped = asyncio.run(ingest(dry_run=args.dry_run, max_items=args.max_items))
    print(f"news feed import: {added} added, {skipped} already present")


if __name__ == "__main__":
    main()
