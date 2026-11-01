"""Outreach CSV for the northern states from official lists (second batch, 1 Nov 2026).

    python3 -I scripts/outreach_build_contacts_states.py <ahc_roll_dir> <states_dir> <out.csv>

<ahc_roll_dir>  roll_NNN.html pages of the Allahabad High Court's Roll of Advocates [Part-A]
                (https://www.allahabadhighcourt.in/advocate/generateRollA.jsp?page=N, 100 per page)
<states_dir>    pdftotext -layout output of
                  up_ahc_lucknow_counsel_event19030_2024-06.txt  Allahabad HC: State standing counsel for
                        advance notice, Lucknow Bench (allahabadhighcourt.in/event/event_19030_27-06-2024.pdf)
                  hr_hslsa_panel_advocates_2025-08.txt           Haryana SLSA panel of advocates (hslsa.gov.in)
Columns: email,name,mobile,city,court,source. Office mailboxes are left out; one address per person.
"""
import csv
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from outreach_build_contacts import clean_name, emails_in  # noqa: E402

SRC_ROLL = "the Allahabad High Court's Roll of Advocates, Part-A (allahabadhighcourt.in)"
SRC_LKO = "the Allahabad High Court's directory of standing counsel for advance notice to the State, Lucknow Bench (allahabadhighcourt.in, June 2024)"
SRC_HSLSA = "the Haryana State Legal Services Authority's panel of advocates (hslsa.gov.in, 2025)"
OFFICE_LOCAL = re.compile(r"^(csc|cschc|asg|ag[._-]|office|chamber[s]?of|legalcell|dlsa|slsa|hclsc|secy)", re.I)
MOBILE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?([6-9]\d{9})(?!\d)")


def mobile_in(text: str) -> str | None:
    # Join only a mobile printed in two halves ('97172 68371', '98642-48331', '9864 054 183'); never digits of
    # neighbouring columns ('769/89   9419193047' must stay apart).
    text = re.sub(r"(?<!\d)(\d{5})[\s-](\d{5})(?!\d)", r"\1\2", text)
    text = re.sub(r"(?<!\d)(\d{4})[\s-](\d{3})[\s-](\d{3})(?!\d)", r"\1\2\3", text)
    m = MOBILE.search(text)
    return m.group(1) if m else None


def cells_of(row_html: str) -> list[str]:
    return [html.unescape(re.sub(r"<[^>]+>", "|", c)) for c in re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.S | re.I)]


def parse_roll(pages: list[Path]):
    """Each row: S.N. | roll no, name, father | enrolment | date | address | telephones | e-mail | remark."""
    for page in pages:
        text = page.read_text(encoding="utf-8", errors="replace")
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S | re.I):
            cells = cells_of(row)
            if len(cells) < 7:
                continue
            ident = [p.strip() for p in cells[1].split("|") if p.strip()]
            if len(ident) < 2 or not re.match(r"^[A-Z]/", ident[0]):
                continue
            name = clean_name(ident[1])
            addrs = emails_in(cells[6])
            if not addrs:
                continue
            phones = cells[5].split("3.Mobile:")[-1] if "3.Mobile:" in cells[5] else ""
            res = cells[4].split("2.Office:")[0] if "2.Office:" in cells[4] else cells[4]
            city = city_of(res)
            yield addrs[0], name, mobile_in(phones), city


UP_TOWNS = {"lucknow", "kanpur", "varanasi", "gorakhpur", "agra", "meerut", "noida", "ghaziabad", "bareilly", "jhansi",
            "mirzapur", "jaunpur", "pratapgarh", "kaushambi", "fatehpur", "sultanpur", "azamgarh", "basti", "faizabad",
            "ayodhya", "deoria", "ballia", "mau", "aligarh", "mathura", "moradabad", "saharanpur", "delhi", "bhadohi",
            "chitrakoot", "banda", "hamirpur", "unnao", "raebareli", "barabanki", "sitapur", "hardoi", "etawah", "mainpuri",
            "firozabad", "ghazipur", "chandauli", "sonbhadra", "ambedkarnagar", "gonda", "bahraich", "shahjahanpur", "budaun"}


def city_of(address: str) -> str:
    """Prayagraj for an Allahabad/Prayagraj address; otherwise a known UP town named in it; else blank."""
    text = re.sub(r"\|+", " ", address).replace("1.Residence:", "")
    if re.search(r"allahabad|prayagraj|\balld\b|naini|jhunsi|phaphamau", text, re.I):
        return "Prayagraj"
    for w in re.split(r"[^A-Za-z]+", text):
        if w.lower() in UP_TOWNS:
            return "New Delhi" if w.lower() == "delhi" else w.title()
    return ""


def parse_lucknow(text: str):
    """Entries start '(N). Mr. Name,' then email lines, then a 'Mob.' line, then the bodies represented."""
    name, buf = None, []

    def flush():
        if name:
            body = " ".join(buf)
            addrs = [a for a in emails_in(body) if not OFFICE_LOCAL.match(a.split("@")[0])]
            mob = mobile_in(" ".join(ln for ln in buf if re.search(r"Mob", ln)))
            if addrs:
                yield addrs[0], name, mob

    for line in text.splitlines():
        m = re.match(r"^\s*\((\d+)\)\.?\s*(.+?)\s*,?\s*$", line)
        if m and re.search(r"[A-Za-z]", m.group(2)) and "@" not in m.group(2):
            yield from flush()
            name, buf = clean_name(m.group(2)), []
            continue
        if name:
            buf.append(line)
    yield from flush()


def parse_hslsa(text: str):
    for line in text.splitlines():
        m = re.match(r"^\s*\d+\.\s+(\S.*?)\s{2,}((?:\+?91[\s-]?)?[6-9]\d{9})\s+(\S+@\S+)\s*$", line)
        if m:
            addrs = emails_in(m.group(3))
            if addrs:
                yield addrs[0], clean_name(m.group(1)), mobile_in(m.group(2))


def main() -> None:
    roll_dir, states_dir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    rows, seen = [], set()

    def add(addr, name, mobile, city, court, source):
        if addr in seen:
            return False
        if not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{3,44}", name or "") or re.search(r"\b(Mr|Ms|Mrs|Dr|Ch|Counsel|Sh|Smt)\b", name or ""):
            name = ""
        seen.add(addr)
        rows.append({"email": addr, "name": f"Adv. {name}" if name else "", "mobile": mobile or "", "city": city or "",
                     "court": court, "source": source})
        return True

    n = sum(add(a, nm, mob, city, "Allahabad High Court", SRC_ROLL) for a, nm, mob, city in parse_roll(sorted(roll_dir.glob("roll_*.html"))))
    print(f"Allahabad roll          {n:6} ({len(list(roll_dir.glob('roll_*.html')))} pages)")
    lko = (states_dir / "up_ahc_lucknow_counsel_event19030_2024-06.txt").read_text(encoding="utf-8", errors="replace")
    n = sum(add(a, nm, mob, "Lucknow", "Allahabad High Court, Lucknow Bench", SRC_LKO) for a, nm, mob in parse_lucknow(lko))
    print(f"Lucknow standing counsel {n:5}")
    hs = (states_dir / "hr_hslsa_panel_advocates_2025-08.txt").read_text(encoding="utf-8", errors="replace")
    n = sum(add(a, nm, mob, "Panchkula", "Haryana State Legal Services Authority panel", SRC_HSLSA) for a, nm, mob in parse_hslsa(hs))
    print(f"Haryana SLSA panel      {n:6}")
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["email", "name", "mobile", "city", "court", "source"])
        w.writeheader()
        w.writerows(rows)
    print(f"total {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
