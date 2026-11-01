"""Outreach CSV from the eastern / north-eastern / southern official lists (third batch, 1 Nov 2026).

    python3 -I scripts/outreach_build_contacts_east.py <src_dir> <out.csv> [<calcutta_dir>]

<calcutta_dir> holds cis_<id>.txt: the Calcutta High Court's "Registered Advocates in CIS 1.0" lists
(Notice-Files/general-notice/<id>; 5371 = as on 04.01.2022, 5463…6661 = weekly additions, 7671 = master
database up to 22.12.2022). Mobiles are masked there, so only the email is kept.

<src_dir> holds pdftotext -layout output (see docs/OUTREACH.md → Sources for the URLs):
  jharkhand_hc_reg_advocates_2024-11-30.txt   Jharkhand High Court, list of advocates as on 30.11.2024 (one row each)
  wb_slsa_panel_lawyers_catA_2025-10.txt      West Bengal SLSA panel lawyers, category A
  tripura_hclsc_notification_1174.txt         Tripura HC Legal Services Committee empanelment, 27.06.2025
  assam_gauhati_hc_senior_advocates_2022.txt  Gauhati High Court, senior advocates, 30.06.2022
  assam_gauhati_hc_amicus_curiae_2024.txt     Gauhati High Court, amicus curiae panel, notification 80 of 03.12.2024
  telangana_hc_standing_counsels_2021.txt     Telangana: Special Government Pleaders / Government Pleaders (2020)
Columns: email,name,mobile,city,court,source.
"""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from outreach_build_contacts import clean_name, emails_in  # noqa: E402
from outreach_build_contacts_states import mobile_in  # noqa: E402

HON = r"(?:Mr|Ms|Mrs|Smt|Shri|Sri|Sh|Dr|Md|Miss)\.?"
NAME_LINE = re.compile(rf"^\s*(?:\d+\.?\s+)?(?:{HON}\s+)+([A-Z][A-Za-z .'\-]{{2,60}}?),?\s*(?:Sr\.?\s*Advocate.*)?$")


def parse_jharkhand(text: str):
    """Sl | NAME | enrolment | mobile or NULL | address (wraps) | email, one advocate per first line."""
    row = re.compile(r"^\s*\d+\s+([A-Z][A-Z .'\-]+?)\s{2,}(\S+)\s+(\d{10}|NULL)\s*(.*?)\s*(\S+@\S+)\s*$")
    for line in text.splitlines():
        m = row.match(line)
        if m:
            addrs = emails_in(m.group(5))
            if addrs:
                yield addrs[0], clean_name(m.group(1)), (m.group(3) if m.group(3) != "NULL" else None), "Ranchi"


def parse_wb(text: str):
    """Entries start 'N.  NAME   mobile(s)   field'; the email sits on the next line under the mobile.
    A name may wrap onto that next line (left column)."""
    lines = text.splitlines()
    entries = []
    for i, ln in enumerate(lines):
        m = re.match(r"^\s*(\d+)\.\s+(\S.*?)(?:\s{2,}|$)", ln)
        if m and not re.match(r"^\s*\d+\.\s+\d", ln):
            entries.append([clean_name(m.group(2)), i])
    for k, (name, start) in enumerate(entries):
        end = entries[k + 1][1] if k + 1 < len(entries) else len(lines)
        block = lines[start:end]
        nxt = block[1] if len(block) > 1 else ""
        mm = re.match(r"^\s{2,12}([A-Z][A-Za-z .'\-]+?)(?:\s{2,}|$)", nxt)
        if mm and "@" not in mm.group(1):
            name = clean_name(f"{name} {mm.group(1)}")
        joined = re.sub(r"@gmail\.c\s*$", "@gmail.com", " ".join(block).replace("\n", " "))
        addrs = emails_in(joined)
        if addrs:
            yield addrs[0], name, mobile_in(block[0]), "Kolkata"


def parse_anchor(text: str, *, city: str, window: int = 8, join_wrapped: bool = False):
    """Generic: each email, with the nearest preceding honorific-led name line (within `window` lines)."""
    lines = text.splitlines()
    if join_wrapped:  # 'vijaydewanhanda@rediffmail.co' + next line 'm'
        out = []
        for ln in lines:
            if out and re.fullmatch(r"\s*[a-z]{1,3}\s*", ln) and "@" in out[-1]:
                out[-1] = out[-1].rstrip() + ln.strip()
            else:
                out.append(ln)
        lines = out
    for i, ln in enumerate(lines):
        if "@" not in ln:
            continue
        addrs = emails_in(ln)  # scanned lists: only addresses that read cleanly; never "repair" OCR gaps
        if not addrs:
            continue
        name = None
        for j in range(i, max(-1, i - window), -1):
            m = NAME_LINE.match(lines[j])
            if m:
                name = clean_name(m.group(1))
                break
        if name:
            mob = mobile_in(" ".join(lines[max(0, i - window): i + 3]))
            yield addrs[0], name, mob, city


def parse_gauhati_seniors(text: str):
    """Sl | Shri Name | GHC Principal Seat | phone | email (email may wrap)."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if "@" not in ln:
            continue
        joined = ln
        if i + 1 < len(lines) and re.fullmatch(r"\s*[a-z]{1,3}\s*", lines[i + 1]):
            joined = ln.rstrip() + lines[i + 1].strip()
        m = re.match(rf"^\s*\d+\.\s+(?:{HON}\s+)?([A-Z][A-Za-z .'\-]+?)\s{{2,}}", joined)
        addrs = emails_in(joined)
        if m and addrs:
            yield addrs[0], clean_name(m.group(1)), mobile_in(joined), "Guwahati"


def parse_telangana(text: str):
    """Sl | Name, (GP) | department | mobile | mail; the AG office's shared mailbox is dropped."""
    for line in text.splitlines():
        m = re.match(r"^\s*\d+\s+([A-Za-z][A-Za-z .'\-]+?)(?:,\s*(?:Spl\.\s*)?\(?GP\)?)?\s{2,}.*?\s(\S+@\S+)\s*(?:\S*)?\s*$", line)
        if m and "agofficetg" not in m.group(2) and not re.search(r"Attached|Advocate General|Addl", m.group(1)):
            addrs = emails_in(m.group(2))
            if addrs:
                yield addrs[0], clean_name(m.group(1)), mobile_in(line), "Hyderabad"


SRC_CAL = "the Calcutta High Court's lists of registered advocates in CIS 1.0 (calcuttahighcourt.gov.in, 2022)"
CAL_ROW_NAMED = re.compile(r"^(\S.*?)\s{2,}(\S.*?)\s{2,}\S*\*{3,}\S*\s+(\S+@\S+)\s*$")
CAL_ROW_NUMBERED = re.compile(r"^\s*\d+\s+(\S.*?)\s{2,}\S*\*{3,}\S*\s+(\S+@\S+)\s*$")


def parse_calcutta(text: str):
    for line in text.splitlines():
        m = CAL_ROW_NAMED.match(line)
        if m:
            addrs = emails_in(m.group(3))
            if addrs:
                yield addrs[0], clean_name(m.group(2)), None, "Kolkata"
            continue
        m = CAL_ROW_NUMBERED.match(line)
        if m:
            addrs = emails_in(m.group(2))
            if addrs:
                yield addrs[0], clean_name(m.group(1)), None, ""


SOURCES = [
    ("jharkhand_hc_reg_advocates_2024-11-30.txt", parse_jharkhand, "Jharkhand High Court",
     "the Jharkhand High Court's list of advocates as on 30.11.2024 (jharkhandhighcourt.nic.in)"),
    ("wb_slsa_panel_lawyers_catA_2025-10.txt", parse_wb, "Calcutta High Court",
     "the West Bengal State Legal Services Authority's panel of lawyers, category A (westbengal.nalsa.gov.in)"),
    ("tripura_hclsc_notification_1174.txt", lambda t: parse_anchor(t, city="Agartala", window=10), "Tripura High Court",
     "the Tripura High Court Legal Services Committee's empanelment notification of 27.06.2025 (hctlsc.tripura.gov.in)"),
    ("assam_gauhati_hc_senior_advocates_2022.txt", parse_gauhati_seniors, "Gauhati High Court",
     "the Gauhati High Court's list of senior advocates, 30.06.2022 (ghconline.gov.in)"),
    ("assam_gauhati_hc_amicus_curiae_2024.txt", lambda t: parse_anchor(t, city="Guwahati", window=6), "Gauhati High Court",
     "the Gauhati High Court's panel of amicus curiae, notification of 03.12.2024 (ghconline.gov.in)"),
    ("telangana_hc_standing_counsels_2021.txt", parse_telangana, "Telangana High Court",
     "the Telangana High Court's list of Special Government Pleaders and Government Pleaders (tshc.gov.in)"),
]


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    sources = list(SOURCES)
    if len(sys.argv) > 3:
        cal = Path(sys.argv[3])
        sources += [(str(p), parse_calcutta, "Calcutta High Court", SRC_CAL) for p in sorted(cal.glob("cis_*.txt"))]
    rows, seen = [], set()
    for fname, parser, court, source in sources:
        path = src / fname if not Path(fname).is_absolute() else Path(fname)
        if not path.exists():
            print(f"{fname:44} missing")
            continue
        n = 0
        for addr, name, mobile, city in parser(path.read_text(encoding="utf-8", errors="replace")):
            if addr in seen:
                continue
            if not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{3,44}", name or "") or re.search(r"\b(Mr|Ms|Mrs|Dr|Ch|Counsel|Sh|Smt|Shri|Sri)\b", name or ""):
                name = ""
            seen.add(addr)
            rows.append({"email": addr, "name": f"Adv. {name}" if name else "", "mobile": mobile or "", "city": city,
                         "court": court, "source": source})
            n += 1
        print(f"{fname:44} {n:5}")
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["email", "name", "mobile", "city", "court", "source"])
        w.writeheader()
        w.writerows(rows)
    print(f"total {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
