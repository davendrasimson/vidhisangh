"""Derive structured fields from a Supreme Court judgment PDF.

Fills the fields the AWS Open Data corpus does not carry — ``acts``,
``sections``, ``keywords``, ``bench`` and ``headnote`` — from the judgment
document itself, following the pluggable-seam pattern used by storage, payments
and link_preview: a rule-based extractor by default, swappable via
:func:`set_judgment_enricher` so tests (and a future LLM summariser) can plug in
without touching callers.

What is extracted, and why it is safe
-------------------------------------
* **Facts, not expression.** Act names, section numbers, judge names and the
  index terms in the reports' own "List of Keywords" block are factual metadata.
  Copyright protects expression, not facts.
* **The headnote is the Court's own words.** SCR PDFs carry an official headnote,
  but it is editorial work — the documents credit it ("Headnotes prepared by:
  <name>"), which is exactly what *Eastern Book Company v. D.B. Modak* (2008)
  held to be protected. So it is deliberately NOT copied. Instead the operative
  disposal sentences are taken from the body of the judgment, whose reproduction
  is expressly permitted by s.52(1)(q)(iv) of the Copyright Act.

Two report formats
------------------
Newer reports (roughly 2024 onward) print explicit ``List of Acts`` and
``List of Keywords`` blocks; older ones do not. The extractor prefers those
blocks when present and falls back to pattern matching over the text otherwise,
so the whole 1950–2026 range is covered.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import structlog

log = structlog.get_logger("app.judgment_enrichment")

# ── Report structure ────────────────────────────────────────────────
_LIST_BLOCK = (
    r"List of {label}\s*(.*?)(?=\n?\s*(?:List of |Case Arising From|Headnotes|\d+\s*\[\d{{4}}\]))"
)
_ACTS_BLOCK = re.compile(_LIST_BLOCK.format(label="Acts"), re.S)
_KEYWORDS_BLOCK = re.compile(_LIST_BLOCK.format(label="Keywords"), re.S)

# "[C.T. Ravikumar and Sanjay Karol,* JJ.]" — the coram, i.e. the real bench.
_CORAM = re.compile(r"\[([^\]\n]{5,220}?),?\s*(JJ|J)\.\s*\]")
_JUDGE_SPLIT = re.compile(r"\s+and\s+|,", re.I)

_ACT_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z’'&.\-]+(?:\s+(?:of|and|the|for|to|[A-Z][A-Za-z’'&.\-]+)){0,8}?"
    r"\s+(?:Act|Code))\s*,\s*(\d{4})\b"
)
_CONSTITUTION = re.compile(r"\bConstitution of India\b")
_SECTION = re.compile(r"\b(?:[Ss]ections?|[Ss]s?\.)\s*(\d+[A-Z]{0,3})")
_ARTICLE = re.compile(r"\b[Aa]rticles?\s*(\d+[A-Z]{0,2})")

_BODY_MARKERS = (
    "CRIMINAL APPELLATE JURISDICTION", "CIVIL APPELLATE JURISDICTION",
    "ORIGINAL JURISDICTION", "CRIMINAL ORIGINAL JURISDICTION", "Case Arising From",
)
# Page furniture and editorial trailers that must never reach a headnote.
_TRAILER = re.compile(
    r"(Result of the case|†?Headnotes prepared by|Digital Supreme Court Reports"
    r"|\(Assisted by\s*:|©|Downloaded on)"
)
_DISPOSAL = re.compile(
    r"\b(appeal|petition|application|writ|revision)s?\b[^.]{0,90}?"
    r"\b(allowed|dismissed|disposed|set aside|quashed|succeeds?|fails?)\b",
    re.I,
)
_DISPOSAL_SENTENCE = re.compile(
    r"[^.]*\b(?:allowed|dismissed|disposed of|set aside|quashed|succeeds|remanded)\b[^.]*\.",
    re.I,
)
# Reports end with the compiler's name and a result stamp ("Devika Gujral
# Appeal dismissed."). That is editorial furniture, not the Court's words.
_RESULT_STAMP = re.compile(
    r"(?:[A-Z][a-z’']+\s+){0,3}(?:Appeals?|Petitions?|Writ Petitions?|Matters?)\s+"
    r"(?:allowed|dismissed|disposed of|partly allowed|dismissed as withdrawn)\s*\.?\s*$",
    re.I,
)
# A lone margin letter (SCR prints A–H down the page gutter) stranded between words.
_MARGIN_LETTER = re.compile(r"(?<=[a-z,;])\s+[B-H]\s+(?=[a-z])")
# Trailing gutter letters / stray punctuation left at the end of an extract.
_TRAILING_NOISE = re.compile(r"[\s·•.,;:*]*\b[A-H]\b[\s·•.,;:*]*$")
# Role markers that sit in the coram line but are not judges' names.
_ROLE_TOKENS = {"cji", "cj", "j", "jj", "jj.", "j.", "author"}

_BENCH_BY_SIZE = {
    1: "Single Judge", 2: "Division Bench", 3: "Three-Judge Bench",
    4: "Four-Judge Bench", 5: "Constitution Bench", 7: "Seven-Judge Bench",
    9: "Nine-Judge Bench", 11: "Eleven-Judge Bench", 13: "Thirteen-Judge Bench",
}

# Controlled vocabulary for older reports that carry no keyword index.
_TOPIC_VOCABULARY: dict[str, tuple[str, ...]] = {
    "bail": ("bail", "anticipatory bail"),
    "limitation": ("limitation act", "barred by limitation", "condonation of delay"),
    "arbitration": ("arbitration", "arbitral award", "arbitrator"),
    "insolvency": ("insolvency", "corporate debtor", "resolution professional"),
    "land acquisition": ("land acquisition", "acquisition of land", "compensation for land"),
    "service law": ("seniority", "promotion", "departmental enquiry", "regularisation"),
    "criminal law": ("conviction", "acquittal", "charge sheet", "prosecution"),
    "murder": ("murder", "section 302"),
    "cheque dishonour": ("dishonour", "section 138", "negotiable instruments"),
    "tax": ("income tax", "assessing officer", "gst", "excise", "customs duty"),
    "constitutional law": ("fundamental right", "article 14", "article 21", "ultra vires"),
    "writ jurisdiction": ("article 226", "writ petition", "mandamus"),
    "contempt": ("contempt of court", "contemnor"),
    "family law": ("maintenance", "divorce", "custody", "matrimonial"),
    "property": ("gift deed", "sale deed", "title", "possession of the suit"),
    "consumer": ("consumer", "deficiency in service"),
    "environment": ("environmental", "pollution", "forest"),
    "reservation": ("reservation", "scheduled caste", "other backward"),
    "electricity": ("electricity", "tariff"),
    "motor accident": ("motor accident", "compensation to the claimant"),
}


@dataclass(slots=True)
class Enrichment:
    """Structured fields derived from one judgment."""

    acts: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    bench: str | None = None
    judges: list[str] = field(default_factory=list)
    headnote: str | None = None

    def is_empty(self) -> bool:
        return not (self.acts or self.sections or self.keywords or self.bench or self.headnote)


@runtime_checkable
class Enricher(Protocol):
    def enrich(self, text: str) -> Enrichment: ...


# ── Helpers ─────────────────────────────────────────────────────────
def extract_text(pdf_bytes: bytes) -> str:
    """Plain text of a judgment PDF (empty string if it cannot be parsed)."""
    from pypdf import PdfReader  # imported lazily — only ingestion needs it

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:  # a corrupt or scanned PDF must not kill a batch
        log.warning("pdf_parse_failed", error=str(exc))
        return ""


def _norm(value: str) -> str:
    return " ".join(value.split())


def _split_index_block(block: str) -> list[str]:
    items: list[str] = []
    for part in re.split(r"[;\n]", block):
        cleaned = _norm(part).strip(" .;·-")
        if 2 < len(cleaned) < 160 and cleaned not in items:
            items.append(cleaned)
    return items


def _dedupe_acts(names: list[str]) -> list[str]:
    """Drop names that are just a shorter tail of another ("Penal Code, 1860"
    when "Indian Penal Code, 1860" is also present), plus obvious debris.

    Page breaks can split a title from its year, leaving fragments like "1881"
    or "Negotiable Instruments Act," — neither is a usable Act name.
    """
    cleaned: set[str] = set()
    for raw in names:
        name = _norm(raw).strip(" ,;")
        if len(name) < 8 or name.isdigit():
            continue
        # Must read as "<Something> Act/Code/Constitution[, YEAR]".
        if not re.search(r"\b(Act|Code|Constitution|Rules|Regulations)\b", name):
            continue
        cleaned.add(name)

    ordered = sorted(cleaned, key=len, reverse=True)
    kept: list[str] = []
    for name in ordered:
        # A suffix of one already kept, or the year-less form of one ("X" vs "X, 1950").
        if any(longer.endswith(name) or longer.startswith(name + ",") for longer in kept):
            continue
        kept.append(name)
    return sorted(kept)


def _tidy(text: str) -> str:
    """Strip gutter letters and the reporter's trailing result stamp.

    Applied repeatedly because they nest: "… Appeals disposed of B" needs the
    stray "B" gone before the stamp itself matches at the end of the string.
    """
    cleaned = _MARGIN_LETTER.sub(" ", _norm(text))
    for _ in range(3):
        before = cleaned
        cleaned = _TRAILING_NOISE.sub("", cleaned).strip()
        cleaned = _RESULT_STAMP.sub("", cleaned).strip()
        if cleaned == before:
            break
    return cleaned.strip(" ·•,;:")


def _judgment_body(text: str) -> str:
    """Text from the start of the judgment proper, past the editorial headnote."""
    positions = [text.find(marker) for marker in _BODY_MARKERS]
    starts = [p for p in positions if p > 0]
    return text[min(starts):] if starts else text


class RuleBasedEnricher:
    """Pattern-based extraction over the report text. No network, no model."""

    def enrich(self, text: str) -> Enrichment:
        if not text.strip():
            return Enrichment()
        flat = _norm(text)
        result = Enrichment()

        # ── Acts: prefer the report's own index, else pattern-match ──
        block = _ACTS_BLOCK.search(text)
        if block:
            result.acts = _dedupe_acts(_split_index_block(block.group(1)))
        if not result.acts:
            found = [f"{_norm(m.group(1))}, {m.group(2)}" for m in _ACT_PATTERN.finditer(flat)]
            # Guard against the index label being swept into a match.
            found = [f for f in found if "List of" not in f]
            result.acts = _dedupe_acts(found)[:8]
        if _CONSTITUTION.search(flat) and not any(
            a.startswith("Constitution of India") for a in result.acts
        ):
            result.acts.append("Constitution of India")

        # ── Sections & Articles ─────────────────────────────────────
        sections = {f"Section {s}" for s in _SECTION.findall(flat)}
        articles = {f"Article {a}" for a in _ARTICLE.findall(flat)}
        result.sections = sorted(sections, key=_section_sort)[:12] + sorted(
            articles, key=_section_sort
        )[:6]

        # ── Keywords: the report's index, else a topic vocabulary ───
        kw_block = _KEYWORDS_BLOCK.search(text)
        if kw_block:
            result.keywords = [
                k for k in _split_index_block(kw_block.group(1))
                if not re.match(r"(?i)^(section|article)s?\b", k)
            ][:12]
        if not result.keywords:
            lowered = flat.lower()
            result.keywords = [
                topic for topic, needles in _TOPIC_VOCABULARY.items()
                if any(n in lowered for n in needles)
            ][:8]

        # ── Bench, from the coram line ──────────────────────────────
        coram = _CORAM.search(text)
        if coram:
            names = [
                _norm(n).strip("*,. ") for n in _JUDGE_SPLIT.split(coram.group(1))
                if _norm(n).strip("*,. ")
            ]
            # "B.R. Gavai, CJI and ..." — CJI/J/JJ are roles, not judges.
            names = [
                n for n in names
                if 2 < len(n) < 60 and n.lower().rstrip(".") not in _ROLE_TOKENS
            ]
            if names:
                result.judges = [
                    n if n.lower().startswith("justice") else f"Justice {n.title()}"
                    for n in names
                ]
                result.bench = _BENCH_BY_SIZE.get(len(names), f"{len(names)}-Judge Bench")

        result.headnote = self._headnote(text)
        return result

    def _headnote(self, text: str) -> str | None:
        """The Court's own operative disposal, never the editorial headnote."""
        body = _judgment_body(text)
        paragraphs = re.findall(
            r"(?m)^\s*\d{1,3}\.\s+(.{60,2000}?)(?=\n\s*\d{1,3}\.\s|\Z)", body, re.S
        )
        candidates = [p for p in paragraphs if _DISPOSAL.search(p)]
        if not candidates:
            source = paragraphs[-1] if paragraphs else ""
        else:
            # Prefer the last *substantive* disposal paragraph. The final one is
            # often boilerplate ("Pending applications shall stand disposed of"),
            # which says nothing about what the Court actually decided.
            substantive = [p for p in candidates if len(_norm(p)) >= 160]
            source = (substantive or candidates)[-1]

        source = _tidy(_TRAILER.split(source)[0])
        if not source:
            return None

        sentences = [m.group(0).strip() for m in _DISPOSAL_SENTENCE.finditer(source)]
        summary = _norm(" ".join(sentences)) if sentences else source
        if len(summary) < 40:
            summary = source
        return _tidy(summary)[:1200] or None


def _section_sort(label: str) -> tuple[int, str]:
    digits = re.sub(r"\D", "", label)
    return (int(digits) if digits else 0, label)


_enricher: Enricher | None = None


def get_judgment_enricher() -> Enricher:
    global _enricher
    if _enricher is None:
        _enricher = RuleBasedEnricher()
    return _enricher


def set_judgment_enricher(enricher: Enricher | None) -> None:
    """Swap the extractor (tests, or a future LLM-backed summariser)."""
    global _enricher
    _enricher = enricher
