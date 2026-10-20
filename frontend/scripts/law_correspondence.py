"""Old law <-> new law correspondence (IPC->BNS, CrPC->BNSS, Evidence Act->BSA).

Source: the "Correspondence Table and Comparison Summary" PDFs published by the
Bureau of Police Research & Development (BPRD), MHA:
https://bprd.mha.gov.in/page/documents_by_bprd

Only the facts are kept: each new-law section or sub-section, its subject, and
the old-law section(s) it corresponds to. The "summary of comparison" column
is the compiler's own commentary (it carries a copyright line), so it is not
copied; pages link to BPRD for it.

Usage (from frontend/, one-off; the JSON output is committed and read by
scripts/build-act-pages.mjs, so builds need neither the PDFs nor pdfplumber):

    python3 scripts/law_correspondence.py <dir with the three BPRD PDFs>

Needs pdfplumber (pip install pdfplumber), outside the app's dependencies.
"""

from __future__ import annotations

import json
import os
import re
import sys

PAIRS = {
    # new act id: (old act id, PDF file, column order of new / subject / old)
    "bns": ("ipc", "COMPARISON SUMMARY BNS to IPC .pdf", ("new", "subject", "old")),
    "bnss": ("crpc", "Comparison summary BNSS to CrPC.pdf", ("new", "subject", "old")),
    "bsa": ("evidence", "Comparison Summary BSA to IEA.pdf", ("new", "old", "subject")),
}
SOURCE = "https://bprd.mha.gov.in/page/documents_by_bprd"


def _cell(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\n", " ")).strip()


def raw_rows(path: str, order: tuple[str, str, str]) -> list[dict]:
    """Rows of (new, subject, old). Cells are assigned to columns by where they
    sit on the page (the header row's column edges), not by their index:
    some pages split a column in two, which shifts every index after it."""
    import pdfplumber

    out: list[dict] = []
    with pdfplumber.open(path) as pdf:
        edges: list[float] = []
        for page in pdf.pages:
            # Continuation pages draw no line above their first row, which
            # pdfplumber then drops: add one where the column rules start.
            verticals = [e for e in page.edges if e["orientation"] == "v" and e["height"] > 8]
            settings = {"explicit_horizontal_lines": [min(e["top"] for e in verticals)]} if verticals else {}
            for table in page.find_tables(settings):
                for row in table.rows:
                    boxes = [b for b in row.cells if b is not None]
                    texts = [(b[0], _cell(page.crop(b).extract_text())) for b in boxes]
                    if not edges and any(re.match(r"(?i)^(BNS|BNSS|BSA)\b", t) for _, t in texts):
                        # Header row: the left edge of each of the four columns,
                        # found by its words (the first page's header has
                        # overlapping cells with scrambled text).
                        def at(pattern: str) -> float:
                            return min(x for x, t in texts if re.search(pattern, t, re.I))
                        edges = sorted([min(x for x, _ in texts), at(r"^subject"),
                                        at(r"^(IPC|CrPC|IEA)\b"), at(r"^summary")])
                        continue
                    if not edges:
                        continue
                    cols = ["", "", "", ""]
                    for x0, text in texts:
                        if not text:
                            continue
                        i = max(k for k, e in enumerate(edges) if x0 >= e - 3) if x0 >= edges[0] - 3 else 0
                        cols[i] = (cols[i] + " " + text).strip()
                    if re.match(r"(?i)^(BNS|BNSS|BSA)\b", cols[0]):
                        continue  # header repeated on a later page
                    row_ = dict(zip(order, cols[:3]))
                    if not row_["new"]:
                        if out and (row_["subject"] or row_["old"]):
                            # A cell that ran onto the next page.
                            out[-1]["subject"] = (out[-1]["subject"] + " " + row_["subject"]).strip()
                            out[-1]["old_raw"] = (out[-1]["old_raw"] + " " + row_["old"]).strip()
                        continue
                    out.append({"new": row_["new"], "subject": row_["subject"], "old_raw": row_["old"]})
    return out


def norm_section(value: str) -> str:
    """'125 (a)' -> '125(a)', '2(1) (c)' -> '2(1)(c)', '2(1)(e )' -> '2(1)(e)';
    'First proviso to section 22' -> '22, first proviso'."""
    text = re.sub(r"\s+", " ", value).replace("Explanati on", "Explanation")
    m = re.match(r"(?i)^(.*?(?:proviso|explanation))\s+to\s+section\s+(\d+[A-Z]?(?:\(\d+\))?)", text)
    if m:
        return f"{m.group(2)}, {m.group(1).lower()}"
    v = re.sub(r"\s+", "", value)
    v = v.replace("[", "(").replace("]", ")")
    return v.rstrip(".,;")


OLD_NUMBER = re.compile(r"\b(\d{1,3}[A-Z]{0,2})(?=\b|\()")


def old_sections(raw: str) -> list[str]:
    """Base old-law section numbers named in the cell: '29 and 29A' -> ['29', '29A'];
    '3, para 1' -> ['3']; 'New' / '-' -> []. Sub-section detail stays in old_raw."""
    text = raw.replace("]", ")").replace("[", "(")
    if re.fullmatch(r"(?i)\s*(new|-|–|—|nil|n/?a)?\s*", text):
        return []
    text = re.sub(r"(?i)\bpara\s*\d+", "", text)          # "3, para 1"
    text = re.sub(r"\([^)]*\)", "", text)                  # "2(a)" -> "2"
    text = re.sub(r"(?i)\b(IEA|IPC|CrPC|Cr\.P\.C\.|section|sections|sec\.?)\b", " ", text)
    found: list[str] = []
    # Ranges such as "121 to 123" or "121-123".
    for a, b in re.findall(r"\b(\d{1,3})\s*(?:to|-|–)\s*(\d{1,3})\b", text):
        if int(a) < int(b) <= int(a) + 40:
            found += [str(n) for n in range(int(a), int(b) + 1)]
    found += OLD_NUMBER.findall(text.upper())
    seen: list[str] = []
    for s in found:
        if s not in seen:
            seen.append(s)
    return seen


def build(pdf_dir: str) -> None:
    os.makedirs("content/correspondence", exist_ok=True)
    for new_id, (old_id, pdf, order) in PAIRS.items():
        rows = raw_rows(os.path.join(pdf_dir, pdf), order)
        new_secs = {s["number"] for s in json.load(open(f"content/acts/{new_id}.json", encoding="utf-8"))["sections"]}
        old_path = f"content/acts/{old_id}.json"
        old_secs = {s["number"] for s in json.load(open(old_path, encoding="utf-8"))["sections"]} if os.path.exists(old_path) else None
        entries, problems = [], []
        for r in rows:
            new = norm_section(r["new"])
            base = re.match(r"\d+", new)
            if not base or base.group(0) not in new_secs:
                problems.append(f"unknown {new_id} section {r['new']!r}")
                continue
            olds = old_sections(r["old_raw"])
            if old_secs is not None:
                unknown = [o for o in olds if o not in old_secs]
                if unknown:
                    problems.append(f"{new_id} {new}: {old_id} {unknown} not in the Act text ({r['old_raw']!r})")
            entries.append({
                "new": new, "subject": r["subject"].rstrip("."), "old": olds,
                "old_raw": r["old_raw"] if r["old_raw"] not in ("-", "–") else "",
            })
        covered = {re.match(r"\d+", e["new"]).group(0) for e in entries}
        missing_new = sorted(new_secs - covered, key=lambda s: int(re.match(r"\d+", s).group(0)))
        data = {"new_act": new_id, "old_act": old_id, "source": SOURCE, "entries": entries}
        with open(f"content/correspondence/{new_id}.json", "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        mapped_old = {o for e in entries for o in e["old"]}
        print(f"{new_id:5} <- {old_id:8} {len(entries)} rows, {len(covered)}/{len(new_secs)} {new_id} sections, "
              f"{len(mapped_old)} {old_id} sections; {len(problems)} problems; {new_id} sections not in table: {missing_new[:15]}")
        for p in problems[:40]:
            print("   ", p)


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else ".")
