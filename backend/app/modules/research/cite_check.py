"""Cite check — find every case citation in a draft and verify it against the corpus.

Deterministic, no LLM. A draft (pasted text or a .docx) is scanned for Indian
case citations — SCR, INSC and High Court neutral citations, SCC / SCC OnLine,
AIR, SCALE, JT, Cri LJ — and each distinct citation is resolved against the
research library in three tiers:

1. ``verified``         exact match on the corpus citation (SCR) or neutral
                        citation (INSC / High Court) — the record is linked.
2. ``matched_by_name``  the reporter is one the corpus does not key by (SCC,
                        AIR, …) but the case named before the citation is found
                        in the Supreme Court corpus for that year window.
                        ``possible_matches`` when several records fit.
3. ``cited_elsewhere``  the citation string itself appears in other judgments'
                        text — the authority exists even though the library has
                        no record keyed by it.
   ``not_found``        nothing — the citation needs manual verification; a
                        fabricated or mistyped citation looks exactly like this.

The output is a first pass for a lawyer to review, never a conclusion about
whether the cited case supports the proposition — that needs reading the case.
"""

from __future__ import annotations

import re
import time
import zipfile
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from typing import TYPE_CHECKING

from docx import Document as DocxDocument

from app.core.exceptions import ValidationError
from app.modules.drafting.docx_import import _validate_container
from app.modules.research.models import CourtLevel, Judgment

if TYPE_CHECKING:
    from app.modules.research.repository import ResearchRepository

MAX_TEXT_CHARS = 300_000
MAX_DISTINCT_CITATIONS = 150
_CONTEXT_CHARS = 90


# ── Citation grammar ─────────────────────────────────────────────────────
# Each rule: kind (how it is resolved), reporter label, regex, normaliser.
# Order matters only for overlapping spans: the first rule to claim a span wins,
# so the more specific forms (SCC OnLine before SCC) come first.

def _scr(m: re.Match) -> str:
    supp = " SUPP." if m.group("supp") else ""
    return f"[{m.group('y')}]{supp} {int(m.group('v'))} S.C.R. {int(m.group('p'))}"


def _insc(m: re.Match) -> str:
    return f"{m.group('y')} INSC {int(m.group('n'))}"


def _neutral(m: re.Match) -> str:
    return m.group(0).upper().replace(" ", "")


def _scc_online(m: re.Match) -> str:
    return f"{m.group('y')} SCC OnLine {m.group('c')} {int(m.group('p'))}"


def _scc(m: re.Match) -> str:
    series = f" ({m.group('s')})" if m.group("s") else ""
    return f"({m.group('y')}) {int(m.group('v'))} SCC{series} {int(m.group('p'))}"


def _scc_supp(m: re.Match) -> str:
    return f"{m.group('y')} Supp ({int(m.group('v'))}) SCC {int(m.group('p'))}"


def _air(m: re.Match) -> str:
    return f"AIR {m.group('y')} {m.group('c')} {int(m.group('p'))}"


def _scale(m: re.Match) -> str:
    return f"{m.group('y')} ({int(m.group('v'))}) SCALE {int(m.group('p'))}"


def _jt(m: re.Match) -> str:
    return f"JT {m.group('y')} ({int(m.group('v'))}) SC {int(m.group('p'))}"


def _crilj(m: re.Match) -> str:
    return f"{m.group('y')} Cri LJ {int(m.group('p'))}"


_YEAR = r"(?P<y>(?:19|20)\d{2})"
_RULES: list[tuple[str, str, re.Pattern[str], object]] = [
    # "[2019] 4 S.C.R. 532", "(2019) 4 SCR 532", "[1996] Supp. 1 S.C.R. 499"
    ("scr", "S.C.R.", re.compile(
        rf"[\[(]\s*{_YEAR}\s*[\])]\s*(?:(?P<supp>Supp\.?)\s*)?\(?(?P<v>\d{{1,2}})\)?\s*S\.?\s?C\.?\s?R\.?(?![A-Za-z])\s*(?P<p>\d{{1,5}})\b",
        re.I), _scr),
    # "2019 (4) SCR 532"
    ("scr", "S.C.R.", re.compile(
        rf"\b{_YEAR}\s*\((?P<v>\d{{1,2}})\)\s*(?P<supp>)S\.?\s?C\.?\s?R\.?(?![A-Za-z])\s*(?P<p>\d{{1,5}})\b", re.I), _scr),
    ("insc", "INSC", re.compile(rf"\b{_YEAR}\s+INSC\s+(?P<n>\d{{1,5}})\b"), _insc),
    ("neutral", "Neutral citation", re.compile(
        r"\b(?P<y>(?:19|20)\d{2}):(?P<c>[A-Z]{2,6}(?:-[A-Z]{2,4})?):(?P<n>\d{1,7})(?P<db>-DB)?\b"), _neutral),
    ("reporter", "SCC OnLine", re.compile(
        rf"\b{_YEAR}\s+SCC\s+OnLine\s+(?P<c>[A-Z][A-Za-z&]{{0,5}})\s+(?P<p>\d{{1,6}})\b"), _scc_online),
    ("reporter", "SCC", re.compile(
        rf"{_YEAR}\s+Supp\.?\s*\(?(?P<v>\d{{1,2}})\)?\s*SCC\s+(?P<p>\d{{1,5}})\b", re.I), _scc_supp),
    ("reporter", "SCC", re.compile(
        rf"\(?{_YEAR}\)?\s*\(?(?P<v>\d{{1,3}})\)?\s*SCC(?!\s*OnLine)\s*(?:\((?P<s>Cri|Civ|L&S|Cr)\)\s*)?(?P<p>\d{{1,5}})\b"), _scc),
    ("reporter", "AIR", re.compile(
        rf"\bAIR\s+{_YEAR}\s+(?P<c>SCW|SC|[A-Z][A-Za-z&]{{1,4}})\s+(?P<p>\d{{1,6}})\b"), _air),
    ("reporter", "SCALE", re.compile(rf"\b{_YEAR}\s*\((?P<v>\d{{1,2}})\)\s*SCALE\s+(?P<p>\d{{1,5}})\b"), _scale),
    ("reporter", "JT", re.compile(rf"\bJT\s+{_YEAR}\s*\((?P<v>\d{{1,2}})\)\s*SC\s+(?P<p>\d{{1,5}})\b"), _jt),
    ("reporter", "Cri LJ", re.compile(rf"\b{_YEAR}\s+Cr(?:i)?\.?\s?L\.?\s?J\.?\s+(?P<p>\d{{1,5}})\b"), _crilj),
]


@dataclass
class Occurrence:
    start: int
    end: int
    raw: str
    context: str
    case_name: str | None


@dataclass
class FoundCitation:
    kind: str
    reporter: str
    normalised: str
    year: int
    occurrences: list[Occurrence] = field(default_factory=list)

    @property
    def case_names(self) -> list[str]:
        seen: list[str] = []
        for o in self.occurrences:
            if o.case_name and o.case_name not in seen:
                seen.append(o.case_name)
        return seen


# "v." has no word boundary after the dot, so the ends are spelled out.
_VS_RE = re.compile(r"(?<![A-Za-z])(?:versus|vs\.?|v\.?)(?=\s)", re.I)
_BOUNDARY_RE = re.compile(r"[.;:!?]\s+|\n|\(|—|–|\s-\s|\bsee\s|\bvide\s|\bin\s(?=[A-Z])", re.I)
# A full stop after one of these is part of a name, not the end of a sentence.
_NAME_ABBREVIATIONS = {
    "ltd", "pvt", "co", "inc", "corpn", "ors", "anr", "smt", "shri", "sri", "dr", "mr", "mrs", "ms", "no", "nos",
    "hon'ble", "retd", "jr", "sr", "st", "bros", "llp", "m/s", "etc", "govt", "dept", "deptt", "u.p", "m.p", "a.p",
    "h.p", "j&k", "t.n", "w.b", "n.c.t",
}
_CITATION_LIKE_RE = re.compile(r"\d{4}|\bSCC\b|\bSCR\b|\bAIR\b|\bINSC\b|\bSCALE\b", re.I)


def _last_clause(left: str) -> str:
    """The text after the last real sentence/clause boundary (initials and 'Ltd.' are not one)."""
    cut = 0
    for m in _BOUNDARY_RE.finditer(left):
        if m.group(0)[0] == ".":
            before = left[: m.start()]
            token = re.split(r"[\s(]", before)[-1].lower() if before else ""
            # "K.S. Puttaswamy", "U.P.", "Ltd." — initials or an abbreviation before the
            # dot are part of a name; "4." (a list number) is a boundary.
            if re.fullmatch(r"(?:[a-z]\.)*[a-z]", token) or token.rstrip(".") in _NAME_ABBREVIATIONS or token in _NAME_ABBREVIATIONS:
                continue
        cut = m.end()
    return left[cut:]
_LEAD_WORDS_RE = re.compile(
    r"^(?:(?:also|and|the|decision|decisions|judgment|judgments|case|of|this|hon'?ble|court|courts|supreme|apex|"
    r"relied|on|upon|reliance|placed|cited|following|followed|held|ratio|refer|referred|to|by|a|an|as|at|that|"
    r"was|were|is|are|been|has|had|have|it|its|he|she|they|their|further|reported|laid|down|law|principle|"
    r"matter|para|paras|paragraph|see|vide|in)\s+)+",
    re.I,
)
_TRAIL_WORDS_RE = re.compile(
    r"(?:\s+(?:reported|reported\s+in|reported\s+at|in|at|as|and|supra|cited|decided\s+on|dated)\s*[,.;:]?)+$",
    re.I,
)
_CASE_NAME_WINDOW = 220


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", fragment).strip(" ,;:-–—\t\n")


def _case_name_before(text: str, start: int) -> str | None:
    """'X v. Y' named immediately before a citation, if the sentence reads that way."""
    window = text[max(0, start - _CASE_NAME_WINDOW):start]
    vs_matches = list(_VS_RE.finditer(window))
    if not vs_matches:
        return None
    vs = vs_matches[-1]
    left = window[: vs.start()]
    right = window[vs.end():]
    # Petitioner: the last clause before "v." — cut at the previous sentence or bracket.
    petitioner = _clean(_last_clause(left))
    petitioner = _LEAD_WORDS_RE.sub("", petitioner).strip()
    # Respondent: up to the citation, less filler like "reported in". If another
    # citation or a sentence end lies between "v." and this citation, the name
    # belongs to something earlier, not to this citation.
    respondent = _clean(right)
    respondent = _TRAIL_WORDS_RE.sub("", respondent).strip(" ,;:")
    if _CITATION_LIKE_RE.search(respondent) or re.search(r"[.;:]\s+[A-Z]", respondent) or len(respondent.split()) > 10:
        return None
    if not petitioner or not respondent or len(petitioner) > 120 or len(respondent) > 120:
        return None
    if not re.search(r"[A-Za-z]{2}", petitioner) or not re.search(r"[A-Za-z]{2}", respondent):
        return None
    return f"{petitioner} v. {respondent}"


def find_citations(text: str) -> list[FoundCitation]:
    """Every distinct citation in the text, with each place it occurs."""
    if len(text) > MAX_TEXT_CHARS:
        raise ValidationError(f"The text is too long to check at once ({len(text):,} characters; the limit is {MAX_TEXT_CHARS:,}).")
    claimed: list[tuple[int, int]] = []
    found: dict[str, FoundCitation] = {}
    for kind, reporter, pattern, normalise in _RULES:
        for m in pattern.finditer(text):
            start, end = m.span()
            if any(s < end and start < e for s, e in claimed):
                continue
            claimed.append((start, end))
            normalised = normalise(m)  # type: ignore[operator]
            year = int(m.group("y"))
            ctx_start, ctx_end = max(0, start - _CONTEXT_CHARS), min(len(text), end + _CONTEXT_CHARS)
            context = re.sub(r"\s+", " ", text[ctx_start:ctx_end]).strip()
            occ = Occurrence(start, end, m.group(0), context, _case_name_before(text, start))
            if normalised not in found:
                found[normalised] = FoundCitation(kind, reporter, normalised, year)
            found[normalised].occurrences.append(occ)
    ordered = sorted(found.values(), key=lambda c: c.occurrences[0].start)
    for c in ordered:
        c.occurrences.sort(key=lambda o: o.start)
    return ordered


# ── Party-name matching ──────────────────────────────────────────────────
_NAME_STOP = {
    "state", "union", "india", "govt", "government", "limited", "ltd", "private", "pvt", "company", "co",
    "corporation", "corpn", "and", "others", "another", "anr", "ors", "through", "the", "of", "m/s", "ms",
    "smt", "shri", "sri", "mr", "mrs", "dr", "its", "by", "rep", "represented", "secretary", "principal",
    "chief", "commissioner", "collector", "district", "officer", "board", "authority", "department", "deptt",
    "national", "central", "bank", "bharat", "nct", "delhi", "etc", "anor", "thr", "lrs", "lr", "dead", "deceased",
}


def _tokens(side: str) -> list[str]:
    out: list[str] = []
    for raw in re.split(r"[^A-Za-z]+", side):
        tok = raw.lower()
        if len(tok) >= 4 and tok not in _NAME_STOP and tok not in out:
            out.append(tok)
    return out


def party_tokens(case_name: str) -> list[str]:
    """Distinctive words from both sides of 'X v. Y' to look the case up by."""
    sides = re.split(r"\s+v\.\s+", case_name, maxsplit=1)
    if len(sides) != 2:
        return _tokens(case_name)[:3]
    left, right = (_tokens(s) for s in sides)
    picked = left[:2] + right[:2]
    # Fall back to anything distinctive when a side is all stop-words ("State of X").
    # Stop-words never qualify: "State of Punjab v. Others" yields nothing rather
    # than a lookup on "state"/"others", which match most of the corpus.
    if not picked:
        picked = [t for t in _tokens(case_name) if len(t) >= 5][:3]
    return picked[:4]


def _year_window(year: int, kind: str) -> tuple[date, date]:
    # A reporter volume year is the year of publication: the judgment is usually
    # that year or the one before, occasionally two before. Neutral citations
    # carry the decision year itself.
    back = 0 if kind in {"scr", "insc", "neutral"} else 2
    return date(year - back, 1, 1), date(year, 12, 31)


# ── Resolution ───────────────────────────────────────────────────────────
@dataclass
class JudgmentRef:
    id: str
    case_name: str
    citation: str | None
    neutral_citation: str | None
    court: str
    judgment_date: date | None

    @classmethod
    def of(cls, j: Judgment) -> "JudgmentRef":
        return cls(str(j.id), j.cause_title or j.case_name, j.citation, j.neutral_citation, j.court, j.judgment_date)


@dataclass
class Finding:
    citation: str
    reporter: str
    kind: str
    year: int
    case_name_as_cited: str | None
    occurrences: int
    contexts: list[str]
    status: str
    judgment: JudgmentRef | None = None
    candidates: list[JudgmentRef] = field(default_factory=list)
    cited_in_count: int = 0
    cited_in_examples: list[JudgmentRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _name_warning(cited: str | None, matched: Judgment) -> str | None:
    if not cited:
        return None
    toks = party_tokens(cited)
    hay = (matched.cause_title or matched.case_name or "").lower()
    missing = [t for t in toks if t not in hay]
    if missing and len(missing) == len(toks):
        return f"The record's title does not contain the names cited ({cited})."
    return None


def _year_warning(found: FoundCitation, matched: Judgment) -> str | None:
    if matched.judgment_date is None:
        return None
    lo, hi = _year_window(found.year, found.kind)
    if not (lo <= matched.judgment_date <= hi):
        return (
            f"Cited as a {found.year} authority but the record was decided on "
            f"{matched.judgment_date:%d/%m/%Y}; check the citation."
        )
    return None


async def _resolve(repo: "ResearchRepository", found: FoundCitation, budget: "_Budget") -> Finding:
    names = found.case_names
    finding = Finding(
        citation=found.normalised, reporter=found.reporter, kind=found.kind, year=found.year,
        case_name_as_cited=names[0] if names else None, occurrences=len(found.occurrences),
        contexts=[o.context for o in found.occurrences[:3]], status="not_found",
    )
    if len(names) > 1:
        finding.warnings.append("Cited under more than one case name: " + " / ".join(names[:3]))

    # Tier 1 — the corpus keys this citation directly.
    exact: Judgment | None = None
    if found.kind == "scr":
        exact = await repo.get_by_citation(found.normalised)
    elif found.kind in {"insc", "neutral"}:
        exact = await repo.get_by_neutral_citation(found.normalised)
        if exact is None and found.kind == "neutral":
            alt = found.normalised[:-3] if found.normalised.endswith("-DB") else found.normalised + "-DB"
            exact = await repo.get_by_neutral_citation(alt)
    # Tier 1b — a parallel citation the library has mapped (mined from judgment
    # texts or curated): "(2017) 10 SCC 1" → the SCR record.
    alias = None
    if exact is None and found.kind == "reporter":
        hit = await repo.get_alias(found.normalised)
        if hit is not None:
            alias, exact = hit
    if exact is not None:
        finding.status = "verified"
        finding.judgment = JudgmentRef.of(exact)
        if alias is not None:
            agree = alias.support
            finding.warnings.append(
                f"Resolved through the library's parallel-citation table ({'curated' if alias.source == 'curated' else f'{agree} citing judgment{'s' if agree != 1 else ''} name this case next to the citation'}); "
                f"the library keys it as {exact.citation or exact.neutral_citation}."
            )
        for w in (_name_warning(finding.case_name_as_cited, exact), _year_warning(found, exact)):
            if w:
                finding.warnings.append(w)
        return finding

    # Tier 2 — look the named case up in the Supreme Court corpus.
    if finding.case_name_as_cited and found.kind != "neutral":
        tokens = party_tokens(finding.case_name_as_cited)
        if tokens:
            lo, hi = _year_window(found.year, found.kind)
            rows = await repo.find_by_parties(tokens, lo, hi, CourtLevel.SUPREME_COURT, limit=4)
            if len(rows) == 1:
                finding.status = "matched_by_name"
                finding.judgment = JudgmentRef.of(rows[0])
                finding.warnings.append(
                    f"Matched on the parties' names and year; the library keys this case as "
                    f"{rows[0].citation or rows[0].neutral_citation or 'an unreported record'}, not {found.normalised}."
                )
            elif len(rows) > 1:
                finding.status = "possible_matches"
                finding.candidates = [JudgmentRef.of(r) for r in rows]

    # Tier 3 — does any Supreme Court judgment in the library cite this string?
    # Only when nothing else resolved it, and only while the request's time
    # budget lasts: the phrase lookup is best effort (see repository.mentions).
    if finding.status == "not_found" and found.kind in {"reporter", "scr", "insc"}:
        if budget.spent():
            finding.warnings.append("The search for judgments citing this string was skipped to keep the check quick; verify the citation against the reporter.")
        else:
            result = await repo.mentions(found.normalised, limit=3)
            if result is None:
                finding.warnings.append("The search for judgments citing this string took too long and was skipped; verify the citation against the reporter.")
            else:
                count, examples = result
                finding.cited_in_count = count
                finding.cited_in_examples = [JudgmentRef.of(j) for j in examples]
                if count:
                    finding.status = "cited_elsewhere"
    if finding.status == "not_found" and not finding.warnings:
        finding.warnings.append("No record and no citing judgment found: verify this citation against the reporter before filing.")
    elif finding.status == "not_found" and not any("verify" in w for w in finding.warnings):
        finding.warnings.append("Verify this citation against the reporter before filing.")
    return finding


class _Budget:
    """Wall-clock budget for the best-effort lookups across one request."""

    def __init__(self, seconds: float) -> None:
        self.deadline = time.monotonic() + seconds

    def spent(self) -> bool:
        return time.monotonic() > self.deadline


MENTIONS_BUDGET_SECONDS = 8.0


async def check_text(repo: "ResearchRepository", text: str) -> tuple[list[Finding], int, bool]:
    """(findings, citations found in all, truncated?) for a draft's text."""
    found = find_citations(text)
    total = sum(len(c.occurrences) for c in found)
    truncated = len(found) > MAX_DISTINCT_CITATIONS
    budget = _Budget(MENTIONS_BUDGET_SECONDS)
    findings = [await _resolve(repo, c, budget) for c in found[:MAX_DISTINCT_CITATIONS]]
    return findings, total, truncated


# ── .docx text ───────────────────────────────────────────────────────────
_W_T_RE = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.S)
_W_P_END_RE = re.compile(r"</w:p>")
_XML_ENTITY = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'"}


def _xml_part_text(data: bytes, name: str) -> str:
    """Plain text of one WordprocessingML part (footnotes/endnotes), paragraph per line."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            if name not in archive.namelist():
                return ""
            xml = archive.read(name).decode("utf-8", errors="ignore")
    except (zipfile.BadZipFile, KeyError):
        return ""
    xml = _W_P_END_RE.sub("\n", xml)
    pieces = []
    for chunk in xml.split("\n"):
        line = "".join(_W_T_RE.findall(chunk))
        for ent, ch in _XML_ENTITY.items():
            line = line.replace(ent, ch)
        if line.strip():
            pieces.append(line)
    return "\n".join(pieces)


def extract_docx_text(data: bytes) -> str:
    """Body paragraphs, table cells, footnotes and endnotes of a Word file."""
    _validate_container(data)
    try:
        document = DocxDocument(BytesIO(data))
    except Exception as exc:  # python-docx raises several unrelated types
        raise ValidationError("The uploaded file is not a valid Word document.") from exc
    lines = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    for part in ("word/footnotes.xml", "word/endnotes.xml"):
        extra = _xml_part_text(data, part)
        if extra:
            lines.append(extra)
    text = "\n".join(lines)
    if len(text) > MAX_TEXT_CHARS:
        raise ValidationError(f"The document is too long to check at once ({len(text):,} characters; the limit is {MAX_TEXT_CHARS:,}).")
    return text
