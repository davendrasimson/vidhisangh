"""Outreach CSV from district court / legal-services advocate lists (CIS exports), 1–2 Nov 2026.

    python3 -I scripts/outreach_build_contacts_district.py <src_dir> <out.csv> [--meta meta.csv]

<src_dir> holds `<state>_<district>_<publisher>_<topic>.pdf.txt` files (pdftotext -layout) downloaded from
`<district>.dcourts.gov.in/document-category/pleaders-and-bar-association/` and similar official pages.
Most are the eCourts CIS "Advocate details" export: one row per advocate with code, name, mobile, email, bar
registration (columns vary; some put the address or the registration before the email). The parser splits each
line that carries an email into fields (2+ spaces), takes the first name-like field as the name, any 10-digit
number as the mobile, and drops a mailbox that recurs 3+ times in one file (an association's shared address).
`--meta` is an optional CSV `file,city,court,source` overriding what is derived from the file name.
"""
import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from outreach_build_contacts import clean_name, emails_in  # noqa: E402
from outreach_build_contacts_states import mobile_in  # noqa: E402

NAME_FIELD = re.compile(r"^[A-Za-z][A-Za-z .'\-()]{3,60}$")
NOT_NAMES = re.compile(r"^(male|female|other|advocate|advocates|yes|no|null|none|n/?a|sri|smt|shri|mr|ms|mrs|llb|ll\.b|b\.a|ba|bcom|m\.a|ma|senior|junior|active|inactive|"
                       r"jharkhand|haryana|bihar|punjab|assam|maharashtra|gujarat|rajasthan|karnataka|kerala|odisha|delhi|chhattisgarh|"
                       r"west bengal|himachal pradesh|madhya pradesh|uttar pradesh|tamil nadu|andhra pradesh|telangana|manipur|tripura|"
                       r"bokaro|ranchi|dhanbad|hazaribag|giridih|deoghar|dumka|chatra|jamtara|koderma|ramgarh|gumla|latehar|sahibganj|simdega|"
                       r"district court|high court|bar association)\b", re.I)
STATE_NAMES = {"hp": "Himachal Pradesh", "wb": "West Bengal", "up": "Uttar Pradesh", "mp": "Madhya Pradesh", "jk": "Jammu & Kashmir"}
CITY_FIX = {"paschimmedinipur": "Paschim Medinipur", "gautambuddhnagar": "Gautam Buddh Nagar", "hazaribag": "Hazaribagh", "all": ""}


def title(s: str) -> str:
    return " ".join(w.capitalize() for w in s.replace("_", " ").split())


def meta_from_name(path: Path) -> tuple[str, str, str]:
    """(city, court, source) from `<state>_<district>_<publisher>_<topic>.pdf.txt`."""
    if "__" in path.name:  # the nationwide sweep names files <subdomain>__<original>.pdf.txt
        sub = path.name.split("__")[0]
        city = CITY_FIX.get(sub, title(sub))
        return city, f"District Court, {city}", f"the District Court {city}'s list of advocates ({sub}.dcourts.gov.in)"
    parts = path.name.split(".")[0].split("_")
    state, district = parts[0], parts[1] if len(parts) > 1 else ""
    publisher = parts[2] if len(parts) > 2 else ""
    state_name = STATE_NAMES.get(state, title(state))
    city = CITY_FIX.get(district, title(district))
    if publisher == "dcourts" and city:
        return city, f"District Court, {city}", f"the District Court {city}'s list of advocates ({district}.dcourts.gov.in)"
    if "slsa" in publisher or "dslsa" in publisher or "nalsa" in publisher:
        who = f"{state_name} State Legal Services Authority" if district == "all" else f"District Legal Services Authority, {city}"
        return city, f"{who} panel", f"the {who}'s list of panel lawyers ({state_name.lower().replace(' ', '')}.nalsa.gov.in)"
    return city, (f"District Court, {city}" if city else ""), f"the {city or state_name} advocates' list published by {publisher} ({state})"


def parse_rows(text: str, *, name_from_gender_line: bool = False):
    """Yield (email, name, mobile) from a CIS-style export."""
    lines = text.splitlines()
    pending_name = None
    for i, ln in enumerate(lines):
        gm = re.match(r"^\s*(?:\d+\s+)?([A-Z][A-Za-z .'\-]{3,60}?)\s{2,}(?:MALE|FEMALE|OTHER)\b", ln)
        if gm:
            pending_name = clean_name(gm.group(1))
        if "@" not in ln:
            continue
        addrs = emails_in(ln)
        if not addrs:
            continue
        fields = [f.strip() for f in re.split(r"\s{2,}", ln.strip()) if f.strip()]
        name = None
        if name_from_gender_line:
            name, pending_name = pending_name, None
        else:
            for f in fields:
                if "@" in f or re.search(r"\d", f):
                    continue
                f_clean = re.sub(r"^(Adv\.?|Advocate|Sh\.?|Shri|Smt\.?|Mr\.?|Ms\.?|Mrs\.?|Miss|Dr\.?)\s+", "", f).strip()
                if NAME_FIELD.match(f_clean) and not NOT_NAMES.match(f_clean) and len(f_clean.split()) <= 6:
                    name = clean_name(f_clean)
                    break
        mob = mobile_in(ln)
        yield addrs[0], name, mob


def main() -> None:
    args = sys.argv[1:]
    src, out = Path(args[0]), Path(args[1])
    meta: dict[str, tuple[str, str, str]] = {}
    if "--meta" in args:
        for row in csv.DictReader(open(args[args.index("--meta") + 1], encoding="utf-8")):
            meta[row["file"]] = (row["city"], row["court"], row["source"])
    rows, seen = [], set()
    for path in sorted(src.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="replace")
        city, court, source = meta.get(path.name) or meta_from_name(path)
        gender_mode = bool(re.search(r"\s(MALE|FEMALE)\s", text)) and not re.search(r"Mobile No\.\s+Email|Email\s+Bar Regn", text)
        found = list(parse_rows(text, name_from_gender_line=gender_mode))
        shared = {a for a, n in Counter(a for a, _, _ in found).items() if n >= 3}
        n_new = 0
        for addr, name, mob in found:
            if addr in shared or addr in seen:
                continue
            if not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{3,44}", name or ""):
                name = ""
            seen.add(addr)
            rows.append({"email": addr, "name": f"Adv. {name}" if name else "", "mobile": mob or "", "city": city,
                         "court": court, "source": source[:300]})
            n_new += 1
        print(f"{path.name[:60]:60} {n_new:6}  (shared mailboxes dropped: {len(shared)})")
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["email", "name", "mobile", "city", "court", "source"])
        w.writeheader()
        w.writerows(rows)
    print(f"total {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
