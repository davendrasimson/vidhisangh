"""The First Schedule to the BNSS, 2023 (classification of offences), as data.

Part I of the Schedule classifies every offence under the Bharatiya Nyaya
Sanhita: section, substance of the offence, punishment, cognizable or not,
bailable or not, and the court that tries it. Part II classifies offences
under other laws by their punishment. Reads the official text bundled at
public/bare-acts/bnss.pdf (Gazette of India) through `pdftotext -layout`.

Each page of the Schedule has a numeric header row ("1 2 3 4 5 6") whose
digits sit over the six columns; the left edge of each column is the smallest
start position, on that page, of a word run that sits under that digit. Lines
are then sliced at those edges. A row begins where column 1 carries a section
number; a further row for the same section (e.g. the second limb of section
55) begins where column 2 starts a new sentence and the classification
columns are filled again.

Writes content/bnss-first-schedule.json for the offence screener and the Act reader.

    python3 scripts/bnss_schedule.py      (from frontend/; needs poppler-utils)
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter

PDF = "public/bare-acts/bnss.pdf"
HEADER_RE = re.compile(r"^\s*1\s{4,}2\s{4,}3\s{4,}4\s{4,}5\s{4,}6\s*$")
SECTION_RE = re.compile(r"^(\d{1,3})\s*((?:\(\w{1,3}\))*)\s*$")
# The column headings repeated on each page: "Section Offence Punishment …" / "cognizable bailable triable".
COLUMN_HEADER_RE = re.compile(r"^\s*(Section\s+Offence\s+Punishment|cognizable\s+bailable\s+triable)\b")
FURNITURE = ("THE GAZETTE OF INDIA", "EXTRAORDINARY", "[Part II", "Sec. 1]", "__________", "THE FIRST SCHEDULE",
             "CLASSIFICATION OF OFFENCES", "I.—OFFENCES UNDER", "EXPLANATORY NOTES",
             "intended as the definition", "Nyaya Sanhita, but merely", "third columns against", "(2) In this Schedule",
             "does not include Executive", "may arrest without warrant", "shall not arrest without")

# Two rows where a column's text starts left of its header on that page and the
# slicer cannot tell the columns apart; set by hand from the Gazette text.
OVERRIDES = {
    "57": {"offence": "Abetting commission of an offence by the public or by more than ten persons.",
           "punishment": "Imprisonment which may extend to 7 years and fine.",
           "cognizable_text": "According as offence abetted is cognizable or non-cognizable.",
           "bailable_text": "According as offence abetted is bailable or non-bailable.",
           "court": "Court by which offence abetted is triable."},
    "193(3)": {"offence": "Agent of owner or occupier for whose benefit a riot is committed not using all lawful means to prevent it.",
               "punishment": "Fine.", "cognizable_text": "Non-cognizable.", "bailable_text": "Bailable.",
               "court": "Any Magistrate."},
}

PART_II = [
    {"band": "Punishable with death, imprisonment for life, or imprisonment for more than 7 years",
     "cognizable": "cognizable", "bailable": "non_bailable", "court": "Court of Session."},
    {"band": "Punishable with imprisonment for 3 years and upwards but not more than 7 years",
     "cognizable": "cognizable", "bailable": "non_bailable", "court": "Magistrate of the first class."},
    {"band": "Punishable with imprisonment for less than 3 years or with fine only",
     "cognizable": "non_cognizable", "bailable": "bailable", "court": "Any Magistrate."},
]


def _runs(line: str) -> list[int]:
    """Start positions of word runs preceded by two or more spaces (or the line start)."""
    return [m.start() for m in re.finditer(r"(?:(?<=\s{2})|^)\S", line)]


def _edges(lines: list[str], centres: list[int]) -> list[int]:
    """Left edge of each of the six columns on one page."""
    starts: list[list[int]] = [[] for _ in centres]
    for line in lines:
        for pos in _runs(line):
            # A column's text starts left of (or under) its centred header digit.
            col = next((i for i, c in enumerate(centres) if pos <= c + 2), None)
            if col is not None:
                starts[col].append(pos)
    edges = [min(s) if s else c for s, c in zip(starts, centres)]
    edges[0] = 0
    return edges


def _slice(line: str, edges: list[int]) -> list[str]:
    cells = []
    for i, start in enumerate(edges):
        end = edges[i + 1] if i + 1 < len(edges) else len(line)
        cells.append(line[start:end])
    # A word straddling an edge belongs to the column it starts in.
    for i in range(len(cells) - 1):
        if cells[i] and not cells[i].endswith(" ") and cells[i + 1][:1] not in ("", " "):
            m = re.match(r"^(\S+)(.*)$", cells[i + 1])
            cells[i], cells[i + 1] = cells[i] + m.group(1), m.group(2)
    return [re.sub(r"\s+", " ", c).strip() for c in cells]


def _norm_flag(text: str, positive: str, negative: str) -> str:
    t = text.lower()
    if t.startswith("non-" + positive) or t.startswith("non " + positive):
        return negative
    if t.startswith(positive):
        return positive
    if t.startswith("according"):
        return "according"
    return "" if not t else "see_text"


def extract() -> tuple[list[dict], list[str]]:
    text = subprocess.run(["pdftotext", "-layout", PDF, "-"], capture_output=True, text=True, check=True).stdout
    started = False
    rows: list[dict] = []
    notes: list[str] = []
    for page in text.split("\f"):
        if "II.—CLASSIFICATION OF OFFENCES AGAINST OTHER LAWS" in page:
            page = page.split("II.—CLASSIFICATION OF OFFENCES AGAINST OTHER LAWS")[0]
            last = True
        else:
            last = False
        if not started:
            if "THE FIRST SCHEDULE" not in page:
                continue
            started = True
        lines = page.splitlines()
        header = next((l for l in lines if HEADER_RE.match(l)), None)
        if header is None:
            if last:
                break
            continue
        centres = [m.start() for m in re.finditer(r"\d", header)]
        body = [l for l in lines[lines.index(header) + 1:]
                if l.strip() and not re.fullmatch(r"\s*\d+\s*", l) and not any(f in l for f in FURNITURE)
                and not COLUMN_HEADER_RE.match(l)]
        edges = _edges(body, centres)
        for line in body:
            sec, offence, punishment, cog, bail, court = _slice(line, edges)
            m = SECTION_RE.match(sec) if sec else None
            new_section = bool(m)
            new_limb = (not new_section and offence[:1].isupper()
                        and sum(1 for c in (punishment, cog, bail, court) if c) >= 3 and rows)
            if new_section or new_limb:
                section = f"{m.group(1)}{m.group(2)}" if new_section else rows[-1]["section"]
                rows.append({"section": section, "offence": offence, "punishment": punishment,
                             "cognizable_text": cog, "bailable_text": bail, "court": court})
            elif rows:
                r = rows[-1]
                if sec:  # a stray fragment in column 1 ("(a)" on its own line) belongs to the number
                    r["section"] += sec
                for key, val in (("offence", offence), ("punishment", punishment), ("cognizable_text", cog),
                                 ("bailable_text", bail), ("court", court)):
                    if val:
                        r[key] = f"{r[key]} {val}".strip()
            else:
                notes.append(f"skipped before first row: {line.strip()[:80]}")
        if last:
            break
    for r in rows:
        if r["section"] in OVERRIDES:
            r.update(OVERRIDES[r["section"]])
        for k in ("offence", "punishment", "cognizable_text", "bailable_text", "court"):
            r[k] = re.sub(r"\s+", " ", r[k]).replace(" .", ".").replace("- ", "-").strip()
        r["cognizable"] = _norm_flag(r["cognizable_text"], "cognizable", "non_cognizable")
        r["bailable"] = _norm_flag(r["bailable_text"], "bailable", "non_bailable")
    return rows, notes


if __name__ == "__main__":
    rows, notes = extract()
    # IPC section -> BNS section(s), from the BPRD correspondence table already in the repo,
    # so the screener can take "IPC 420" as well as a BNS section.
    ipc: dict[str, list[str]] = {}
    for e in json.load(open("content/correspondence/bns.json"))["entries"]:
        for old in e["old"]:
            key = re.sub(r"\s+", "", old)
            if e["new"] not in ipc.setdefault(key, []):
                ipc[key].append(e["new"])
    data = {"source": "BNSS 2023, First Schedule (Gazette of India), via public/bare-acts/bnss.pdf",
            "part_i": rows, "part_ii": PART_II, "ipc_to_bns": ipc}
    json.dump(data, open("content/bnss-first-schedule.json", "w"), ensure_ascii=False, indent=1)
    sections = [r["section"] for r in rows]
    print(len(rows), "rows;", len(set(sections)), "distinct section labels")
    print("cognizable:", Counter(r["cognizable"] for r in rows).most_common())
    print("bailable:", Counter(r["bailable"] for r in rows).most_common())
    print("courts:", Counter(r["court"] for r in rows).most_common(8))
    for n in notes[:5]:
        print("note:", n)
    for want in ("64(1)", "103(1)", "303(2)", "318(4)", "351(2)", "356(4)", "55", "106(1)"):
        for r in rows:
            if r["section"] == want:
                print(want, "|", r["offence"][:60], "|", r["punishment"][:60], "|", r["cognizable"], r["bailable"], "|", r["court"])
