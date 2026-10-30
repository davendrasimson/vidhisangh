"""Pydantic schemas for the legal research module."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.research.models import CitationRelationship, CourtLevel


class JudgmentCreate(BaseModel):
    case_name: str = Field(min_length=2, max_length=500)
    citation: str = Field(min_length=1, max_length=200)
    neutral_citation: str | None = Field(default=None, max_length=200)
    # eCourts CNR — groups this order with the case's other orders.
    cnr_number: str | None = Field(default=None, min_length=10, max_length=20)
    court: str = Field(min_length=1, max_length=200)
    court_level: CourtLevel = CourtLevel.OTHER
    bench: str | None = Field(default=None, max_length=120)
    judges: list[str] = Field(default_factory=list, max_length=15)
    judgment_date: date | None = None
    acts: list[str] = Field(default_factory=list, max_length=30)
    sections: list[str] = Field(default_factory=list, max_length=50)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    headnote: str | None = Field(default=None, max_length=20000)
    outcome: str | None = Field(default=None, max_length=300)
    url: str | None = Field(default=None, max_length=500)
    # Optional full text of the order/judgment (pasted or from a document).
    full_text: str | None = Field(default=None, max_length=2_000_000)


class _RegistryFields(BaseModel):
    """Structured fields shared by list and detail shapes (migration 0036)."""

    model_config = ConfigDict(from_attributes=True)
    # High Court order records carry no citation — only reported judgments do.
    citation: str | None
    cnr_number: str | None = None
    case_type: str | None = None
    case_number: str | None = None
    case_year: int | None = None
    # Title with the "TYPE/NUM/YEAR of" prefix stripped; null until backfilled.
    cause_title: str | None = None
    # Normalised bare judge names — what to display and filter by. The raw
    # provider strings stay in `judges` on the detail shape.
    judge_names: list[str] = Field(default_factory=list)
    # Case parties and counsel (migration 0039). Advocates are only known where
    # the registry prints them in the order's opening.
    filed_on: date | None = None
    petitioner: str | None = None
    respondent: str | None = None
    petitioner_advocates: list[str] = Field(default_factory=list)
    respondent_advocates: list[str] = Field(default_factory=list)


def _split_judges(value: str | None) -> list[str]:
    return [name for name in (value or "").split(" | ") if name]


class CaseOrder(BaseModel):
    """One order/judgment in a case's timeline."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    judgment_date: date | None
    judge_names: list[str] = Field(default_factory=list)
    outcome: str | None
    url: str | None
    # The registry's opening line of the order — enough to tell orders apart.
    summary: str | None = None

    @classmethod
    def from_orm_row(cls, j) -> "CaseOrder":  # noqa: ANN001
        return cls(
            id=j.id, judgment_date=j.judgment_date,
            judge_names=_split_judges(j.judge_text), outcome=j.outcome, url=j.url,
            summary=(j.headnote or "")[:300] or None,
        )


class CaseRead(BaseModel):
    """A case (one CNR) with every order the corpus holds for it, oldest first.

    The corpus lists *orders*; a case has many. This is the view that groups
    them: what the case is, who the parties and counsel are, when it was filed,
    and each hearing's order with its outcome.
    """

    cnr_number: str
    court: str
    court_level: CourtLevel
    case_type: str | None
    case_number: str | None
    case_year: int | None
    cause_title: str | None
    petitioner: str | None
    respondent: str | None
    # Union across the case's orders — counsel can change between hearings.
    petitioner_advocates: list[str] = Field(default_factory=list)
    respondent_advocates: list[str] = Field(default_factory=list)
    judge_names: list[str] = Field(default_factory=list)
    filed_on: date | None
    first_order_on: date | None
    latest_order_on: date | None
    # The most recent order's disposal — the case's current position.
    latest_outcome: str | None
    orders: list[CaseOrder]


# ─── AI-generated headnotes (migration 0064) ─────────────────────────
AI_HEADNOTE_LABEL = "AI-generated headnote. Verify against the judgment before relying on it."


class AiProvision(BaseModel):
    """A statutory provision the Court applied, read before the holding is stated."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    act: str = Field(min_length=2, max_length=200)
    provision: str = Field(min_length=1, max_length=120)
    how_applied: str = Field(min_length=10, max_length=700)
    paragraphs: list[str] = Field(default_factory=list, max_length=20)


class AiHeldPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    point: str = Field(min_length=10, max_length=1500)
    paragraphs: list[str] = Field(default_factory=list, max_length=20)


class AiHeadnoteContent(BaseModel):
    """What a headnote writer must produce. Original wording, grounded in the
    judgment's own paragraphs; never the reporter's editorial headnote."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    summary: str = Field(min_length=20, max_length=900)
    issues: list[str] = Field(min_length=1, max_length=8)
    provisions: list[AiProvision] = Field(default_factory=list, max_length=12)
    held: list[AiHeldPoint] = Field(min_length=1, max_length=10)
    result: str = Field(min_length=3, max_length=600)


class AiHeadnoteRead(AiHeadnoteContent):
    model_config = ConfigDict(extra="ignore")
    ai_generated: Literal[True] = True
    label: str = AI_HEADNOTE_LABEL
    model: str | None = None
    generated_at: datetime | None = None
    version: str | None = None

    @classmethod
    def from_judgment(cls, judgment) -> "AiHeadnoteRead | None":  # noqa: ANN001
        data = getattr(judgment, "ai_headnote", None)
        if not data:
            return None
        return cls(
            **data,
            model=judgment.ai_headnote_model,
            generated_at=judgment.ai_headnote_generated_at,
            version=judgment.ai_headnote_version,
        )


class JudgmentRead(_RegistryFields):
    id: uuid.UUID
    case_name: str
    neutral_citation: str | None
    court: str
    court_level: CourtLevel
    bench: str | None
    judges: list[str]
    judgment_date: date | None
    acts: list[str]
    sections: list[str]
    keywords: list[str]
    headnote: str | None
    outcome: str | None
    url: str | None
    # Text extracted from the PDF (migration 0040); null until extracted.
    full_text: str | None = None
    text_extracted_at: datetime | None = None
    # Always flagged as AI-generated (ai_generated=true, label); null until written.
    ai_headnote: AiHeadnoteRead | None = None
    # Other reporters' citations for this judgment (migration 0080), best supported first.
    aliases: list[str] = Field(default_factory=list)
    created_at: datetime

    @classmethod
    def from_orm_row(cls, judgment, aliases: list[str] | None = None) -> "JudgmentRead":  # noqa: ANN001
        read = cls.model_validate(judgment)
        read.ai_headnote = AiHeadnoteRead.from_judgment(judgment)
        read.judge_names = _split_judges(getattr(judgment, "judge_text", None))
        read.aliases = aliases or []
        return read


class JudgmentSummary(_RegistryFields):
    """Search-result shape: the registry line plus a ranked, highlighted snippet."""

    id: uuid.UUID
    case_name: str
    court: str
    court_level: CourtLevel
    judgment_date: date | None
    outcome: str | None
    # Fragment of the text that matched, with <mark>…</mark> around the hits.
    # Only produced by the PostgreSQL full-text path.
    snippet: str | None = None
    # How many orders the corpus holds for this row's case (CNR) — so a result
    # can say "1 of 7 orders" and link to the case view.
    order_count: int | None = None
    # The AI headnote's one-paragraph summary, when the judgment has one
    # (Supreme Court); always shown labelled as AI-generated.
    ai_summary: str | None = None

    @classmethod
    def from_orm_row(cls, judgment, snippet: str | None = None) -> "JudgmentSummary":  # noqa: ANN001
        summary = cls.model_validate(judgment)
        summary.judge_names = _split_judges(getattr(judgment, "judge_text", None))
        summary.snippet = snippet
        headnote = getattr(judgment, "ai_headnote", None)
        summary.ai_summary = headnote.get("summary") if isinstance(headnote, dict) else None
        return summary


class SearchPage(BaseModel):
    """A page of results plus how many matched in total."""

    items: list[JudgmentSummary]
    total: int
    # True when `total` is the planner's estimate for a very large match set
    # ("About 1,40,000 results") rather than an exact count.
    total_is_estimate: bool = False
    # True when `total` is a floor we counted past, not a guess: the UI should
    # say "More than N", not "About N".
    total_is_lower_bound: bool = False
    page: int
    size: int
    # False when the match set was too large to rank interactively and the
    # page is newest-first instead — the UI should say so.
    ranked: bool = True
    # Set when an unranked page was drawn from only the most recent N years.
    recent_years: int | None = None


class FacetBucket(BaseModel):
    value: str
    count: int


class SearchFacets(BaseModel):
    """Counts for the current query, for the filter sidebar."""

    total: int
    total_is_estimate: bool = False
    total_is_lower_bound: bool = False
    # Set when the counts (like the results) cover only the most recent N years.
    recent_years: int | None = None
    # True when the aggregation timed out and buckets are empty — results still work.
    facets_partial: bool = False
    courts: list[FacetBucket] = Field(default_factory=list)
    years: list[FacetBucket] = Field(default_factory=list)
    case_types: list[FacetBucket] = Field(default_factory=list)
    judges: list[FacetBucket] = Field(default_factory=list)
    advocates: list[FacetBucket] = Field(default_factory=list)
    outcomes: list[FacetBucket] = Field(default_factory=list)


class CiteCheckRequest(BaseModel):
    """A draft's text to scan for case citations."""

    text: str = Field(min_length=1, max_length=300_000)


class CiteCheckJudgment(BaseModel):
    """The library record a citation resolved to (or might have)."""

    id: uuid.UUID
    case_name: str
    citation: str | None
    neutral_citation: str | None
    court: str
    judgment_date: date | None


CiteCheckStatus = Literal["verified", "matched_by_name", "possible_matches", "cited_elsewhere", "not_found"]


class CiteCheckFinding(BaseModel):
    citation: str                  # normalised, e.g. "(2019) 5 SCC 123" or "[2019] 4 S.C.R. 532"
    reporter: str                  # "SCC", "AIR", "S.C.R.", "INSC", "Neutral citation", …
    kind: str                      # scr | insc | neutral | reporter
    year: int
    case_name_as_cited: str | None
    occurrences: int
    contexts: list[str]            # up to three passages around the citation
    status: CiteCheckStatus
    judgment: CiteCheckJudgment | None = None
    candidates: list[CiteCheckJudgment] = Field(default_factory=list)
    cited_in_count: int = 0        # judgments in the library whose text cites this string (capped at 50)
    cited_in_examples: list[CiteCheckJudgment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StatuteReference(BaseModel):
    """A section of the IPC / CrPC / Evidence Act (or BNS / BNSS / BSA) cited in the draft."""

    act: str                       # ipc | crpc | evidence | bns | bnss | bsa
    act_label: str
    section: str                   # as cited
    base: str                      # the number the correspondence table keys by
    occurrences: int
    contexts: list[str]
    status: Literal["mapped", "not_carried", "new_law", "unknown"]
    new_act: str | None = None
    new_act_label: str | None = None
    new_sections: list[str] = Field(default_factory=list)
    subject: str | None = None
    old_sections: list[str] = Field(default_factory=list)
    converter_path: str | None = None
    note: str | None = None


class CiteCheckReport(BaseModel):
    source_chars: int
    citations_found: int           # every occurrence
    distinct_citations: int
    truncated: bool                # more distinct citations than were checked
    counts: dict[str, int]         # per status
    findings: list[CiteCheckFinding]
    statutes: list[StatuteReference] = Field(default_factory=list)   # old-law → new-law references
    statute_counts: dict[str, int] = Field(default_factory=dict)
    checked_at: datetime
    note: str = (
        "A first pass, not an opinion: it confirms that a citation exists in or is cited by the library, "
        "not that the case supports the proposition. Read the authority before relying on it."
    )


class CitationCreate(BaseModel):
    to_judgment_id: uuid.UUID | None = None
    external_citation: str | None = Field(default=None, max_length=200)
    relationship_type: CitationRelationship = CitationRelationship.REFERRED


class CitationEdge(BaseModel):
    id: uuid.UUID
    relationship_type: CitationRelationship
    judgment_id: uuid.UUID | None = None  # the other judgment (if in-corpus)
    case_name: str | None = None
    citation: str  # the other case's citation (in-corpus or external)


class CitationGraph(BaseModel):
    cites: list[CitationEdge] = Field(default_factory=list)      # outgoing
    cited_by: list[CitationEdge] = Field(default_factory=list)   # incoming
