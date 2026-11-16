"""Read a court's cause-list index: which lists exist for which day.

Only index pages are fetched (one or two requests per court per run) and only
labels and PDF links are kept. No list is opened, no case, party, counsel or
AOR search is submitted, and the CAPTCHA-protected searches are never touched.

* **Supreme Court** (``sci``): the "Cause lists at a glance" table on
  ``/cause-list/``: one row per listing day, fourteen columns in a fixed order
  (advance list, then main/supplementary pairs for court-number, judge,
  chamber, single-judge, review & curative and registrar lists, then the
  weekly list). Labels come from the column position, dates from the PDF
  path (``/jonew/cl/<date>/...``).
* **Allahabad High Court** (``allahabad``): each bench's cause-list form
  (``input1A.jsp`` / ``input1L.jsp``, list type Z = the combined cause list;
  type D, "daily", offers no dates) lists the dates a combined list exists
  for, as unquoted ``<option value=dd-mm-yyyy>``. Lists are court-wise pages
  on the bench's own site, so the link is the bench's index page.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime
from html import unescape

import httpx

from app.modules.courts.registry import Court

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36 VidhiSangh"
TIMEOUT = 40

SCI_COLUMNS = (
    "Advance list",
    "Court number-wise, main", "Court number-wise, supplementary",
    "Judge-wise, main", "Judge-wise, supplementary",
    "Chamber, main", "Chamber, supplementary",
    "Single judge, main", "Single judge, supplementary",
    "Review and curative, main", "Review and curative, supplementary",
    "Registrar, main", "Registrar, supplementary",
    "Weekly list",
)
_SCI_DATE = re.compile(r"/cl/(?:advance/|wk/)?(\d{4}-\d{2}-\d{2})")
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_HREF = re.compile(r'href="([^"]+\.pdf)"', re.I)
_OPTION = re.compile(r"<option[^>]*\svalue=[\"']?([^\"'\s>]*)", re.I)  # quoted or bare values
ALLAHABAD_LIST_TYPE = "Z"  # the combined cause list

ALLAHABAD_BENCHES = (
    ("Allahabad", "https://www.allahabadhighcourt.in/causelist/input1A.jsp",
     "https://www.allahabadhighcourt.in/causelist/indexA.html"),
    ("Lucknow Bench", "https://hclko.allahabadhighcourt.in/causelist/input1L.jsp",
     "https://hclko.allahabadhighcourt.in/causelist/indexL.html"),
)


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def parse_sci(html: str) -> dict[date, list[dict]]:
    """The glance table → {listing day: [{label, url}]}. Rows that do not have the
    fourteen columns (the layout changed) are ignored, so the job reports nothing
    rather than mislabelled links."""
    start = html.find("causelist-glance")
    table = html[start:] if start >= 0 else html
    out: dict[date, list[dict]] = defaultdict(list)
    seen: set[str] = set()
    for row in _ROW.findall(table):
        cells = _CELL.findall(row)
        if len(cells) not in (len(SCI_COLUMNS), len(SCI_COLUMNS) + 1):
            continue
        for label, cell in zip(SCI_COLUMNS, cells[-len(SCI_COLUMNS):], strict=True):
            m = _HREF.search(cell)
            if not m:
                continue
            url = unescape(m.group(1))
            d = _SCI_DATE.search(url)
            if not d or url in seen:
                continue
            seen.add(url)
            out[date.fromisoformat(d.group(1))].append({"label": label, "url": url})
    return dict(out)


def parse_dates(html: str) -> list[date]:
    """The dates offered by a ``<select>`` of listing dates (dd-mm-yyyy, dd/mm/yyyy or ISO)."""
    found: list[date] = []
    for value in _OPTION.findall(html):
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                found.append(datetime.strptime(value.strip(), fmt).date())
                break
            except ValueError:
                continue
    return sorted(set(found))


async def fetch_sci(http: httpx.AsyncClient, court: Court) -> dict[date, list[dict]]:
    r = await http.get(court.cause_list_url)
    r.raise_for_status()
    return parse_sci(r.text)


async def fetch_allahabad(http: httpx.AsyncClient, court: Court) -> dict[date, list[dict]]:
    out: dict[date, list[dict]] = defaultdict(list)
    for bench, form_url, index_url in ALLAHABAD_BENCHES:
        r = await http.post(form_url, data={"listType": ALLAHABAD_LIST_TYPE})
        r.raise_for_status()
        for day in parse_dates(r.text):
            out[day].append({"label": f"Combined cause list, {bench} (court-wise)", "url": index_url})
    return dict(out)


FETCHERS = {"sci": fetch_sci, "allahabad": fetch_allahabad}


async def fetch(http: httpx.AsyncClient, court: Court) -> dict[date, list[dict]]:
    if not court.fetcher:
        return {}
    return await FETCHERS[court.fetcher](http, court)
