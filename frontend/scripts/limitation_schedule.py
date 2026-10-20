"""The Schedule to the Limitation Act, 1963 (periods of limitation), as data.

Reads the official text bundled at public/bare-acts/limitation.pdf (India
Code) through `pdftotext -layout`, splitting each line into the Schedule's
three columns at the positions of that page's header ("Description of suit |
Period of limitation | Time from which period begins to run"). Footnote
markers and amendment footnotes are dropped.
Writes content/limitation-schedule.json for the limitation calculator.

    python3 scripts/limitation_schedule.py      (from frontend/; needs poppler-utils)
"""

from __future__ import annotations

import json
import re
import subprocess

PDF = "public/bare-acts/limitation.pdf"
HEADING = re.compile(r"^\s*(FIRST|SECOND|THIRD) DIVISION|^\s*PART [IVX]+\.?\s*[—-]")
FOOTNOTE = re.compile(r"^\s{0,4}\d+\.\s*(Subs\.|Ins\.|Omitted|The words|Added|Rep\.)")
PERIOD = re.compile(r"^((?:\[?(?:One|Two|Three|Six|Ten|Twelve|Thirty|Sixty|Ninety)\s+(?:years?|days|months?)\.?\]?\s*)+)(.*)$", re.I)


def extract() -> list[dict]:
    text = subprocess.run(["pdftotext", "-layout", PDF, "-"], capture_output=True, text=True, check=True).stdout
    articles: list[dict] = []
    division = part = ""
    started = False
    for page in text.split("\f"):
        if not started:
            if "PERIODS OF LIMITATION" not in page:
                continue
            started = True
        lines = page.splitlines()
        header = next((l for l in lines if "Period" in l and "Time from which" in l), None)
        if header is None:
            continue
        cut1, cut2 = header.index("Period") - 2, header.index("Time from which") - 2
        in_footnotes = False
        for line in lines:
            if not line.strip() or line is header or re.fullmatch(r"\s*\d+\s*", line):
                continue
            if re.fullmatch(r"\s*_{5,}\s*", line):
                in_footnotes = True  # amendment footnotes below the rule
            if in_footnotes or FOOTNOTE.match(line):
                continue
            if "Description of" in line or "suit" == line.strip():
                continue
            if HEADING.match(line):
                label = re.sub(r"\s+", " ", line.strip()).title().replace("—", " — ")
                if "Division" in label:
                    division, part = label, ""
                else:
                    part = label
                continue
            desc, period, start = line[:cut1], line[cut1:cut2], line[cut2:]
            # A word straddling a cut belongs to the column it starts in.
            m = re.match(r"^(\S+)(\s.*)?$", period)
            if desc and not desc.endswith(" ") and m and period[:1] != " ":
                desc, period = desc + m.group(1), (m.group(2) or "")
            if period and not period.endswith(" ") and start[:1] not in (" ", ""):
                m2 = re.match(r"^(\S+)(.*)$", start)
                period, start = period + m2.group(1), m2.group(2)
            desc, period, start = (re.sub(r"\s+", " ", x).strip() for x in (desc, period, start))
            # The period column holds only "Three years." etc.; any other word
            # there is the start of the third column that began a little early.
            spaced = re.sub(r"\b([A-Z])\s(?=[a-z]\s|[a-z]{1,2}\b)", r"\1", period)  # "O n e" -> "One"
            spaced = re.sub(r"(?<=\b[a-z])\s(?=[a-z]\b)", "", spaced)
            pm = PERIOD.match(spaced)
            if pm:
                period, start = pm.group(1).strip(), f"{pm.group(2)} {start}".strip()
            elif period and not re.search(r"(?i)year|day|month", period):
                period, start = "", f"{period} {start}".strip()
            num = re.match(r"^(\d+)\.\s*(.*)$", desc)
            if num and (not articles or int(num.group(1)) == articles[-1]["article"] + 1):
                articles.append({"article": int(num.group(1)), "division": division, "part": part,
                                 "description": num.group(2), "period": period, "from": start})
            elif articles:
                a = articles[-1]
                a["description"] = f"{a['description']} {desc}".strip()
                a["period"] = f"{a['period']} {period}".strip()
                a["from"] = f"{a['from']} {start}".strip()
    for a in articles:
        for k in ("description", "period", "from"):
            v = a[k].replace("‟", "'").replace("“", '"').replace("”", '"')
            v = re.sub(r"(?<=\w)\d\[|\]|\b\d\[", "", v)  # amendment markers "1[...]"
            a[k] = re.sub(r"\s+", " ", v).replace("[", "").strip()
        for k in ("division", "part"):
            a[k] = re.sub(r"\b(Ii|Iii|Iv|Vi|Vii|Viii|Ix|Xi)\b", lambda m: m.group(1).upper(), a[k])
    return articles


if __name__ == "__main__":
    arts = extract()
    json.dump(arts, open("content/limitation-schedule.json", "w"), ensure_ascii=False, indent=1)
    nums = [a["article"] for a in arts]
    print(len(arts), "articles; sequential:", nums == list(range(1, len(nums) + 1)))
    from collections import Counter
    print(Counter(a["period"] for a in arts).most_common())
