#!/usr/bin/env python3
"""Build lightweight, readable English text copies from the local bare-act PDFs."""

from __future__ import annotations

import json
import re
import subprocess
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "frontend" / "public" / "bare-acts"
TEXT_DIR = PDF_DIR / "text"

DISPLAY_TITLES = {
    "bns": "The Bharatiya Nyaya Sanhita, 2023",
    "bnss": "The Bharatiya Nagarik Suraksha Sanhita, 2023",
    "bsa": "The Bharatiya Sakshya Adhiniyam, 2023",
    "ipc": "The Indian Penal Code, 1860",
    "crpc": "The Code of Criminal Procedure, 1973",
    "evidence": "The Indian Evidence Act, 1872",
    "companies": "The Companies Act, 2013",
    "contract": "The Indian Contract Act, 1872",
    "consumer": "The Consumer Protection Act, 2019",
    "rera": "The Real Estate (Regulation and Development) Act, 2016",
    "dv": "The Protection of Women from Domestic Violence Act, 2005",
    "rti": "The Right to Information Act, 2005",
    "cpc": "The Code of Civil Procedure, 1908",
    "limitation": "The Limitation Act, 1963",
    "arbitration": "The Arbitration and Conciliation Act, 1996",
    "cheque": "The Negotiable Instruments Act, 1881",
    "it": "The Information Technology Act, 2000",
    "hindu-marriage": "The Hindu Marriage Act, 1955",
    "succession": "The Hindu Succession Act, 1956",
    "posh": "The Sexual Harassment of Women at Workplace Act, 2013",
    "pocso": "The Protection of Children from Sexual Offences Act, 2012",
    "ibc": "The Insolvency and Bankruptcy Code, 2016",
    "property": "The Transfer of Property Act, 1882",
    "special-marriage": "The Special Marriage Act, 1954",
    "legal-aid": "The Legal Services Authorities Act, 1987",
}

SEARCH_INDEX = TEXT_DIR / "search-index.json"
SECTION_MARKER = re.compile(r"(?:^|\n|\s)(\d{1,3}[A-Z]{0,2})\.\s*(?=[A-Z\[(\"“])")

DROP_LINES = (
    re.compile(r"^\s*\d+\s*$"),
    re.compile(r"^[_—-]{8,}\s*$"),
    re.compile(r"^THE GAZETTE OF INDIA EXTRAORDINARY", re.I),
    re.compile(r"^GAZETTE OF INDIA EXTRAORDINARY", re.I),
    re.compile(r"^VIDHISANGH READING COPY", re.I),
)


def first_english_heading(text: str, title: str) -> int:
    candidates = ["ARRANGEMENT OF SECTIONS", title.upper(), "MINISTRY OF LAW AND JUSTICE"]
    positions = [text.upper().find(item) for item in candidates]
    positions = [position for position in positions if position >= 0]
    return min(positions) if positions else 0


def clean_text(raw: str, title: str) -> str:
    text = unicodedata.normalize("NFKC", raw).replace("\x00", "")
    text = text[first_english_heading(text, title) :]
    lines: list[str] = []
    blank = False

    for source_line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", source_line).strip()
        if not line:
            if lines and not blank:
                lines.append("")
            blank = True
            continue
        blank = False
        if any(pattern.match(line) for pattern in DROP_LINES):
            continue
        if "Uploaded by Dte. of Printing" in line:
            continue
        if re.match(r"^(CHAPTER|PART|SCHEDULE|APPENDIX)\b", line, re.I) and lines and lines[-1] != "":
            lines.append("")
        if re.match(r"^\d+[A-Z]?[.]\s+(?!\d)", line) and lines and lines[-1] != "":
            lines.append("")
        lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return f"{title}\n\n{text}\n"


def search_records(act_id: str, text: str) -> list[dict[str, str]]:
    """Create compact verbatim passages for client-side cross-Act search."""
    records: list[dict[str, str]] = []
    current_section = ""
    for paragraph in re.split(r"\n{2,}", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        markers = list(SECTION_MARKER.finditer(paragraph))
        boundaries = [0, *[match.start() for match in markers[1:]], len(paragraph)] if markers else [0, len(paragraph)]
        for index in range(len(boundaries) - 1):
            passage = paragraph[boundaries[index]:boundaries[index + 1]].strip()
            marker = SECTION_MARKER.search(passage)
            if marker:
                current_section = marker.group(1)
            # Keep results readable even when a source PDF extracted a whole page as one paragraph.
            cursor = 0
            while cursor < len(passage):
                end = min(len(passage), cursor + 1800)
                if end < len(passage):
                    break_at = passage.rfind(" ", cursor + 1200, end)
                    if break_at > cursor:
                        end = break_at
                chunk = passage[cursor:end].strip()
                if chunk:
                    records.append({"actId": act_id, "section": current_section, "text": chunk})
                if end >= len(passage):
                    break
                cursor = max(cursor + 1, end - 180)
    return records


def main() -> None:
    manifest = json.loads((PDF_DIR / "manifest.json").read_text(encoding="utf-8"))
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict[str, int | str]] = {}
    full_text_index: list[dict[str, str]] = []

    for act_id, record in manifest.items():
        title = DISPLAY_TITLES.get(act_id, str(record["title"]))
        raw = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", "-nopgbrk", str(PDF_DIR / f"{act_id}.pdf"), "-"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        cleaned = clean_text(raw, title)
        if len(cleaned.split()) < 250:
            raise RuntimeError(f"{act_id}: extracted text is unexpectedly short")
        output = TEXT_DIR / f"{act_id}.txt"
        output.write_text(cleaned, encoding="utf-8")
        index[act_id] = {"title": title, "words": len(cleaned.split()), "bytes": output.stat().st_size}
        full_text_index.extend(search_records(act_id, cleaned))

    (TEXT_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    SEARCH_INDEX.write_text(json.dumps(full_text_index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Built {len(index)} English text editions and {len(full_text_index)} search passages in {TEXT_DIR}")


if __name__ == "__main__":
    main()
