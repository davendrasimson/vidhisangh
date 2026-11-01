"""Outreach CSV from the western / central / northern official lists (fourth batch, 1 Nov 2026).

    python3 -I scripts/outreach_build_contacts_west.py <src_dir> <out.csv> [--hp <dir>] [--mphc <dir>]

<src_dir> holds pdftotext -layout output and one HTML page (URLs in docs/OUTREACH.md → Sources):
  maharashtra_mslsa_panel_b_2025-11.txt   MSLSA panel advocates, April 2026 (HCLSC / DLSA / TLSC)
  maharashtra_mslsa_panel_a_2025-11.txt   MSLSA retainer lawyers, April 2026
  jk_hc_advocate_list_2026-08.txt         J&K High Court, Bar Council roll "Advocate List as on August 2026"
  jk_jkslsa_panel_lawyers_2025-06.txt     JKSLSA panel lawyers, June 2025
  mp_mpslsa_panel_lawyers_2026-06.txt     MPSLSA panel lawyers, June 2026
  gujarat_hc_panel_advocates_2026-08-29.txt  Gujarat HC government / PSU panel advocates as on 29.08.2026
  chandigarh_slsa_panel_2026-10_a.txt     SLSA UT Chandigarh panel, Oct 2026
  chandigarh_phhc_arbitrators_advocates.txt, chandigarh_phhc_arbitrators_advocates_2.txt  P&H HC arbitrator-advocate panels
  ladakh_nalsa_list_of_panel_lawyers.html Ladakh legal services panel (HTML table)
--hp <dir>    hp_<letter>.json from the Himachal Pradesh HC "Advocate On Record" directory (adv_search_ajax.php)
--mphc <dir>  mp_<letter>_p<n>.html from the Madhya Pradesh HC advocates directory (advocates-details/search)
"""
import csv
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from outreach_build_contacts import clean_name, emails_in  # noqa: E402
from outreach_build_contacts_states import mobile_in  # noqa: E402

HON = r"(?:Shri|Smt|Sh|Mr|Mrs|Ms|Miss|Dr|Adv|Advocate|Md)\.?"
JK_TOWNS = {"jammu", "srinagar", "anantnag", "baramulla", "kathua", "udhampur", "rajouri", "poonch", "doda", "kishtwar", "ramban",
            "reasi", "samba", "budgam", "pulwama", "shopian", "kulgam", "ganderbal", "bandipora", "kupwara", "leh", "kargil"}
MP_TOWNS = {"jabalpur", "indore", "bhopal", "gwalior", "ujjain", "sagar", "rewa", "satna", "ratlam", "dewas", "chhindwara", "katni",
            "mandsaur", "vidisha", "sehore", "hoshangabad", "narmadapuram", "khandwa", "khargone", "burhanpur", "shivpuri", "guna",
            "morena", "bhind", "datia", "damoh", "tikamgarh", "chhatarpur", "panna", "sidhi", "singrauli", "shahdol", "umaria",
            "dindori", "mandla", "balaghat", "seoni", "betul", "harda", "neemuch", "shajapur", "rajgarh", "dhar", "jhabua", "alirajpur",
            "barwani", "anuppur", "niwari", "agar", "ashoknagar", "sheopur"}
HP_TOWNS = {"shimla", "mandi", "kangra", "dharamshala", "solan", "una", "hamirpur", "bilaspur", "chamba", "kullu", "sirmaur", "nahan",
            "kinnaur", "lahaul", "spiti", "palampur", "nurpur", "baddi", "parwanoo", "paonta"}


def town_in(text: str, towns: set[str]) -> str:
    for w in re.split(r"[^A-Za-z]+", text or ""):
        if w.lower() in towns:
            return w.title()
    return ""


# ─── Maharashtra SLSA (one row per advocate; the district is on the group's first row) ───
MSLSA_HON = re.compile(r"^(?:Adv\.?\s*)?(?:Shri|Smt|Ms|Mr|Mrs|Miss|Dr|Kum|Sou|Sow)\.?\s*|^Adv\.?\s*", re.I)
QUAL = re.compile(r"LL|L\.?\s?L\.?\s?B|B\.|^BA|BSL|M\.A|B\s?Com|LLM|GDC|^MA\b|^B\.?Sc|^M\.?Sc|LAW|^BE\b|^BBA|^BCA|^MBA", re.I)
ALPHA = re.compile(r"^[A-Za-z][A-Za-z .,'\-()]*$")


def parse_mslsa(text: str):
    """Fields split on 2+ spaces: [serial] [district] name [qualification] phone email dates gender."""
    district = ""
    for line in text.splitlines():
        if "@" not in line:
            continue
        fields = [f for f in re.split(r"\s{2,}", line.strip()) if f]
        idx = next((i for i, f in enumerate(fields) if "@" in f), None)
        if idx is None:
            continue
        j = idx - 1
        if j >= 0 and re.fullmatch(r"[\d ,/+-]+", fields[j]):
            j -= 1                                   # phone
        if j >= 0 and QUAL.search(fields[j]) and not MSLSA_HON.match(fields[j]):
            j -= 1                                   # qualification
        if j < 0 or not ALPHA.match(fields[j]):
            continue
        name = MSLSA_HON.sub("", fields[j])
        before = [f for f in fields[:j] if not re.fullmatch(r"\d+", f)]
        if before and ALPHA.match(before[-1]):
            district = before[-1]
        addrs = emails_in(fields[idx])
        if not addrs:
            continue
        mob = mobile_in(" ".join(fields[j + 1: idx]))
        hc = "HCLSC" in district.upper()
        city = re.sub(r"(?i)\b(HCLSC|DLSA|TLSC|district)\b|[,()]", " ", district)
        city = re.sub(r"\s+", " ", city).strip().title()
        court = "Bombay High Court" if hc else f"District Court, {city}" if city else ""
        yield addrs[0], clean_name(name), mob, city, court


# ─── J&K Bar Council roll ─────────────────────────────────────────────
JK_ROW = re.compile(r"^\s*\d+\s+([A-Za-z][A-Za-z .'\-]+?)\s{2,}(JK\S*|\S+)\s+&\s+[\d.]+\s+(.*)$")


def parse_jk_roll(text: str):
    for line in text.splitlines():
        m = JK_ROW.match(line)
        if not m or "Surrendered" in line or "@" not in line:
            continue
        addrs = emails_in(line)
        if addrs:
            rest = m.group(3)
            yield addrs[0], clean_name(m.group(1)), mobile_in(rest), town_in(rest, JK_TOWNS), "Jammu & Kashmir and Ladakh High Court"


# ─── JKSLSA panel ─────────────────────────────────────────────────────
def parse_jkslsa(text: str):
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if "@" not in ln:
            continue
        addrs = emails_in(ln)
        if not addrs:
            continue
        for j in range(i, max(-1, i - 3), -1):
            m = re.match(r"^\s*\d+\s+(?:Advocate|Adv|Mr|Ms|Mrs|Smt|Sh)\.?\s+([A-Za-z][A-Za-z .'\-]*?[a-z])(?=[A-Z0-9]|\s{2,}|\s+\d|\s*$)", lines[j])
            if m:
                window = " ".join(lines[j: i + 2])
                where = re.search(r"(HCLSC|DLSA|SLSA|TLSC)\s+([A-Za-z]+)", window)
                city = where.group(2).title() if where else ""
                court = "Jammu & Kashmir and Ladakh High Court" if where and where.group(1) == "HCLSC" else f"District Court, {city}" if city else ""
                yield addrs[0], clean_name(m.group(1)), mobile_in(window), city, court
                break


# ─── MPSLSA panel (rows wrap; email and name often on different lines) ───
MP_NAME = re.compile(r"\b(?:MISS|SHRIMATI|SHRI|SMT|MRS|MR|DR|KU|KUMARI|SH)\.?\s+([A-Za-z][A-Za-z .'\-]{2,}?)(?=\s{2,}|\s+\d|\s*$)", re.I)


def parse_mpslsa(text: str):
    lines = text.splitlines()
    names, mails = [], []
    for i, ln in enumerate(lines):
        m = MP_NAME.search(ln)
        if m and "@" not in m.group(1):
            name = m.group(1)
            # a wrapped second line of the name: same column start, letters only, no digits
            if i + 1 < len(lines):
                mm = re.match(r"^(\s+)([A-Za-z][A-Za-z .'\-]{2,}?)(?=\s{2,}|\s*$)", lines[i + 1])
                if mm and abs(len(mm.group(1)) - m.start(1)) <= 3 and not re.search(r"\d|@|HCLSC|DLSA|TLSC", lines[i + 1]):
                    name = f"{name} {mm.group(2)}"
            names.append((i, clean_name(name)))
        for addr in emails_in(ln):
            mails.append((i, addr))
            break
    used = set()
    for ni, name in names:
        best = None
        for mi, addr in mails:
            if mi in used or abs(mi - ni) > 3:
                continue
            if best is None or abs(mi - ni) < abs(best[0] - ni):
                best = (mi, addr)
        if best:
            used.add(best[0])
            mob = mobile_in(" ".join(lines[max(0, ni - 2): ni + 3]))
            where = " ".join(lines[max(0, ni - 2): ni + 3])
            hc = re.search(r"HCLSC\s+(JBP|IND|GWL)", where)
            city = {"JBP": "Jabalpur", "IND": "Indore", "GWL": "Gwalior"}.get(hc.group(1), "") if hc else town_in(where, MP_TOWNS)
            court = "Madhya Pradesh High Court" if hc else f"District Court, {city}" if city else ""
            yield best[1], name, mob, city, court


# ─── Gujarat HC government panel ──────────────────────────────────────
def parse_gujarat(text: str):
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if "@" not in ln:
            continue
        addrs = emails_in(ln)
        if not addrs:
            continue
        name = None
        for j in range(i, max(-1, i - 4), -1):
            m = re.search(rf"{HON}\s*([A-Z][A-Za-z .'\-]+?)\s{{2,}}", lines[j])
            if m and "M/s" not in lines[j]:
                name = clean_name(m.group(1))
                break
        if name:
            yield addrs[0], name, mobile_in(" ".join(lines[max(0, i - 2): i + 2])), "Ahmedabad", "Gujarat High Court"


# ─── Chandigarh SLSA panel ────────────────────────────────────────────
def parse_chd_slsa(text: str):
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if "@" not in ln:
            continue
        addrs = emails_in(ln)
        if not addrs:
            continue
        for j in range(i, max(-1, i - 3), -1):
            m = re.match(rf"^\s*\d+\s+{HON}\s+([A-Za-z][A-Za-z .'\-]+?)\s{{2,}}", lines[j])
            if m:
                yield addrs[0], clean_name(m.group(1)), mobile_in(" ".join(lines[max(0, i - 2): i + 3])), "Chandigarh", "Punjab & Haryana High Court"
                break


# ─── P&H HC arbitrator-advocate panels (name wraps in the first column) ───
def parse_phhc_arbitrators(text: str):
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines) if re.match(r"^\d+\.?\s+[A-Z]", ln)]
    for k, s0 in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(lines)
        block = lines[s0:e]
        frags = []
        for ln in block[:4]:
            frag = re.sub(r"^\d+\.?\s*", "", ln[:22]).strip()
            if not frag or re.search(r"\d|@", frag):
                break
            if re.match(r"Advocate", frag):
                break
            frags.append(frag.rstrip(","))
        name = re.sub(r"^(?:Colonel|Col|Capt|Major|Sh|Ms|Mrs|Mr|Smt|Dr)\.?\s+", "", " ".join(frags))
        addrs = emails_in(" ".join(block))
        if addrs and name:
            where = " ".join(block)
            city = "Mohali" if "Mohali" in where else "Panchkula" if "Panchkula" in where else "Mumbai" if "Mumbai" in where or "Mumabi" in where else "Chandigarh"
            yield addrs[0], clean_name(name), mobile_in(where), city, "Punjab & Haryana High Court"


# ─── Ladakh HTML table ────────────────────────────────────────────────
def parse_ladakh(text: str):
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S | re.I):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S | re.I)]
        if len(cells) < 7:
            continue
        addr = cells[4].replace("[at]", "@").replace("[dot]", ".").replace(" ", "")
        addrs = emails_in(addr)
        if addrs:
            city = "Kargil" if "Kargil" in cells[6] else "Leh"
            yield addrs[0], clean_name(re.sub(r"^Adv\.?\s+", "", cells[1])), mobile_in(cells[3]), city, "Jammu & Kashmir and Ladakh High Court"


# ─── Himachal Pradesh HC directory (JSON with an HTML table) ──────────
def parse_hp(files: list[Path]):
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8", errors="replace")).get("data", "")
        except json.JSONDecodeError:
            continue
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", data, flags=re.S | re.I):
            cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S | re.I)]
            if len(cells) < 4:
                continue
            addrs = emails_in(cells[3])
            if addrs:
                city = town_in(cells[4] if len(cells) > 4 else "", HP_TOWNS)
                yield addrs[0], clean_name(cells[1]), mobile_in(cells[2]), city, "Himachal Pradesh High Court"


# ─── Madhya Pradesh HC directory (HTML table fragments) ───────────────
def parse_mphc(files: list[Path]):
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S | re.I):
            cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S | re.I)]
            if len(cells) < 7:
                continue
            addrs = emails_in(cells[6])
            if addrs:
                city = town_in(cells[7] if len(cells) > 7 else "", MP_TOWNS)
                yield addrs[0], clean_name(cells[1]), mobile_in(cells[5]), city, "Madhya Pradesh High Court"


SOURCES = [
    ("maharashtra_mslsa_panel_b_2025-11.txt", parse_mslsa, "the Maharashtra State Legal Services Authority's list of panel advocates, April 2026 (maharashtra.nalsa.gov.in)"),
    ("maharashtra_mslsa_panel_a_2025-11.txt", parse_mslsa, "the Maharashtra State Legal Services Authority's list of retainer lawyers, April 2026 (maharashtra.nalsa.gov.in)"),
    ("jk_hc_advocate_list_2026-08.txt", parse_jk_roll, "the High Court of Jammu & Kashmir and Ladakh's advocate list as on August 2026 (jkhighcourt.nic.in)"),
    ("jk_jkslsa_panel_lawyers_2025-06.txt", parse_jkslsa, "the J&K State Legal Services Authority's panel of lawyers, June 2025 (jammukashmir.nalsa.gov.in)"),
    ("mp_mpslsa_panel_lawyers_2026-06.txt", parse_mpslsa, "the Madhya Pradesh State Legal Services Authority's list of panel lawyers, June 2026 (madhyapradesh.nalsa.gov.in)"),
    ("gujarat_hc_panel_advocates_2026-08-29.txt", parse_gujarat, "the Gujarat High Court's list of panel advocates for Government and public bodies as on 29.08.2026 (gujarathighcourt.nic.in)"),
    ("chandigarh_slsa_panel_2026-10_a.txt", parse_chd_slsa, "the State Legal Services Authority, UT Chandigarh's panel of advocates (chandigarh.nalsa.gov.in)"),
    ("chandigarh_phhc_arbitrators_advocates.txt", parse_phhc_arbitrators, "the Punjab & Haryana High Court's panel of advocates as arbitrators, 2025 (highcourtchd.gov.in)"),
    ("chandigarh_phhc_arbitrators_advocates_2.txt", parse_phhc_arbitrators, "the Punjab & Haryana High Court's panel of advocates as arbitrators, 2022 (highcourtchd.gov.in)"),
    ("ladakh_nalsa_list_of_panel_lawyers.html", parse_ladakh, "the Ladakh Legal Services Authority's panel of lawyers (ladakh.nalsa.gov.in)"),
]


def main() -> None:
    args = sys.argv[1:]
    hp_dir = Path(args[args.index("--hp") + 1]) if "--hp" in args else None
    mphc_dir = Path(args[args.index("--mphc") + 1]) if "--mphc" in args else None
    src, out = Path(args[0]), Path(args[1])
    rows, seen = [], set()

    def add(addr, name, mobile, city, court, source):
        if addr in seen:
            return False
        if not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{3,44}", name or "") or re.search(r"\b(Mr|Ms|Mrs|Dr|Ch|Counsel|Sh|Smt|Shri|Sri|Miss|Advocate)\b", name or ""):
            name = ""
        seen.add(addr)
        rows.append({"email": addr, "name": f"Adv. {name}" if name else "", "mobile": mobile or "", "city": city or "",
                     "court": court, "source": source})
        return True

    for fname, parser, source in SOURCES:
        path = src / fname
        if not path.exists():
            print(f"{fname:46} missing")
            continue
        n = sum(add(*rec, source) for rec in parser(path.read_text(encoding="utf-8", errors="replace")))
        print(f"{fname:46} {n:6}")
    if hp_dir:
        n = sum(add(*rec, "the Himachal Pradesh High Court's Advocate On Record directory (highcourt.hp.gov.in)") for rec in parse_hp(sorted(hp_dir.glob("hp_*.json"))))
        print(f"{'HP High Court directory':46} {n:6}")
    if mphc_dir:
        n = sum(add(*rec, "the Madhya Pradesh High Court's advocates directory (mphc.gov.in)") for rec in parse_mphc(sorted(mphc_dir.glob("mp_*_p*.html"))))
        print(f"{'MP High Court directory':46} {n:6}")
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["email", "name", "mobile", "city", "court", "source"])
        w.writeheader()
        w.writerows(rows)
    print(f"total {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
