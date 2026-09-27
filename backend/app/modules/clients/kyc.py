"""KYC validation — the checks a submission (or a staff edit) must pass.

Everything here is a pure function over plain dicts so the same rules run
on the public form's submission, on staff edits, and in tests. Findings are
returned, not raised: a submission with problems is still recorded so the
initiator can see exactly what the client typed and decide.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

# GST state codes (first two digits of a GSTIN; also the place of supply).
GST_STATE_CODES: dict[str, str] = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
    "97": "Other Territory", "99": "Centre Jurisdiction",
}
STATE_NAME_TO_CODE: dict[str, str] = {v.lower(): k for k, v in GST_STATE_CODES.items()}

# TDS sections a client is likely to deduct on a firm's fees, with the
# statutory default rate (%). The rate is editable — thresholds, PAN
# non-availability (206AA: 20%) and lower-deduction certificates change it.
TDS_SECTIONS: list[dict] = [
    {"section": "194J", "label": "194J — Fees for professional services", "rate": 10.0},
    {"section": "194J(b)", "label": "194J(b) — Fees for technical services", "rate": 2.0},
    {"section": "194C", "label": "194C — Contractors (individual/HUF 1%, others 2%)", "rate": 2.0},
    {"section": "194H", "label": "194H — Commission or brokerage", "rate": 2.0},
    {"section": "194I(a)", "label": "194I(a) — Rent of plant & machinery", "rate": 2.0},
    {"section": "194I(b)", "label": "194I(b) — Rent of land, building, furniture", "rate": 10.0},
    {"section": "194Q", "label": "194Q — Purchase of goods", "rate": 0.1},
    {"section": "194A", "label": "194A — Interest other than on securities", "rate": 10.0},
    {"section": "195", "label": "195 — Payments to non-residents", "rate": 20.0},
    {"section": "192", "label": "192 — Salary", "rate": 0.0},
    {"section": "other", "label": "Other section", "rate": 0.0},
]
TDS_SECTION_CODES = {s["section"] for s in TDS_SECTIONS}

BUSINESS_TYPES = [
    "proprietorship", "partnership", "llp", "private_limited", "public_limited", "opc",
    "trust", "society", "huf", "government", "psu", "cooperative", "foreign_entity", "other",
]

_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_TAN_RE = re.compile(r"^[A-Z]{4}[0-9]{5}[A-Z]$")
_CIN_RE = re.compile(r"^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$")
_PIN_RE = re.compile(r"^[1-9][0-9]{5}$")
_MOBILE_RE = re.compile(r"^(?:\+91[\s-]?)?[6-9][0-9]{9}$")
_PHONE_RE = re.compile(r"^[+0-9][0-9\s()-]{5,19}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$")

# PAN's 4th character encodes the holder type: P = person, C = company, F = firm,
# H = HUF, A = AOP, T = trust, B = BOI, L = local authority, J = artificial juridical, G = government.
_PAN_INDIVIDUAL_TYPES = {"P"}


@dataclass(slots=True)
class Issue:
    field: str
    message: str
    severity: str = "error"  # "error" blocks nothing but is shown prominently; "warning" is advisory

    def dict(self) -> dict:
        return asdict(self)


def normalise_pan(value: str | None) -> str | None:
    return value.strip().upper().replace(" ", "") if value else None


def normalise_gstin(value: str | None) -> str | None:
    return value.strip().upper().replace(" ", "") if value else None


def gstin_check_digit(gstin14: str) -> str:
    """The 15th character of a GSTIN (mod-36 weighted checksum)."""
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    total = 0
    for i, ch in enumerate(gstin14):
        factor = 2 if i % 2 else 1
        product = chars.index(ch) * factor
        total += product // 36 + product % 36
    return chars[(36 - total % 36) % 36]


def gstin_is_valid(gstin: str) -> bool:
    return bool(_GSTIN_RE.match(gstin)) and gstin_check_digit(gstin[:14]) == gstin[14]


def validate_client(kind: str, data: dict) -> list[Issue]:
    """Validate a client's identity, contact and tax fields.

    ``data`` is a plain dict of client fields (any subset). Returns findings;
    an empty list means everything present is consistent.
    """
    issues: list[Issue] = []
    get = lambda k: (data.get(k) or "").strip() if isinstance(data.get(k), str) else data.get(k)  # noqa: E731

    pan = normalise_pan(get("pan"))
    if pan and not _PAN_RE.match(pan):
        issues.append(Issue("pan", "PAN must be 10 characters like ABCDE1234F."))
    elif pan:
        holder = pan[3]
        if kind == "individual" and holder not in _PAN_INDIVIDUAL_TYPES:
            issues.append(Issue("pan", f"This PAN is not an individual's (4th character '{holder}').", "warning"))
        if kind == "business" and holder in _PAN_INDIVIDUAL_TYPES:
            issues.append(Issue("pan", "This is an individual's PAN; a business usually has its own (4th character C/F/T/A…). Fine for a proprietorship.", "warning"))

    gstin = normalise_gstin(get("gstin"))
    if data.get("gst_applicable") and not gstin and get("gst_treatment") not in (None, "", "unregistered", "overseas"):
        issues.append(Issue("gstin", "GST is marked applicable but no GSTIN was given."))
    if gstin:
        if not gstin_is_valid(gstin):
            issues.append(Issue("gstin", "GSTIN is not valid (format or check digit)."))
        else:
            if pan and gstin[2:12] != pan:
                issues.append(Issue("gstin", "GSTIN does not contain this PAN (characters 3–12 must match)."))
            code = gstin[:2]
            if code not in GST_STATE_CODES:
                issues.append(Issue("gstin", f"Unknown GST state code {code}."))
            state = (get("state") or "").lower()
            if state and code in GST_STATE_CODES and STATE_NAME_TO_CODE.get(state) not in (None, code):
                issues.append(Issue("state", f"GSTIN is registered in {GST_STATE_CODES[code]}, but the address state is {get('state')}.", "warning"))

    if data.get("tds_applicable"):
        section = get("tds_section")
        if not section:
            issues.append(Issue("tds_section", "TDS is marked as deducted but no section was chosen."))
        elif section not in TDS_SECTION_CODES:
            issues.append(Issue("tds_section", f"Unknown TDS section '{section}'."))
        rate = data.get("tds_rate")
        if rate is None:
            issues.append(Issue("tds_rate", "TDS rate is required when TDS is deducted."))
        elif not (0 <= float(rate) <= 30):
            issues.append(Issue("tds_rate", "TDS rate must be between 0 and 30 percent."))
        tan = get("tan")
        if tan and not _TAN_RE.match(tan.upper()):
            issues.append(Issue("tan", "TAN must look like ABCD12345E."))

    if kind == "business":
        if not (get("legal_name") or get("display_name")):
            issues.append(Issue("legal_name", "Business name is required."))
        cin = get("cin")
        if cin and not _CIN_RE.match(cin.upper()):
            issues.append(Issue("cin", "CIN must be 21 characters like U12345DL2015PTC123456."))
        udyam = get("msme_udyam")
        if udyam and not _UDYAM_RE.match(udyam.upper()):
            issues.append(Issue("msme_udyam", "Udyam number must look like UDYAM-DL-01-0012345."))
    else:
        if not (get("first_name") or get("display_name")):
            issues.append(Issue("first_name", "Name is required."))

    for field in ("email", "contact_person_email"):
        v = get(field)
        if v and not _EMAIL_RE.match(v):
            issues.append(Issue(field, "Email address does not look valid."))
    for field in ("mobile", "contact_person_mobile"):
        v = get(field)
        if v and not _MOBILE_RE.match(v.replace(" ", "")):
            issues.append(Issue(field, "Mobile must be a 10-digit Indian number (optionally +91)."))
    phone = get("phone")
    if phone and not _PHONE_RE.match(phone):
        issues.append(Issue("phone", "Phone number does not look valid."))
    pin = get("pincode")
    if pin and (get("country") or "India").lower() == "india" and not _PIN_RE.match(pin):
        issues.append(Issue("pincode", "PIN code must be 6 digits."))
    if data.get("consent_email") and not get("email"):
        issues.append(Issue("consent_email", "Email consent given but no email address.", "warning"))
    if (data.get("consent_mobile") or data.get("consent_whatsapp")) and not get("mobile"):
        issues.append(Issue("consent_mobile", "Mobile consent given but no mobile number.", "warning"))
    return issues


def tds_default_rate(section: str | None) -> float | None:
    for s in TDS_SECTIONS:
        if s["section"] == section:
            return s["rate"]
    return None
