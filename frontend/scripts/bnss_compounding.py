"""Section 359 BNSS, 2023 — the two tables of compoundable offences, as data.

Table (1): offences compoundable by the person named in column 3.
Table (2): offences compoundable by that person only with the permission of the
Court before which the prosecution is pending. Read from the bundled Gazette
text (public/bare-acts/bnss.pdf) through `pdftotext -layout`; each page's
column edges come from the header line ("Offence | Section of the Bharatiya |
Person by whom offence"). A row begins where the section column carries a value.

Writes content/bnss-compounding.json for the offence screener and the Act reader.

    python3 scripts/bnss_compounding.py      (from frontend/; needs poppler-utils)
"""

from __future__ import annotations

import json
import re
import subprocess

PDF = "public/bare-acts/bnss.pdf"
HEADER_RE = re.compile(r"^\s*Offence\s+Section of the Bharatiya\s+Person by whom offence")
START_1 = re.compile(r"\b359\.\s*\(1\)\s*The offences")  # a margin note ("Compounding") precedes it
START_2 = re.compile(r"^\s*\(2\) The offences punishable under the sections")
END = re.compile(r"^\s*\(3\) When an offence is compoundable")
SKIP = ("THE GAZETTE OF INDIA", "EXTRAORDINARY", "[Part II", "Sec. 1]", "__________", "Nyaya Sanhita applicable",
        "may be compounded", "specified in the first two columns", "Court before which any prosecution",
        "persons mentioned in the third column", "be compounded by the persons", "compounded by the persons")
SECTION_RE = re.compile(r"^\d{1,3}(?:\(\w{1,3}\))*(?:\s*,\s*\d{1,3}(?:\(\w{1,3}\))*)*\s*$")


def _cells(line: str, edges: tuple[int, int]) -> tuple[str, str, str]:
    a, b = edges
    offence, section, person = line[:a], line[a:b], line[b:]
    # A word straddling an edge belongs to the column it starts in.
    if offence and not offence.endswith(" ") and section[:1] not in ("", " "):
        m = re.match(r"^(\S+)(.*)$", section)
        offence, section = offence + m.group(1), m.group(2)
    if section and not section.endswith(" ") and person[:1] not in ("", " "):
        m = re.match(r"^(\S+)(.*)$", person)
        section, person = section + m.group(1), m.group(2)
    offence, section, person = (re.sub(r"\s+", " ", c).strip() for c in (offence, section, person))
    # On some pages column 3 starts left of its header: "84 The husband" — give the words back.
    m = re.match(r"^(\d{1,3}(?:\(\w{1,3}\))*(?:\s*,\s*\d{1,3}(?:\(\w{1,3}\))*)*)\s+([A-Za-z].*)$", section)
    if m:
        section, person = m.group(1), f"{m.group(2)} {person}".strip()
    elif section and not re.match(r"^\d", section):
        person, section = f"{section} {person}".strip(), ""
    return offence, section, person


def extract() -> list[dict]:
    text = subprocess.run(["pdftotext", "-layout", PDF, "-"], capture_output=True, text=True, check=True).stdout
    lines = text.splitlines()
    rows: list[dict] = []
    part = None
    edges: tuple[int, int] | None = None
    for line in lines:
        if START_1.search(line):
            part = "victim"
            continue
        if START_2.match(line):
            part = "court"
            edges = None
            continue
        if part and END.match(line):
            break
        if not part:
            continue
        if HEADER_RE.match(line):
            edges = (line.index("Section of") - 2, line.index("Person by whom") - 2)
            continue
        if edges is None or not line.strip() or re.fullmatch(r"\s*(\d+\s*)+", line) or any(s in line for s in SKIP) \
                or line.strip() in ("Table", "TABLE"):
            continue
        offence, section, person = _cells(line, edges)
        if section and SECTION_RE.match(section):
            rows.append({"part": part, "offence": offence, "section_text": section, "by": person})
        elif rows and rows[-1]["part"] == part:
            r = rows[-1]
            if offence:
                r["offence"] = f"{r['offence']} {offence}".strip()
            if section:  # a wrapped section list ("126(2)," / "127(2)")
                r["section_text"] = f"{r['section_text']} {section}".strip()
            if person:
                r["by"] = f"{r['by']} {person}".strip()
    for r in rows:
        for k in ("offence", "section_text", "by"):
            r[k] = re.sub(r"\s+", " ", r[k]).replace(" ,", ",").replace("- ", "-").strip()
        r["sections"] = [s.strip() for s in re.split(r"\s*,\s*", r["section_text"]) if s.strip()]
    return rows


if __name__ == "__main__":
    rows = extract()
    json.dump({"source": "BNSS 2023, Section 359 (Gazette of India), via public/bare-acts/bnss.pdf", "rows": rows},
              open("content/bnss-compounding.json", "w"), ensure_ascii=False, indent=1)
    by_part = {p: sum(1 for r in rows if r["part"] == p) for p in ("victim", "court")}
    print(len(rows), "rows", by_part, "sections:", sum(len(r["sections"]) for r in rows))
    for r in rows[:3] + rows[-3:]:
        print(r["part"], "|", r["section_text"], "|", r["offence"][:55], "|", r["by"][:55])
    odd = [r for r in rows if not r["by"] or not r["offence"] or not r["section_text"].strip()[0].isdigit()]
    print("odd:", odd[:5])
