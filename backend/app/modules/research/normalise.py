"""Derive the structured research fields from raw registry strings.

The same rules as ``app.scripts.backfill_case_fields`` (which does this in SQL
for millions of existing rows), applied in Python so a judgment written through
the API gets the same ``judge_text`` / ``case_type`` / ``cause_title`` as the
bulk-loaded ones. Keep the two in step: a judge that normalises differently in
the two paths becomes two facet values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# "CRM-M/33310/2019 of RUSTAM Vs STATE" -> type, number, year, cause title
_TITLE_RE = re.compile(r"^([^/]+)/(\d+)/(\d{4})\s+of\s+")

# Honorifics as the registries print them; what remains is the bare name.
# The trailing whitespace is optional so a bare title with no name after it
# ("HON'BLE THE ACTING CHIEF JUSTICE") strips to nothing and is dropped,
# rather than surviving as a judge called "Acting Chief Justice".
_JUDGE_STRIP_RE = re.compile(
    r"^(HON'?BLE\s+)?(THE\s+)?((MR|MRS|MS|DR|SHRI|SMT)\.?\s+)?"
    r"((ACTING\s+)?(CHIEF\s+)?JUSTICE\b\s*)?",
    re.I,
)
# One registry element may name several judges.
_JUDGE_SPLIT_RE = re.compile(r"\s*,\s*|\s+and\s+|\s*&\s*", re.I)


@dataclass(slots=True)
class RegistryTitle:
    case_type: str | None
    case_number: str | None
    case_year: int | None
    cause_title: str


def parse_registry_title(case_name: str, fallback_date: date | None = None) -> RegistryTitle:
    """Split a registry title into its number prefix and the cause title.

    Supreme Court titles have no prefix; they come back whole, with the year
    taken from the decision date so year facets still work.
    """
    match = _TITLE_RE.match(case_name or "")
    if not match:
        return RegistryTitle(
            case_type=None,
            case_number=None,
            case_year=fallback_date.year if fallback_date else None,
            cause_title=(case_name or "")[:500],
        )
    case_type, number, year = match.groups()
    return RegistryTitle(
        case_type=case_type.strip()[:40] or None,
        case_number=number[:40],
        case_year=int(year),
        cause_title=case_name[match.end():][:500],
    )


# Registries put status text in the judge field. Left unfiltered these become
# top facet values — "Justice Case Is Not Allocated To Court." outranked every
# real judge with 74,632 rows.
_JUDGE_PLACEHOLDER_RE = re.compile(
    r"not\s+allocated|no[t]?\s+assigned|vacant|registrar|^court$|^n\.?a\.?$", re.I
)


def is_placeholder_judge(name: str) -> bool:
    """True for registry status text masquerading as a judge's name."""
    return bool(_JUDGE_PLACEHOLDER_RE.search(name or ""))


# "A Vs B", "A v. B", "A Versus B" — the cause title's two sides.
_VERSUS_RE = re.compile(r"\s+(?:vs\.?|v\.|versus)\s+", re.I)


def split_parties(cause_title: str | None) -> tuple[str | None, str | None]:
    """(petitioner, respondent) from a cause title, or (None, None).

    Only the first "Vs" splits: "A Vs B Vs C" does not occur in registry
    titles, but party names containing "v." ("XYZ Pvt. Ltd.") must survive.
    """
    if not cause_title:
        return None, None
    parts = _VERSUS_RE.split(cause_title.strip(), maxsplit=1)
    if len(parts) != 2:
        return None, None
    left, right = (p.strip(" .,") for p in parts)
    return (left[:300] or None), (right[:300] or None)


# Three registries, three ways of printing counsel in an order's opening:
#
#  Delhi      "<A> .....Appellant Through: Mr. X, Advocate versus <B>
#              .....Respondents Through: Ms. Y, Adv. for R-3 CORAM: ..."
#  Allahabad  "Petitioner :- <A> Respondent :- <B> Counsel for Petitioner :-
#              X,Y Counsel for Respondent :- A.S.G.I.,Z Hon'ble ...,J."
#             (also Applicant / Opposite Party, Appellant, Revisionist)
#  P&H        "<A> ....Petitioners Versus <B> ....Respondents CORAM: ...
#              Present: Mr. X, Advocate for the petitioners. Mr. Y, Advocate
#              for the respondents. ***** NAME, J."
_PET_WORDS = r"petitioners?|applicants?|appellants?|revisionists?|complainants?|plaintiffs?|claimants?|decree[- ]holders?"
_RESP_WORDS = r"respondents?|opposite\s+part(?:y|ies)|state|u\.?o\.?i\.?|union\s+of\s+india|defendants?|caveators?|non[- ]applicants?|judgment[- ]debtors?"

# Anchored on the party role the Delhi registry prints right before "Through:"
# ("…Appellant Through: Mr. X"). Without that anchor, ordinary prose in a
# judgment ("…through his son Gaurav Singh") would be read as counsel.
_THROUGH_RE = re.compile(
    rf"\b(?:{_PET_WORDS}|{_RESP_WORDS})\s*Through\s*:?\s*(?P<counsel>.*?)"
    # `\s*` not `\s+` before the boundary words: an empty block ("Through:
    # versus MANMOHAN") has its whitespace consumed already, and the opposite
    # party must not be read as counsel.
    r"(?=\s*\b(?:versus|vs\.?|v\.)\s+|\s*\bCORAM\b|\s+\S+\s+Through\b|$)",
    re.I | re.S,
)
_ALD_COUNSEL_RE = re.compile(
    rf"Counsel\s+for\s+(?P<side>{_PET_WORDS}|{_RESP_WORDS})\s*:-\s*(?P<counsel>.*?)"
    r"(?=\s+Counsel\s+for\b|\s+Hon'?ble\b|\s+CORAM\b|$)",
    re.I | re.S,
)
# The block ends at the "*****" rule or the author line "NAMIT KUMAR, J." —
# that terminator must stay case-sensitive under re.I, or "Punjab for the
# respondents. NAMIT KUMAR, J." matches it and the respondents are cut off.
_PH_PRESENT_RE = re.compile(
    r"Present\s*:\s*(?P<block>.*?)(?=\s*\*{3,}|(?-i:\s+[A-Z][A-Z .]+,\s*J\.)|$)", re.I | re.S
)
# One "Mr. X, Advocate for the petitioners." segment of a P&H "Present:" block
# (Uttarakhand writes "learned counsel for petitioner(s)", without "the").
_PH_SEGMENT_RE = re.compile(
    rf"(?P<names>.+?)\s+for\s+(?:the\s+)?(?P<side>{_PET_WORDS}|{_RESP_WORDS})\b[^.]*\.?",
    re.I | re.S,
)
# Uttarakhand judgments: "Presence:- Mr. A, Mr. B and Mr. C, learned counsel for
# petitioner(s). Mr. D, learned counsel for respondents-University." up to the judge.
_UK_PRESENCE_RE = re.compile(r"Presence\s*:-?\s*(?P<block>.*?)(?=\s*Hon[’']?ble\b|$)", re.I | re.S)
# Uttarakhand order sheets print the appearances right after the judge's name:
# "Hon'ble X, J. Mr. A, Advocate for the petitioners. Mr. B, Brief Holder for the
# State." and then the first numbered paragraph or "Learned counsel …".
_UK_SHEET_RE = re.compile(
    r"Hon[’']?ble\s+[^\n]{3,80}?,\s*J\.\s*(?:\(Oral\))?\s*(?P<block>(?:Mr|Ms|Mrs|Dr|Shri|Smt|Sh)\b.*?)"
    r"(?=\s+\d{1,2}\.\s+(?!(?:Mr|Ms|Mrs|Dr|Shri|Smt|Sh)\b)[A-Z]|\s+Learned\s+counsel\b|\s+Heard\b|\s+This\b|$)",
    re.I | re.S,
)
# Delhi judgments: "Advocates who appeared in this case  For the Petitioner : Mr. X …
# Advocates.  For the Respondents : Mr. Y … CORAM:".
_DEL_FOR_RE = re.compile(
    rf"\bFor\s+the\s+(?P<side>{_PET_WORDS}|{_RESP_WORDS})\s*:\s*(?P<counsel>.*?)"
    rf"(?=\s+For\s+the\s+(?:{_PET_WORDS}|{_RESP_WORDS})\s*:|\s+CORAM\b|$)",
    re.I | re.S,
)

_COUNSEL_SPLIT_RE = re.compile(
    r"\s*,\s*|\s+and\s+|\s*&\s*|\s+with\s+|\s+alongwith\s+|\s+along with\s+|\s+assisted\s+by\s+"
    # A full stop after a lowercase word ends a name ("Nitya Ramakrishnan. Sarim
    # Naved", "Adv. Mr. X") — unlike the dot of an initial ("K. Radhakrishnan").
    # Case-sensitive on purpose: under re.I the lookbehind would match the "K"
    # of "S.K." and split the initials off the surname.
    r"|(?-i:(?<=[a-z])\.\s+(?=(?:Mr|Ms|Mrs|Dr|Shri|Smt)\b|[A-Z][a-z]+\s+[A-Z]))",
    re.I,
)
# Honorifics (also unspaced, "Mr.A.K. Soni") and role words that are not a name.
# Leading honorifics: each must end at a dot or a word boundary, so "Adv." and
# "Mr.A.K." strip but the "Adv" inside "Advocate" does not (that gave "Ocate").
# Repeated prefixes may be separated by dots/spaces ("Adv.. Mr. Rahul Sharma").
_COUNSEL_STRIP_RE = re.compile(
    r"^(?:(?:learned|advocate|shri|smt|mrs|adv|mr|mt|ms|dr|sh|ld)(?:\.|\b)[\s.]*)+|"
    r"\s*\b(?:sr\.?\s+advocates?|senior\s+advocates?|advocates?|advs?\.?|counsel|ld\.?|learned|"
    r"standing\s+counsel|brief\s+holder|ASC|APP|SPP|CGSC|SSC|JSCs?|SPC|DAG|AAG|A\.?G\.?|Addl\.?\s+A\.?G\.?|proxy\s+counsel|"
    r"amicus\s+curiae|\(.*\))\b.*$",
    re.I,
)
# Not a person: absent counsel, party words, government law offices and their
# abbreviations (A.S.G.I., G.A., C.S.C., D.A.G.), and the state a DAG is "for".
_COUNSEL_NOISE_RE = re.compile(
    r"^(?:none|nemo|no\s+one|nil|in\s+person|(?:party|petitioners?|appellants?|respondents?|applicants?)"
    r"[\s-]*in[\s-]*person|petitioners?|respondents?|appellants?|applicants?|anr|ors|"
    r"a\.?s\.?g\.?i?\.?|g\.?a\.?|c\.?s\.?c\.?|a\.?g\.?a\.?|d\.?g\.?c\.?|s\.?c\.?|"
    r"d\.?a\.?g\.?|a\.?a\.?g\.?|punjab|haryana|u\.?t\.?\s*chandigarh|chandigarh|state|-+)$",
    re.I,
)
# Allahabad's abbreviations for government counsel (not a person's name).
_ALD_OFFICE_RE = re.compile(r"^(?:[A-Z]\.){2,5}$")
# Police ranks and stations: SI/ASI/HC/Ct./Insp./ACP/DCP <name>, PS <station>.
_POLICE_RE = re.compile(
    r"^(?:s\.?i|a\.?s\.?i|h\.?c|ct|const|insp|inspector|a\.?c\.?p|d\.?c\.?p|s\.?h\.?o|i\.?o|p\.?s)\b\.?\s",
    re.I,
)


def _counsel_names(block: str) -> list[str]:
    names: list[str] = []
    # Drop "for R-3" / "for UOI." / "for Mr. Shiv Dutt Kaushik" (a proxy) role
    # clauses first: everything up to the next comma, except that a period
    # followed by an honorific starts a new name ("…Adv. for UOI. Mr. Rahul
    # Sharma, …") and must survive.
    block = re.sub(
        r"\s+for\s+(?!the\s+(?:" + _PET_WORDS + "|" + _RESP_WORDS + r"))"
        r"(?:(?!\.\s*(?:mr|ms|mrs|dr|shri|smt)\b)[^,])*",
        "", block, flags=re.I,
    )
    # Parentheticals are never part of a name: "(thru VC)", "(Sr. Adv.)", "(DHCLSC)".
    block = re.sub(r"\([^)]*\)", " ", block)
    # ", assisted by Mr. X" / ", with Mr. X": the comma would win the split and leave
    # the joining words on the next name; numbered appearances ("2. Mr. X") lose the number.
    block = re.sub(r",\s*(?:assisted\s+by|along\s*with|with|and)\s+", ", ", block, flags=re.I)
    block = re.sub(r"(^|\s)\d{1,2}\.\s+(?=(?:Mr|Ms|Mrs|Dr|Shri|Smt|Sh)\b)", r"\1", block)
    for piece in _COUNSEL_SPLIT_RE.split(block):
        piece = " ".join(piece.split())  # pypdf breaks names across lines
        bare = _COUNSEL_STRIP_RE.sub("", piece.strip()).strip(" .,;:-")
        if not bare or _COUNSEL_NOISE_RE.match(bare) or _ALD_OFFICE_RE.match(bare):
            continue
        if len(bare) < 3 or len(bare) > 60 or not re.search(r"[A-Za-z]{2,}", bare):
            continue
        # A short all-caps token is an office or a party abbreviation (DJB,
        # DDA, UOI, NCT, SP), not a person.
        if bare.isupper() and len(bare.replace(".", "")) <= 4:
            continue
        # Delhi criminal orders name the investigating officer beside the
        # State's counsel ("with SI Sandeep Kumar, PS Seema Puri"): a police
        # rank or station prefix marks a police officer, not an advocate.
        if _POLICE_RE.match(bare):
            continue
        name = bare.title()
        if name not in names:
            names.append(name)
    return names


def _is_petitioner_side(side: str) -> bool:
    return bool(re.fullmatch(_PET_WORDS, side.strip(), re.I))


def parse_counsel(description: str | None) -> tuple[list[str], list[str]]:
    """(petitioner's advocates, respondent's advocates) from an order's opening.

    Tries each registry's format and returns empty lists when none applies.
    Never guesses a side: Delhi's first "Through:" block is the petitioner's,
    later ones the respondents'; Allahabad and P&H name the side explicitly.
    """
    if not description:
        return [], []
    head = description[:1500]
    pet: list[str] = []
    resp: list[str] = []

    # Allahabad: explicit "Counsel for <side> :- names".
    for m in _ALD_COUNSEL_RE.finditer(head):
        target = pet if _is_petitioner_side(m.group("side")) else resp
        target.extend(n for n in _counsel_names(m.group("counsel")) if n not in target)
    if pet or resp:
        return pet, resp

    # P&H: "Present: Mr. X, Advocate for the petitioners. Mr. Y ... for the respondents."
    pm = _PH_PRESENT_RE.search(head)
    if pm:
        for seg in _PH_SEGMENT_RE.finditer(pm.group("block")):
            target = pet if _is_petitioner_side(seg.group("side")) else resp
            target.extend(n for n in _counsel_names(seg.group("names")) if n not in target)
        if pet or resp:
            return pet, resp

    # Uttarakhand judgments: "Presence:-" block with "learned counsel for <side>" segments.
    um = _UK_PRESENCE_RE.search(head)
    if um:
        for seg in _PH_SEGMENT_RE.finditer(um.group("block")):
            target = pet if _is_petitioner_side(seg.group("side")) else resp
            target.extend(n for n in _counsel_names(seg.group("names")) if n not in target)
        if pet or resp:
            return pet, resp

    # Delhi judgments: "For the Petitioner : names  For the Respondents : names".
    for m in _DEL_FOR_RE.finditer(head[: (re.search(r"\bCORAM\b", head, re.I) or re.search(r"$", head)).start()]):
        target = pet if _is_petitioner_side(m.group("side")) else resp
        target.extend(n for n in _counsel_names(m.group("counsel")) if n not in target)
    if pet or resp:
        return pet, resp

    # Uttarakhand order sheets: appearances straight after "Hon'ble X, J.".
    sm = _UK_SHEET_RE.search(head)
    if sm:
        for seg in _PH_SEGMENT_RE.finditer(sm.group("block")):
            target = pet if _is_petitioner_side(seg.group("side")) else resp
            target.extend(n for n in _counsel_names(seg.group("names")) if n not in target)
        if pet or resp:
            return pet, resp

    # Delhi: positional "Through:" blocks, only in the opening (before CORAM/ORDER).
    if "through" in head.lower():
        cut = re.search(r"\bCORAM\b|\bO\s*R\s*D\s*E\s*R\b|\bJUDGMENT\b", head, re.I)
        opening = head[: cut.start()] if cut else head
        blocks = [m.group("counsel") for m in _THROUGH_RE.finditer(opening)]
        if blocks:
            pet = _counsel_names(blocks[0])
            resp = _counsel_names(" , ".join(blocks[1:])) if len(blocks) > 1 else []
    return pet, resp


# Allahabad prints its neutral citation first: "No. - 2023:AHC:174410 Court No. - 77 …"
_NEUTRAL_CITATION_RE = re.compile(r"\b(\d{4}:[A-Z]{3,6}(?:-[A-Z]{2,4})?:\d{3,8}(?:-[A-Z]{2})?)\b")


def parse_neutral_citation(description: str | None) -> str | None:
    """The court's neutral citation (e.g. 2023:AHC:174410) if the opening has one."""
    m = _NEUTRAL_CITATION_RE.search((description or "")[:200])
    return m.group(1) if m else None


def advocate_text(petitioner: list[str], respondent: list[str]) -> str | None:
    """All advocates on the record, " | "-joined and de-duplicated, for filtering."""
    seen: list[str] = []
    for name in [*petitioner, *respondent]:
        if name not in seen:
            seen.append(name)
    return " | ".join(seen) or None


# ── Acts and sections from an order's text ───────────────────────────
# Courts cite statutes in many spellings; map the common abbreviations to
# the statute's name so "IPC", "I.P.C." and "Indian Penal Code" facet as one.
_ACT_ALIASES: dict[str, str] = {
    "ipc": "Indian Penal Code, 1860",
    "indian penal code": "Indian Penal Code, 1860",
    "crpc": "Code of Criminal Procedure, 1973",
    "code of criminal procedure": "Code of Criminal Procedure, 1973",
    "cpc": "Code of Civil Procedure, 1908",
    "code of civil procedure": "Code of Civil Procedure, 1908",
    "constitution": "Constitution of India",
    "constitution of india": "Constitution of India",
    "bns": "Bharatiya Nyaya Sanhita, 2023",
    "bharatiya nyaya sanhita": "Bharatiya Nyaya Sanhita, 2023",
    "bnss": "Bharatiya Nagarik Suraksha Sanhita, 2023",
    "bharatiya nagarik suraksha sanhita": "Bharatiya Nagarik Suraksha Sanhita, 2023",
    "bsa": "Bharatiya Sakshya Adhiniyam, 2023",
    "evidence act": "Indian Evidence Act, 1872",
    "indian evidence act": "Indian Evidence Act, 1872",
    "ndps act": "Narcotic Drugs and Psychotropic Substances Act, 1985",
    "ni act": "Negotiable Instruments Act, 1881",
    "negotiable instruments act": "Negotiable Instruments Act, 1881",
    "pocso act": "Protection of Children from Sexual Offences Act, 2012",
    "pc act": "Prevention of Corruption Act, 1988",
    "prevention of corruption act": "Prevention of Corruption Act, 1988",
    "pmla": "Prevention of Money Laundering Act, 2002",
    "uapa": "Unlawful Activities (Prevention) Act, 1967",
    "ibc": "Insolvency and Bankruptcy Code, 2016",
    "insolvency and bankruptcy code": "Insolvency and Bankruptcy Code, 2016",
    "sarfaesi act": "Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act, 2002",
    "arbitration act": "Arbitration and Conciliation Act, 1996",
    "arbitration and conciliation act": "Arbitration and Conciliation Act, 1996",
    # pypdf splits words on kerning ("Arbitrati on and Conciliation Act");
    # the second half alone is still unambiguous.
    "conciliation act": "Arbitration and Conciliation Act, 1996",
    "motor vehicles act": "Motor Vehicles Act, 1988",
    "mv act": "Motor Vehicles Act, 1988",
    "hindu marriage act": "Hindu Marriage Act, 1955",
    "transfer of property act": "Transfer of Property Act, 1882",
    "specific relief act": "Specific Relief Act, 1963",
    "limitation act": "Limitation Act, 1963",
    "companies act": "Companies Act, 2013",
    "income tax act": "Income Tax Act, 1961",
    "domestic violence act": "Protection of Women from Domestic Violence Act, 2005",
    "industrial disputes act": "Industrial Disputes Act, 1947",
    "consumer protection act": "Consumer Protection Act, 2019",
    "land acquisition act": "Land Acquisition Act, 1894",
    "electricity act": "Electricity Act, 2003",
    "gst act": "Goods and Services Tax Act, 2017",
    "cgst act": "Central Goods and Services Tax Act, 2017",
    "excise act": "Central Excise Act, 1944",
    "customs act": "Customs Act, 1962",
    "essential commodities act": "Essential Commodities Act, 1955",
    "wildlife protection act": "Wild Life (Protection) Act, 1972",
    "arms act": "Arms Act, 1959",
    "senior citizens act": "Maintenance and Welfare of Parents and Senior Citizens Act, 2007",
    "juvenile justice act": "Juvenile Justice (Care and Protection of Children) Act, 2015",
    "rti act": "Right to Information Act, 2005",
    "sc/st act": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act, 1989",
    "sc and st act": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act, 1989",
}
# A statute's name. Most end in Act/Code/Sanhita ("Arbitration and
# Conciliation Act, 1996" — connectors allowed, no periods inside words so
# "Act. The Kerala…" cannot glue two sentences together), but the two
# procedure codes and the Constitution are named the other way round.
_ACT_NAME = (
    r"(?:Code\s+of\s+(?:Criminal|Civil)\s+Procedure(?:,?\s*\d{4})?"
    r"|Constitution\s+of\s+India"
    # Words may open with "(" — "Terrorist and Disruptive Activities (Prevention) Act".
    r"|(?:(?!(?:Act|Code|Rules)\b)(?:\(?[A-Z][A-Za-z()&'’-]*|and|of|for|the|&)\s+){0,9}"
    r"(?:Act|Code|Constitution|Sanhita|Adhiniyam|Rules)(?:,?\s*\d{4})?)"
)
# "Section 438 of the Code of Criminal Procedure, 1973" / "u/s 482 Cr.P.C." /
# "Sections 302, 34 IPC" / "Article 226 of the Constitution of India".
_SECTION_RE = re.compile(
    r"\b(?P<kind>Sections?|Sec\.?|Ss?\.|u/s\.?|under\s+s(?:ection)?\.?|Articles?|Arts?\.|Rules?|Orders?)\s*"
    r"(?P<nums>\d{1,4}[A-Z]{0,2}(?:\s*\(\s*\d{1,3}[a-z]?\s*\))*"
    r"(?:\s*(?:,|and|&|/|to|read\s+with|r/w)\s*\d{1,4}[A-Z]{0,2}(?:\s*\(\s*\d{1,3}[a-z]?\s*\))*)*)"
    r"\s*(?:of\s+(?:the\s+)?)?"
    r"(?P<act>" + _ACT_NAME + r"|[A-Z][A-Za-z.]{1,10}\.?(?:\s?Act)?)?",
    re.M,
)
_ACT_ONLY_RE = re.compile(r"\b(?P<act>" + _ACT_NAME + r")")
_ACT_ABBR_RE = re.compile(r"^(?:[A-Z]\.){2,5}$|^[A-Z]{2,6}(?:\s?Act)?$")
# Words that do not name a statute: "the Act", "said Act", "Central Act",
# "Amendment Act" on its own, "U.P. Act" (a state prefix without the name).
_ACT_STOPWORDS = {
    "act", "code", "rules", "the", "said", "same", "this", "that", "such", "central", "state",
    "amendment", "principal", "parent", "present", "impugned", "relevant", "new", "old",
    "and", "of", "for", "&", "u.p.", "m.p.", "h.p.", "a.p.", "j&k",
}


def _substantive(act: str) -> bool:
    """A statute name needs at least one real word besides Act/Code/the year."""
    words = [w.strip(",.()") for w in act.split()]
    return any(len(w) >= 3 and w.lower() not in _ACT_STOPWORDS and not w.isdigit() for w in words)


def _merge_year_variants(counts: dict[str, int]) -> dict[str, int]:
    """'Kerala Forest Act' + 'Kerala Forest Act, 1961' -> the dated one."""
    dated = {re.sub(r",?\s*\d{4}$", "", k): k for k in counts if re.search(r"\d{4}$", k)}
    merged: dict[str, int] = {}
    for k, n in counts.items():
        target = dated.get(k, k) if not re.search(r"\d{4}$", k) else k
        merged[target] = merged.get(target, 0) + n
    return merged


def _canonical_act(raw: str | None) -> str | None:
    if not raw:
        return None
    s = " ".join(raw.replace("’", "'").split()).strip(" ,.")
    # Leading words that are not part of the name, before the alias lookup so
    # "the Constitution" resolves like "Constitution".
    s = re.sub(r"^(?:(?:[Tt]he|said|same|provisions\s+of|under|of|and|for)\s+)+", "", s)
    key = re.sub(r"[.\s]+", "", s.lower())              # "Cr.P.C." -> "crpc"
    key2 = re.sub(r"\s*,?\s*\d{4}$", "", s.lower()).replace(".", "").strip()  # drop year
    for k in (key, key2, s.lower()):
        if k in _ACT_ALIASES:
            return _ACT_ALIASES[k]
    if re.fullmatch(r"(?:i\.?p\.?c\.?)", s, re.I):
        return _ACT_ALIASES["ipc"]
    if re.fullmatch(r"(?:cr\.?\s?p\.?c\.?)", s, re.I):
        return _ACT_ALIASES["crpc"]
    if re.fullmatch(r"(?:c\.?p\.?c\.?)", s, re.I):
        return _ACT_ALIASES["cpc"]
    if len(s) < 6 or not re.search(r"\b(?:Act|Code|Constitution|Sanhita|Adhiniyam|Rules)\b", s):
        return None  # an unknown abbreviation: not worth a facet value
    # Trim leading words that are not part of the name ("the", "said", "provisions of").
    s = re.sub(r"^(?:(?:[Tt]he|said|same|provisions\s+of|under|of|and|for)\s+)+", "", s)
    # "Chapter III of the Act", "Schedule-IV of the Act, 1996": a part of an
    # unnamed statute, not a statute.
    if re.match(r"^(?:Chapter|Schedule|Part|Order|Rule|Section|Clause|Article)\b", s, re.I):
        return None
    if not _substantive(s):
        return None  # "Act, 1956", "Central Act", "U.P. Act": no statute named
    return s[:120]


def parse_acts_sections(text: str | None, *, max_acts: int = 25, max_sections: int = 40) -> tuple[list[str], list[str]]:
    """(acts, sections) cited in an order's text, most-cited first.

    Sections are stored with their statute — "Section 438 (Code of Criminal
    Procedure, 1973)" — because a bare "Section 34" means something different
    in every Act. A section with no recognisable statute is dropped, not guessed.
    """
    if not text:
        return [], []
    body = text[:400_000]
    acts: dict[str, int] = {}
    sections: dict[str, int] = {}
    for m in _SECTION_RE.finditer(body):
        act = _canonical_act(m.group("act"))
        if not act:
            continue
        acts[act] = acts.get(act, 0) + 1
        kind = m.group("kind").lower()
        label = "Article" if kind.startswith(("art",)) else "Rule" if kind.startswith("rule") else "Order" if kind.startswith("order") else "Section"
        for num in re.split(r"\s*(?:,|and|&|/|to|read\s+with|r/w)\s*", m.group("nums")):
            num = re.sub(r"\s+", "", num)
            if num:
                key = f"{label} {num} ({act})"
                sections[key] = sections.get(key, 0) + 1
    for m in _ACT_ONLY_RE.finditer(body):
        act = _canonical_act(m.group("act"))
        if act:
            acts[act] = acts.get(act, 0) + 1
    # "Kerala Forest Act" and "Kerala Forest Act, 1961" are one statute.
    merged = _merge_year_variants(acts)
    rename = {re.sub(r",?\s*\d{4}$", "", k): k for k in merged if re.search(r"\d{4}$", k)}
    secs: dict[str, int] = {}
    for key, n in sections.items():
        label, act = key.split(" (", 1)
        act = act.rstrip(")")
        key = f"{label} ({rename.get(act, act)})"
        secs[key] = secs.get(key, 0) + n
    top_acts = [a for a, _ in sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))[:max_acts]]
    top_secs = [s for s, _ in sorted(secs.items(), key=lambda kv: (-kv[1], kv[0]))[:max_sections]]
    return top_acts, top_secs


# ── Supreme Court Reports (SCR) volumes ──────────────────────────────
# The PDF text opens with the reporter's headnote, index and keywords — the
# publisher's copyright (EBC v. D.B. Modak), unlike the judgment itself
# (s.52(1)(q)(iv)). Only the judgment, with its appearance lines, is kept.
_SC_BODY_START_RE = re.compile(
    r"Case\s+Arising\s+From|\b(?:CIVIL|CRIMINAL|ORIGINAL|APPELLATE|ADVISORY|TRANSFER)[A-Z ]*JURISDICTION\b",
)
_SC_JUDGMENT_RE = re.compile(
    r"Judgment\s*/\s*Order\s+of\s+the\s+Supreme\s+Court|The\s+(?:Judgment|Order)\s+of\s+the\s+Court\s+was\s+delivered\s+by",
    re.I,
)
_SC_NEW_COUNSEL_RE = re.compile(
    rf"Advs?\.?\s+for\s+the\s+(?P<side>{_PET_WORDS}|{_RESP_WORDS})[^:]{{0,40}}:\s*(?P<counsel>.*?)"
    r"(?=Advs?\.?\s+for\s+the\b|Judgment\s*/\s*Order|$)",
    re.I | re.S,
)


def sc_judgment_body(text: str | None) -> str | None:
    """The judgment part of an SCR volume's text, or None when it cannot be
    located — in which case nothing is stored rather than risk the headnote."""
    if not text:
        return None
    m = _SC_BODY_START_RE.search(text)
    if not m:
        return None
    return text[m.start():].strip() or None


def parse_sc_counsel(body: str | None) -> tuple[list[str], list[str]]:
    """Counsel from the appearance block that precedes an SC judgment."""
    if not body:
        return [], []
    end = _SC_JUDGMENT_RE.search(body)
    block = body[: end.start()] if end else body[:3000]
    pet: list[str] = []
    resp: list[str] = []
    for m in _SC_NEW_COUNSEL_RE.finditer(block):          # 2023+ SCR layout
        target = pet if _is_petitioner_side(m.group("side")) else resp
        target.extend(n for n in _counsel_names(m.group("counsel")) if n not in target)
    if not (pet or resp):                                  # older "X and Y for the Appellant."
        # Strip the volume's page furniture first: running headers, the A–H
        # margin letters and page numbers that pypdf interleaves with the text.
        clean = re.sub(r"\b\d{0,4}\s*SUPREME COURT REPORTS\s*\[\d{4}\]\s*\d+\s*S\.?C\.?R\.?", " ", block)
        clean = re.sub(r"(?<![A-Za-z.])[A-H](?![A-Za-z.])", " ", clean)   # lone margin letters
        clean = re.sub(r"\s+", " ", clean)
        pos = 0
        for m in re.finditer(rf"\s+for\s+the\s+(?P<side>{_PET_WORDS}|{_RESP_WORDS})\b\.?", clean, re.I):
            chunk = clean[pos:m.start()]
            pos = m.end()
            target = pet if _is_petitioner_side(m.group("side")) else resp
            target.extend(n for n in _trailing_names(chunk) if n not in target)
    return pet, resp


_NOT_A_NAME_RE = re.compile(
    r"\d|\b(?:Judgment|Order|Tribunal|Court|dated|From|No|Nos|Appeal|Petition|JURISDICTION|"
    r"Constitution|Article|Section|Civil|Criminal|Writ|Special|Leave|High|Supreme)\b",
    re.I,
)


def _trailing_names(chunk: str) -> list[str]:
    """The run of person names at the end of an old-SCR appearance chunk.

    The chunk starts wherever the previous side's list ended — typically
    inside "From the Judgment and Order dated 06.02.2009 of the High Court …
    in LPA No. 4 of 2008." — so walk the comma/and-separated pieces backwards
    and keep going only while each piece still looks like a name.
    """
    pieces = [p for p in _COUNSEL_SPLIT_RE.split(chunk) if p and p.strip()]
    kept: list[str] = []
    for piece in reversed(pieces):
        p = " ".join(piece.split()).strip(" .,;:-")
        # The first piece of the run may carry the tail of the previous
        # sentence: keep only what follows its last full stop + capital.
        cand = re.split(r"(?<=[a-z0-9])\.\s+(?=[A-Z])", p)[-1]
        if not cand or _NOT_A_NAME_RE.search(cand) or len(cand.split()) > 5:
            if cand != p and cand and not _NOT_A_NAME_RE.search(cand):
                kept.append(cand)
            break
        kept.append(cand)
    names: list[str] = []
    for n in _counsel_names(" , ".join(reversed(kept))):
        if n not in names:
            names.append(n)
    return names


def normalise_judges(judges: list[str] | None) -> str | None:
    """Bare, title-cased, de-duplicated names joined with " | " — or None."""
    names: set[str] = set()
    for raw in judges or []:
        for piece in _JUDGE_SPLIT_RE.split(raw or ""):
            bare = _JUDGE_STRIP_RE.sub("", piece.strip()).strip()
            if bare and not is_placeholder_judge(bare):
                names.add(bare.title())
    return " | ".join(sorted(names)) or None
