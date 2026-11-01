"""Build the outreach CSV (email,name,city,court,source) from official public lists.

    python3 -I scripts/outreach_build_contacts.py <src_dir> <out.csv>

First download the PDFs into <src_dir> and run `pdftotext -layout x.pdf x.txt` on each
(URLs and the 31 Oct 2026 import are recorded in docs/OUTREACH.md, "Sources").
Then upload <out.csv> in Platform admin -> Outreach, or import it on the server with
`service.import_contacts`. Sources (pdftotext -layout output in <src_dir>):
  sc_aor_2026.txt           Supreme Court of India, List of Advocates-on-Record as on 09.10.2026
  dhc_nominated_counsel.txt Delhi High Court, nominated counsel for the Union of India (DLA letter 11.09.2025)
  scba_life.txt             Supreme Court Bar Association, life members directory
Rows are de-duplicated by address (first source wins, in the order above); official
role mailboxes (gov.in / nic.in, info@, office@ ...) are left out.
"""
import csv
import re
import sys
from pathlib import Path

EMAIL = re.compile(r"(?<![A-Za-z0-9,/])([A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,})")
GENERIC_LOCAL = {"info", "office", "contact", "admin", "mail", "enquiry", "enquiries", "legal", "support", "advocateonrecord", "advocate", "advocates", "law", "lawyer", "lawyers"}
SKIP_DOMAINS = (".gov.in", ".nic.in", "gov.in", "nic.in")

SRC_AOR = "the Supreme Court of India's List of Advocates-on-Record as on 09.10.2026 (sci.gov.in)"
SRC_DHC = "the Delhi High Court's list of counsel nominated for the Union of India (Ministry of Law & Justice letter dated 11.09.2025, delhihighcourt.nic.in)"
SRC_SCBA = "the Supreme Court Bar Association's life members directory (scbaindia.org)"


def fix_spacing(line: str) -> str:
    """'GMAIL. COM' -> 'GMAIL.COM', 'E-MAIL:x' labels dropped."""
    line = re.sub(r"\.\s+(com|in|org|net|co|edu)\b", r".\1", line, flags=re.I)
    line = re.sub(r"\b(e-?\.?\s*mail|email id|e)\s*[:.\-]+\s*", " ", line, flags=re.I)
    return line


def emails_in(line: str) -> list[str]:
    out = []
    for m in EMAIL.finditer(fix_spacing(line)):
        addr = m.group(1).lower().rstrip(".")
        addr = re.sub(r"@(gmail|yahoo|hotmail|rediffmail|outlook)\.co$", r"@\1.com", addr)  # a truncated '.com'
        local, _, domain = addr.partition("@")
        if domain.endswith(SKIP_DOMAINS) or local in GENERIC_LOCAL:
            continue
        out.append(addr)
    return out


def title_case(name: str) -> str:
    def word(w: str) -> str:
        if re.fullmatch(r"[A-Za-z]\.?", w) or re.fullmatch(r"(?:[A-Za-z]\.)+[A-Za-z]?\.?", w):  # initials: A., A.D., a.p.n.
            return w.upper()
        return "-".join(p[:1].upper() + p[1:].lower() for p in w.split("-"))
    return " ".join(word(w) for w in name.split())


def clean_name(raw: str) -> str:
    raw = re.sub(r"^\s*\d+\.?\s+", "", raw)
    raw = re.sub(r"^(Sh\.?|Shri|Smt\.?|Ms\.?|Mr\.?|Mrs\.?|Dr\.?|Sri)\s+", "", raw, flags=re.I)
    raw = re.sub(r"\(.*?\)", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" ,.-")
    return title_case(raw) if raw.isupper() or raw.islower() else raw


# ─── Supreme Court AOR list ───────────────────────────────────────────
AOR_TAG = re.compile(r"^(.*?)\((?:[^()]*?,\s*)?(?:Sr\.?\s*)?Advocate\s*\)")
AOR_HON = re.compile(r"^\s*(?:\d+\s+)?(?:Mr|Ms|Mrs|Dr|Sh|Smt|Shri)\.?\s+([A-Za-z][A-Za-z .'\-]{2,60})\s*$")


def parse_aor(text: str):
    """Older entries tag the name '(Advocate)'; newer ones start with 'Mr./Ms. Name'.
    Contact lines follow until the next name. Entries remarked 'Expired' are skipped."""
    blocks, current = [], None
    for line in text.splitlines():
        m = AOR_TAG.search(line)
        if m:
            left = re.sub(r"^\s*\d+\s+", "", m.group(1))
            left = re.sub(r"^\s*(Sh|Smt|Ms|Mr|Mrs|Dr)\.?\s+", "", left)
            current = [clean_name(left), []]
            blocks.append(current)
            continue
        m = AOR_HON.match(line)
        if m and "@" not in line:
            current = [clean_name(m.group(1)), []]
            blocks.append(current)
            continue
        if current is not None:
            current[1].append(line)
    for name, lines in blocks:
        body = " ".join(lines)
        if "Expired" in body or not name:
            continue
        addrs = emails_in(body)
        if addrs:
            yield addrs[0], name


# ─── Delhi High Court nominated counsel ───────────────────────────────
DHC_SERIAL = re.compile(r"^\s{0,3}(\d{1,3})\.(?:\s|$)")
DHC_LABEL = re.compile(r"^(M\.|MOB|PH|TEL|E\.|E-?MAIL|OFF|CH\.|CHAMBER|FLAT|HOUSE|ROOM|RES|OFFICE)\b", re.I)


def _name_col(line: str) -> str | None:
    """The name-column text of a line (starts at col 4-10), or None."""
    m = re.match(r"^(\s*(?:\d{1,3}\.\s+)?)([A-Za-z][A-Za-z .'\-()]{2,}?)(?=\s{2,}|$)", line)
    if not m or not 4 <= len(m.group(1)) <= 10:
        return None
    token = m.group(2).strip()
    if DHC_LABEL.match(token) or len(token) < 3 or token.isdigit():
        return None
    return token


def parse_dhc(text: str):
    entries = []           # [serial, name, lines]
    cur = None
    prev_was_name = False

    def start():
        nonlocal cur
        cur = [None, None, []]
        entries.append(cur)

    for line in text.splitlines():
        serial = DHC_SERIAL.match(line)
        name = _name_col(line)
        if serial and (cur is None or cur[0] is not None):
            start()
        if serial:
            cur[0] = serial.group(1)
        if name:
            if cur is None or (cur[1] is not None and not prev_was_name):
                start()
            cur[1] = name if cur[1] is None or not prev_was_name else f"{cur[1]} {name}"
        if cur is not None:
            cur[2].append(line)
        prev_was_name = bool(name)
    for _serial, name, lines in entries:
        addrs = emails_in(" ".join(lines))
        if addrs and name:
            yield addrs[0], clean_name(name)


# ─── SCBA life members (two columns) ──────────────────────────────────
def parse_scba(text: str):
    lines = text.splitlines()
    for col in (slice(0, 69), slice(69, None)):
        stream = [ln[col] for ln in lines]
        name = None
        for idx, ln in enumerate(stream):
            m = re.match(r"^\s*(\d{1,4})\s+([A-Za-z][^\d]*?)\s*$", ln)
            if m and idx + 1 < len(stream) and "Membership no" in stream[idx + 1]:
                raw = re.sub(r"\(.*?\)", "", m.group(2))
                if "," in raw:
                    last, _, first = raw.partition(",")
                    raw = f"{first.strip()} {last.strip()}"
                name = clean_name(raw)
                emitted = False
                continue
            if name and "@" in ln and not emitted:
                for addr in emails_in(ln):
                    yield addr, name
                    emitted = True
                    break


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    sources = [
        ("sc_aor_2026.txt", parse_aor, "New Delhi", "Supreme Court of India", SRC_AOR),
        ("dhc_nominated_counsel.txt", parse_dhc, "New Delhi", "Delhi High Court", SRC_DHC),
        ("scba_life.txt", parse_scba, "New Delhi", "Supreme Court of India", SRC_SCBA),
    ]
    rows, seen = [], set()
    for fname, parser, city, court, source in sources:
        text = (src / fname).read_text(encoding="utf-8", errors="replace")
        n_new = n_dup = 0
        for addr, name in parser(text):
            if addr in seen:
                n_dup += 1
                continue
            seen.add(addr)
            # A name the parser could not read cleanly is left blank: the email then says "Dear Colleague".
            if not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{3,44}", name or "") or re.search(r"\b(Mr|Ms|Mrs|Dr|Ch|Counsel)\b", name):
                name = ""
            rows.append({"email": addr, "name": f"Adv. {name}" if name else "", "city": city, "court": court, "source": source})
            n_new += 1
        print(f"{fname:28} {n_new:5} new, {n_dup:4} already listed")
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["email", "name", "city", "court", "source"])
        w.writeheader()
        w.writerows(rows)
    print(f"total {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
