"""Outreach CSV from official lists of law officers, panel counsel, mediators, trade mark agents and law
faculty (2 Nov 2026).

    python3 -I scripts/outreach_build_contacts_professions.py <professions_dir> <faculty_dir> <out.csv>

<professions_dir> (pdftotext -layout .txt files; URLs in docs/OUTREACH.md → Sources):
  lawofficer_legalaffairs_consolidated_panel_counsel_2026.txt  DoLA, consolidated Union of India panel counsel (Apr 2026):
        the email sits on its own line above the serial row (sometimes wrapped over two lines)
  lawofficer_legalaffairs_new_LOs_2025.txt, lawofficer_legalaffairs_new_DSGI_list.txt  law officers (ASGs, DSGIs)
  mediator_hpslsa_d*.txt, ladc_hpslsa_pl*.txt                HP SLSA trained mediators / panel of legal practitioners
  slsa_rajasthan_mediators_1.txt                             Rajasthan SLSA mediators (email wraps to the next line)
  slsa_more/karnataka_*.txt, slsa_more/delhi_*.txt, slsa_more/assam_*.txt   panel lawyers by district
  tmagent_ipindia_list_2020.txt                              IP India, trade marks agents as of 30.11.2020
  lawofficer_odisha_law_node20024.html                       Odisha Law Department, law officers (HTML table)
<faculty_dir>: saved faculty pages (nlsiu_*.html, hpnlu_staff4.html, dbranlu_members.html, ili_facultydetails.html,
  tnnlu_faculty2.html, dnlu_directory.pdf.txt, persons/<inst>_*.html).
Judicial officers (serving or retired, as labelled) are left out; shared mailboxes recurring 3+ times are dropped.
"""
import csv
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from outreach_build_contacts import clean_name, emails_in  # noqa: E402
from outreach_build_contacts_district import NAME_FIELD, NOT_NAMES  # noqa: E402
from outreach_build_contacts_states import mobile_in  # noqa: E402

HON = re.compile(r"^(?:(?:Adv|Advocate|Sh|Shri|Smt|Mr|Ms|Mrs|Miss|Dr|Ku|Kum|Km|Sri|Prof|Senior Prof)(?:\.\s*|\s+)(?:\(Dr\.?\)\s*)?)+", re.I)
GLUED = re.compile(r"^(?:na)?(?:[6-9]\d{9}|\d{6})(?=[A-Za-z])|^na(?=adv)")  # a mobile, PIN or 'NA' printed hard against the address


def fix_glued(addr: str) -> str:
    local, _, domain = addr.partition("@")
    return f"{GLUED.sub('', local)}@{domain}"


JUDICIAL = re.compile(r"judicial officer|J\.O\b|Rtd|Retd|Retired|Judge|Justice|Magistrate|Registrar", re.I)
EMAIL_FULL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}")


def join_wrapped(lines: list[str]) -> list[str]:
    """Re-join an address split over two lines: '…@gm' + 'ail.com', 'xyz.advo' + 'cate@gmail.com'."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        tok = re.search(r"(\S*@\S*)\s*$", ln)
        if tok and not EMAIL_FULL.search(tok.group(1)) and re.match(r"^\s*[A-Za-z0-9.@][A-Za-z0-9.@_-]*\s*$", nxt):
            out.append(ln.rstrip() + nxt.strip())
            i += 2
            continue
        m2 = re.match(r"^\s*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|[A-Za-z0-9._-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\s*$", nxt)
        if m2 and re.fullmatch(r"\s*[A-Za-z0-9._-]{2,}\s*", ln) and (nxt.strip().startswith("@") or "." not in nxt.split("@")[0]):
            out.append(ln.strip() + nxt.strip())
            i += 2
            continue
        out.append(ln)
        i += 1
    return out


def first_name_field(fields: list[str]) -> str | None:
    for f in fields:
        f = re.sub(r"^\d+\.?\s+", "", f)
        if "@" in f or re.search(r"\d", f):
            continue
        f_clean = re.sub(r"\s+Advocate\.?$", "", HON.sub("", f).strip(), flags=re.I)
        if NAME_FIELD.match(f_clean) and not NOT_NAMES.match(f_clean) and len(f_clean.split()) <= 6 and not re.search(r"\b(DLSA|TLSC|SDLSC|High Court|District|Courts?|Counsel|Pleader|Advocate General|Male|Female)\b", f_clean):
            return clean_name(f_clean)
    return None


def rows_with_email(text: str, *, name_above: bool = False, skip: re.Pattern | None = None):
    lines = join_wrapped(text.splitlines())
    for i, ln in enumerate(lines):
        if "@" not in ln or (skip and skip.search(ln)):
            continue
        addrs = emails_in(ln)
        if not addrs:
            continue
        fields = [f.strip() for f in re.split(r"\s{2,}", ln.strip()) if f.strip()]
        name = first_name_field(fields)
        if name is None and name_above:
            for j in range(i - 1, max(-1, i - 3), -1):
                cand = first_name_field([f.strip() for f in re.split(r"\s{2,}", lines[j].strip()) if f.strip()])
                if cand:
                    name = cand
                    break
        yield addrs[0], name, mobile_in(ln), ln


def parse_consolidated(text: str):
    """DoLA consolidated panel counsel: each serial row has an address block (with the email) printed above or
    below it, depending on the page; every email is given to the nearest serial row, once."""
    lines = join_wrapped(text.splitlines())
    row_re = re.compile(r"^\s*\d+\s+([A-Za-z][A-Za-z .'\-]+?)\s{2,}(?=[A-Z0-9][A-Za-z0-9/.() -]*\d|.*\b(?:Counsel|Pleader|Panel|Advocate)\b)")
    rows = {i: m for i, ln in enumerate(lines) if (m := row_re.match(ln))}
    row_idx = sorted(rows)
    taken: dict[int, str] = {}
    import bisect
    for i, ln in enumerate(lines):
        if i in rows or "@" not in ln:
            continue
        cand = emails_in(ln)
        if not cand:
            continue
        pos = bisect.bisect_left(row_idx, i)
        above = row_idx[pos - 1] if pos > 0 else None
        below = row_idx[pos] if pos < len(row_idx) else None
        choices = sorted([r for r in (above, below) if r is not None and abs(r - i) <= 8 and r not in taken], key=lambda r: (abs(r - i), -r))
        if choices:
            taken[choices[0]] = fix_glued(cand[0])
    for i, email in taken.items():
        ln, m = lines[i], rows[i]
        fields = [f.strip() for f in re.split(r"\s{2,}", ln.strip()) if f.strip()]
        court = next((f for f in fields if re.search(r"Supreme Court|High Court|District Courts?|Tribunal|CAT\b|Commission|Forum|NCLT|NCLAT|AFT\b|DRT\b|Authority", f)
                      and not re.search(r"\d|,|Chamber|Block|Road|Nagar", f)), "")
        state = district = ""
        if court:
            k = next(idx for idx, f in enumerate(fields) if f == court)
            nxt = [f for f in fields[k + 1:k + 3] if not re.search(r"\d|Court|,", f)]
            state = nxt[0] if nxt else ""
            district = nxt[1] if len(nxt) > 1 else ""
        city = district or ("New Delhi" if "Supreme Court" in court or "Delhi" in court else "")
        yield email, clean_name(m.group(1)), mobile_in(ln), city, court or state, state


def html_lines(path: Path) -> list[str]:
    s = path.read_text(encoding="utf-8", errors="replace")
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</(p|div|li|tr|td|th|h\d|span|a|strong|em|dd|dt)>", "\n", s, flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("[at]", "@").replace("[dot]", ".").replace(" (at) ", "@")
    return [re.sub(r"\s+", " ", ln).strip() for ln in s.splitlines() if ln.strip()]


DESIGNATION = re.compile(r"professor|lecturer|dean|director|registrar|fellow|faculty|assistant|associate|vice|chancellor|head|librarian|officer|coordinator|research|visiting|adjunct|emeritus|scholar|teacher|view profile|email|phone|mobile|intercom|click", re.I)


def parse_faculty_lines(lines: list[str]):
    """Each email with the nearest preceding person-name line (honorific or 2–5 capitalised words)."""
    for i, ln in enumerate(lines):
        addrs = emails_in(ln)
        if not addrs:
            continue
        name = None
        for j in range(i - 1, max(-1, i - 6), -1):
            cand = lines[j]
            if DESIGNATION.search(cand) and not HON.match(cand):
                continue
            c = HON.sub("", cand).strip()
            if re.fullmatch(r"[A-Z][A-Za-z.'\-]+(?: [A-Z][A-Za-z.'\-]+){1,4}", c) and not NOT_NAMES.match(c):
                name = clean_name(c)
                break
        yield addrs[0], name


FACULTY = [
    ("nlsiu_facultylist.html", "National Law School of India University, Bengaluru", "Bengaluru", "the National Law School of India University's faculty directory (nls.ac.in)"),
    ("nlsiu_visiting.html", "National Law School of India University, Bengaluru", "Bengaluru", "the National Law School of India University's visiting faculty directory (nls.ac.in)"),
    ("nlsiu_researchers.html", "National Law School of India University, Bengaluru", "Bengaluru", "the National Law School of India University's researchers directory (nls.ac.in)"),
    ("hpnlu_staff4.html", "Himachal Pradesh National Law University, Shimla", "Shimla", "the Himachal Pradesh National Law University's faculty directory (hpnlu.ac.in)"),
    ("dbranlu_members.html", "Dr. B.R. Ambedkar National Law University, Sonipat", "Sonipat", "the Dr. B.R. Ambedkar National Law University's faculty directory (dbranlu.ac.in)"),
    ("ili_facultydetails.html", "Indian Law Institute, New Delhi", "New Delhi", "the Indian Law Institute's faculty directory (ili.ac.in)"),
    ("dnlu_directory.pdf.txt", "Dharmashastra National Law University, Jabalpur", "Jabalpur", "the Dharmashastra National Law University's directory of faculty (mpdnlu.ac.in)"),
]
PERSON_PAGES = {
    "nluo": ("National Law University Odisha, Cuttack", "Cuttack", "the National Law University Odisha's faculty pages (nluo.ac.in)"),
    "nujs": ("West Bengal National University of Juridical Sciences, Kolkata", "Kolkata", "the WB National University of Juridical Sciences' faculty pages (nujs.edu)"),
    "nusrl": ("National University of Study and Research in Law, Ranchi", "Ranchi", "the National University of Study and Research in Law's faculty pages (nusrlranchi.ac.in)"),
    "nluj": ("National Law University, Jodhpur", "Jodhpur", "the National Law University Jodhpur's faculty pages (nlujodhpur.ac.in)"),
    "gnlu": ("Gujarat National Law University, Gandhinagar", "Gandhinagar", "the Gujarat National Law University's faculty pages (gnlu.ac.in)"),
    "nlutripura": ("National Law University Tripura, Agartala", "Agartala", "the National Law University Tripura's faculty pages (nlutripura.ac.in)"),
}
GENERIC_LOCAL_EXTRA = re.compile(r"^(director|registrar|dean|office|admin|info|contact|library|exam|academics?|placement|ipr|vc|hod|dsw|principal|secretary|chairman|accounts|estate|hostel|warden|it|webmaster|helpdesk|enquiry|nlu|law|faculty|dept|department|cs|cse|english|economics|sociology|history|political|management)\d*$", re.I)


def main() -> None:
    prof, fac, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    rows, seen = [], set()

    def add(addr, name, mobile, city, court, source):
        addr = fix_glued(addr)
        if addr in seen or len(addr.split("@")[0]) < 3 or GENERIC_LOCAL_EXTRA.match(addr.split("@")[0]):
            return 0
        if not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{3,44}", name or "") or NOT_NAMES.match(name or ""):
            name = ""
        seen.add(addr)
        rows.append({"email": addr, "name": f"Adv. {name}" if name and "faculty" not in source and "directory" not in source else name,
                     "mobile": mobile or "", "city": city or "", "court": court or "", "source": source[:300]})
        return 1

    def report(label, n):
        print(f"{label[:62]:62} {n:6}")

    # Consolidated Union of India panel counsel
    p = prof / "lawofficer_legalaffairs_consolidated_panel_counsel_2026.txt"
    if p.exists():
        n = 0
        for email, name, mob, city, court, state in parse_consolidated(p.read_text(encoding="utf-8", errors="replace")):
            n += add(email, name, mob, city, court, "the Department of Legal Affairs' consolidated list of panel counsel for the Union of India, April 2026 (legalaffairs.gov.in)")
        report("DoLA consolidated panel counsel", n)
    # Row-style lists
    for pattern, court, city, source, kw in (
        ("lawofficer_legalaffairs_new_LOs_2025.txt", "Supreme Court of India", "New Delhi", "the Department of Legal Affairs' list of Law Officers, August 2026 (legalaffairs.gov.in)", {}),
        ("lawofficer_legalaffairs_new_DSGI_list.txt", "High Court", "", "the Department of Legal Affairs' list of Deputy Solicitors General in the High Courts, August 2026 (legalaffairs.gov.in)", {}),
        ("mediator_hpslsa_d*.txt", "District Legal Services Authority, Himachal Pradesh", "", "the Himachal Pradesh State Legal Services Authority's lists of trained mediators (himachalpradesh.nalsa.gov.in)", {"skip": JUDICIAL}),
        ("ladc_hpslsa_pl*.txt", "District Legal Services Authority, Himachal Pradesh", "", "the Himachal Pradesh State Legal Services Authority's district panels of legal practitioners (himachalpradesh.nalsa.gov.in)", {}),
        ("slsa_rajasthan_mediators_1.txt", "District Legal Services Authority, Rajasthan", "", "the Rajasthan State Legal Services Authority's list of mediators, November 2025 (rajasthan.nalsa.gov.in)", {"skip": JUDICIAL}),
        ("slsa_more/karnataka_*.txt", "District Legal Services Authority, Karnataka", "", "the Karnataka State Legal Services Authority's district panels of lawyers (karnataka.nalsa.gov.in)", {"name_above": True}),
        ("slsa_more/delhi_*.txt", "Delhi State Legal Services Authority panel", "New Delhi", "the Delhi State Legal Services Authority's panel lists (dslsa.org)", {}),
        ("slsa_more/assam_*.txt", "District Legal Services Authority, Assam", "", "the Assam State Legal Services Authority's district panels of lawyers (assam.nalsa.gov.in)", {}),
        ("tmagent_ipindia_list_2020.txt", "Trade Marks Registry", "", "the Controller General of Patents, Designs and Trade Marks' list of trade marks agents as of 30.11.2020 (ipindia.gov.in)", {}),
    ):
        n = 0
        for path in sorted(prof.glob(pattern)):
            text = path.read_text(encoding="utf-8", errors="replace")
            found = list(rows_with_email(text, **kw))
            shared = {a for a, c in Counter(a for a, *_ in found).items() if c >= 3}
            place = city
            if not place:
                m = re.search(r"(?:DLSA|District Legal Services Authority|TLSC)[, ]+([A-Z][A-Za-z]+)", text)
                place = m.group(1) if m else ""
            for addr, name, mob, ln in found:
                if addr in shared:
                    continue
                row_city = place
                rm = re.search(r"\b(?:DLSA|TLSC|SDLSC)[, ]+(?:at\s+)?([A-Z][A-Za-z]+)", ln)
                if rm:
                    row_city = rm.group(1)
                if "trade marks" in source:
                    cm = re.search(r"\b(Delhi|New Delhi|Mumbai|Chennai|Kolkata|Bengaluru|Bangalore|Hyderabad|Pune|Ahmedabad|Coimbatore|Jaipur|Lucknow|Chandigarh|Kochi|Nagpur|Indore|Surat|Vadodara|Gurgaon|Gurugram|Noida)\b", ln)
                    row_city = cm.group(1) if cm else ""
                n += add(addr, name, mob, row_city, court, source)
        report(pattern, n)
    # Odisha law officers (HTML table)
    p = prof / "lawofficer_odisha_law_node20024.html"
    if p.exists():
        n = 0
        s = p.read_text(encoding="utf-8", errors="replace")
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", s, flags=re.S | re.I):
            cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S | re.I)]
            addrs = emails_in(" ".join(cells))
            if cells and addrs:
                n += add(addrs[0], first_name_field(cells), mobile_in(" ".join(cells)), "Cuttack", "Orissa High Court",
                         "the Odisha Law Department's list of law officers (law.odisha.gov.in)")
        report("Odisha law officers", n)
    # Faculty: one-page directories
    for fname, inst, city, source in FACULTY:
        p = fac / fname
        if not p.exists():
            continue
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines() if fname.endswith(".txt") else html_lines(p)
        lines = [ln.replace("&#64;", "@") for ln in lines]
        n = 0
        if fname.endswith(".txt"):
            for addr, name, mob, ln in rows_with_email("\n".join(lines)):
                n += add(addr, name, mob, city, inst, source)
        else:
            for addr, name in parse_faculty_lines(lines):
                n += add(addr, name, None, city, inst, source)
        report(fname, n)
    # TNNLU: JSON blob in the page
    p = fac / "tnnlu_faculty2.html"
    if p.exists():
        s = p.read_text(encoding="utf-8", errors="replace")
        n = 0
        for m in re.finditer(r'"name"\s*:\s*"([^"]+)"[^{}]*?"email"\s*:\s*"([^"]+)"', s):
            addrs = emails_in(m.group(2))
            if addrs:
                n += add(addrs[0], clean_name(m.group(1).title()), None, "Tiruchirappalli", "Tamil Nadu National Law University, Tiruchirappalli",
                         "the Tamil Nadu National Law University's faculty directory (tnnlu.ac.in)")
        report("tnnlu_faculty2.html", n)
    # Faculty: per-person pages
    for prefix, (inst, city, source) in PERSON_PAGES.items():
        n = 0
        for p in sorted((fac / "persons").glob(f"{prefix}_*.html")):
            lines = html_lines(p)
            got = list(parse_faculty_lines(lines))
            if got:
                addr, name = got[0]
                if not name:
                    t = re.search(r"<title>([^<|]+)", p.read_text(encoding="utf-8", errors="replace"))
                    name = clean_name(HON.sub("", t.group(1).split(" - ")[0]).strip()) if t else None
                n += add(addr, name, None, city, inst, source)
        report(f"persons/{prefix}_*", n)

    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["email", "name", "mobile", "city", "court", "source"])
        w.writeheader()
        w.writerows(rows)
    print(f"total {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
