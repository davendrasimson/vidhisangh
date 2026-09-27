"""Extract the text of High Court order PDFs into ``judgments.full_text``.

    python -m app.scripts.extract_order_text --courts delhi --year-from 2024 --year-to 2024
    python -m app.scripts.extract_order_text --courts delhi,phhc --year-from 2020 --limit 500

The open-data bucket ships one tar bundle per bench-year
(``data/tar/year=YYYY/court=<code>/bench=<code>/data.tar``, plus small
``part-*.tar`` files of later additions) whose members are the order PDFs,
named ``<CNR>_<n>_<decision date>.pdf`` — the same file name our stored ``url``
ends in. So the mapping is exact: file name -> judgment row, no network lookups.

Pipeline, per bundle:
  1. stream the tar over HTTPS (never written to disk — Delhi 2024 alone is
     4.5 GB, and the server has 57 GB free);
  2. hand each PDF's bytes to a process pool running pypdf (CPU-bound; the
     main process keeps streaming);
  3. write ``full_text`` in batches. The GIN expression index (0040) updates
     with each row; nothing else to maintain.

Also, where a row has no counsel yet, the text's opening is parsed with the
same ``parse_counsel`` the registry description goes through — P&H and
Allahabad print counsel in the order, not in the metadata.

Idempotent: rows with ``text_extracted_at`` set are skipped unless ``--force``.
Scanned (image-only) PDFs yield no text; they are marked extracted with an
empty string so they are not retried every run, and counted in the log.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import re
import tarfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import Future, ProcessPoolExecutor
from datetime import UTC, date, datetime

import structlog
from sqlalchemy import Text, bindparam, cast, select, update

from app.core.database import session_scope
from app.modules.research.models import Judgment
from app.modules.research.normalise import advocate_text, parse_acts_sections, parse_counsel
from app.scripts.ingest_hc_judgments import BUCKET, COURTS

log = structlog.get_logger("app.extract_text")
_BATCH = 200
_MAX_CHARS = 2_000_000  # a 200-page judgment is ~600k; anything beyond is noise


def _list_tars(court_code: str, year: int) -> list[str]:
    """Every tar bundle key for one court-year (all benches)."""
    prefix = f"data/tar/year={year}/court={court_code}/"
    keys: list[str] = []
    token = None
    while True:
        url = f"{BUCKET}/?list-type=2&prefix={urllib.parse.quote(prefix)}&max-keys=1000"
        if token:
            url += "&continuation-token=" + urllib.parse.quote(token)
        root = ET.fromstring(urllib.request.urlopen(url, timeout=60).read())
        ns = root.tag.split("}")[0] + "}"
        keys += [
            e.find(ns + "Key").text
            for e in root.findall(ns + "Contents")
            if e.find(ns + "Key").text.endswith(".tar")
        ]
        nxt = root.find(ns + "NextContinuationToken")
        if nxt is None:
            return keys
        token = nxt.text


def pdf_text(pdf_bytes: bytes) -> str:
    """Plain text of one PDF; '' when it cannot be read (corrupt or scanned)."""
    from pypdf import PdfReader  # in the worker process

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception:  # noqa: BLE001 — one bad file must not stop the bundle
        return ""
    text = "\n".join(pages)
    # Postgres `text` rejects NUL ("invalid byte sequence for encoding UTF8:
    # 0x00") — one such PDF killed the first production run. Drop NUL and the
    # other C0 controls except tab/newline before anything else.
    text = re.sub(r"[\x00-\x08\x0b\x0e-\x1f\x7f]", "", text)
    # Registries pad with form feeds and runs of blank lines; keep paragraphs.
    text = re.sub(r"[ \t\f\r]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:_MAX_CHARS]


async def _rows_for_bundle(session, court_code: str, bench: str, year: int, force: bool) -> dict:  # noqa: ANN001
    """file name -> (id, has_counsel) for every order in this bench-year."""
    like = f"%/year={year}/court={court_code}/bench={bench}/%"
    q = (
        select(Judgment.id, Judgment.url, Judgment.advocate_text)
        .where(
            Judgment.deleted_at.is_(None),
            Judgment.judgment_date >= date(year, 1, 1),
            Judgment.judgment_date <= date(year, 12, 31),
            Judgment.url.like(like),
        )
    )
    if not force:
        q = q.where(Judgment.text_extracted_at.is_(None))
    return {
        url.rsplit("/", 1)[-1]: (jid, bool(adv))
        for jid, url, adv in (await session.execute(q)).all()
    }


async def _flush(session, results: list[dict]) -> None:  # noqa: ANN001
    t = Judgment.__table__
    stmt = (
        update(t)
        .where(t.c.id == bindparam("_id"))
        .values(full_text=bindparam("full_text"), text_extracted_at=bindparam("at"))
    )
    await session.execute(stmt, [{"_id": r["id"], "full_text": r["text"], "at": r["at"]} for r in results])
    counsel = [r for r in results if r.get("pet") or r.get("resp")]
    if counsel:
        stmt = (
            update(t)
            .where(t.c.id == bindparam("_id"))
            .values(
                petitioner_advocates=bindparam("pet"),
                respondent_advocates=bindparam("resp"),
                advocate_text=bindparam("adv"),
            )
        )
        await session.execute(
            stmt,
            [{"_id": r["id"], "pet": r["pet"], "resp": r["resp"], "adv": r["adv"]} for r in counsel],
        )
    cited = [r for r in results if r.get("acts")]
    if cited:
        # Only rows that have nothing yet: an SC row's curated acts are better
        # than a regex pass and must not be overwritten.
        # `json` has no equality operator in Postgres; compare its text form.
        stmt = (
            update(t)
            .where(t.c.id == bindparam("_id"), cast(t.c.acts, Text) == "[]")
            .values(acts=bindparam("acts"), sections=bindparam("sections"))
        )
        await session.execute(
            stmt, [{"_id": r["id"], "acts": r["acts"], "sections": r["sections"]} for r in cited]
        )
    await session.commit()


async def extract(courts: list[str], year_from: int, year_to: int, force: bool, limit: int, workers: int) -> None:
    started = time.monotonic()
    done = empty = counsel_added = unmatched = 0
    pool = ProcessPoolExecutor(max_workers=workers)

    async with session_scope(bypass_rls=True) as session:
        for name in courts:
            code, label = COURTS[name]
            for year in range(year_to, year_from - 1, -1):  # newest first
                for key in _list_tars(code, year):
                    bm = re.search(r"bench=([^/]+)/", key)
                    if not bm:
                        continue
                    bench = bm.group(1)
                    wanted = await _rows_for_bundle(session, code, bench, year, force)
                    if not wanted:
                        log.info("bundle_skipped", key=key, reason="nothing to extract")
                        continue
                    log.info("bundle_start", key=key, rows=len(wanted))

                    resp = urllib.request.urlopen(f"{BUCKET}/{urllib.parse.quote(key)}", timeout=3600)
                    pending: list[tuple[str, Future]] = []
                    results: list[dict] = []
                    with tarfile.open(fileobj=resp, mode="r|") as tar:
                        for member in tar:
                            if not member.isfile():
                                continue
                            fname = member.name.rsplit("/", 1)[-1]
                            hit = wanted.get(fname)
                            if hit is None:
                                unmatched += 1
                                continue
                            data = tar.extractfile(member).read()
                            pending.append((fname, pool.submit(pdf_text, data)))

                            if len(pending) >= _BATCH:
                                results += _collect(pending, wanted)
                                pending = []
                            if len(results) >= _BATCH:
                                await _flush(session, results)
                                done += len(results)
                                empty += sum(1 for r in results if not r["text"])
                                counsel_added += sum(1 for r in results if r.get("pet") or r.get("resp"))
                                results = []
                                if done % 2000 < _BATCH:
                                    log.info("progress", extracted=done, empty=empty,
                                             counsel_added=counsel_added,
                                             minutes=round((time.monotonic() - started) / 60, 1))
                            if limit and done + len(results) + len(pending) >= limit:
                                break
                    if pending:
                        results += _collect(pending, wanted)
                    if results:
                        await _flush(session, results)
                        done += len(results)
                        empty += sum(1 for r in results if not r["text"])
                        counsel_added += sum(1 for r in results if r.get("pet") or r.get("resp"))
                    log.info("bundle_done", key=key, extracted=done)
                    if limit and done >= limit:
                        pool.shutdown()
                        log.info("finished", extracted=done, empty=empty, counsel_added=counsel_added,
                                 unmatched=unmatched, minutes=round((time.monotonic() - started) / 60, 1))
                        return
    pool.shutdown()
    log.info("finished", extracted=done, empty=empty, counsel_added=counsel_added,
             unmatched=unmatched, minutes=round((time.monotonic() - started) / 60, 1))


def _collect(pending: list[tuple[str, Future]], wanted: dict) -> list[dict]:
    out: list[dict] = []
    now = datetime.now(UTC)
    for fname, fut in pending:
        jid, has_counsel = wanted[fname]
        text = fut.result()
        row: dict = {"id": jid, "text": text, "at": now}
        if text and not has_counsel:
            pet, resp = parse_counsel(text[:1500])
            if pet or resp:
                row.update(pet=pet, resp=resp, adv=advocate_text(pet, resp))
        if text:
            # Statutes cited in the order — the one field still empty for
            # High Court rows (the metadata never carried it).
            acts, sections = parse_acts_sections(text)
            if acts:
                row.update(acts=acts, sections=sections)
        out.append(row)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract order PDF text into judgments.full_text.")
    parser.add_argument("--courts", default="delhi", help="Comma-separated keys from COURTS.")
    parser.add_argument("--year-from", type=int, default=date.today().year)
    parser.add_argument("--year-to", type=int, default=date.today().year)
    parser.add_argument("--force", action="store_true", help="Re-extract rows already done.")
    parser.add_argument("--limit", type=int, default=0, help="Stop after this many rows (pilot).")
    parser.add_argument("--workers", type=int, default=3, help="pypdf worker processes.")
    args = parser.parse_args()
    courts = [c.strip() for c in args.courts.split(",") if c.strip()]
    for c in courts:
        if c not in COURTS:
            raise SystemExit(f"Unknown court '{c}'.")
    asyncio.run(extract(courts, args.year_from, args.year_to, args.force, args.limit, args.workers))


if __name__ == "__main__":
    main()
