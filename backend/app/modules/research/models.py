"""Legal research domain models (Phase 4) — global case-law corpus."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import AuditedBase


class CourtLevel(StrEnum):
    SUPREME_COURT = "supreme_court"
    HIGH_COURT = "high_court"
    TRIBUNAL = "tribunal"
    DISTRICT = "district"
    OTHER = "other"


class CitationRelationship(StrEnum):
    FOLLOWED = "followed"
    OVERRULED = "overruled"
    DISTINGUISHED = "distinguished"
    REFERRED = "referred"
    RELIED_ON = "relied_on"
    DISSENTED = "dissented"


class Judgment(AuditedBase):
    """A judgment / reported case in the shared research library."""

    __tablename__ = "judgments"
    __table_args__ = (
        # Reported judgments (SCR) have a unique citation; High Court order
        # records have none at all, so uniqueness is a PARTIAL index rather than
        # a table constraint — see migration 0034.
        Index(
            "judgment_citation",
            "citation",
            unique=True,
            postgresql_where=text("citation IS NOT NULL"),
            sqlite_where=text("citation IS NOT NULL"),
        ),
    )

    case_name: Mapped[str] = mapped_column(String(500), nullable=False)
    citation: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    neutral_citation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # eCourts Case Number Record — the handle High Court records are keyed by.
    cnr_number: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    # ── Structured registry fields (migration 0036) ─────────────────
    # Parsed out of the registry title ("CRM-M/33310/2019 of X Vs Y") so the
    # corpus can be browsed by case type and filing year, not just searched.
    case_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    case_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    case_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # The cause title alone, with the number prefix stripped — what a reader
    # actually wants to see as the heading.
    cause_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Judges normalised to bare names ("Avneesh Jhingan", not
    # "MR. JUSTICE AVNEESH JHINGAN"), " | "-joined. `judges` keeps the raw
    # provider strings for provenance; this column is what filters and facets
    # use, so one judge is one value however each registry spelled it.
    judge_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NOTE: `search_vector` (tsvector, GENERATED) is deliberately not mapped —
    # SQLite (the test DB) cannot create it. It is referenced by name in the
    # PostgreSQL search path only; see ResearchRepository.search.
    # Deterministic provider row id, so a re-run cannot duplicate rows that have
    # no citation to dedupe on. "<court_code>:<cnr>:<decision_date>".
    source_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    court: Mapped[str] = mapped_column(String(200), nullable=False)
    court_level: Mapped[CourtLevel] = mapped_column(
        String(20), default=CourtLevel.OTHER, nullable=False, index=True
    )
    bench: Mapped[str | None] = mapped_column(String(120), nullable=True)
    judges: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    judgment_date: Mapped[date | None] = mapped_column(nullable=True, index=True)
    # Registry filing date (`date_of_registration`); with judgment_date it gives
    # how long a case has been running. Migration 0039.
    filed_on: Mapped[date | None] = mapped_column(nullable=True)
    # The two sides, split from the cause title ("A Vs B"). Advocates are parsed
    # from the order's opening ("…Appellant Through: Mr. X, Advocate versus …")
    # where a registry prints it (Delhi does; P&H and Allahabad mostly do not).
    petitioner: Mapped[str | None] = mapped_column(String(300), nullable=True)
    respondent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    petitioner_advocates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    respondent_advocates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # All advocates on the record, " | "-joined — the filter/facet column, like judge_text.
    advocate_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    acts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sections: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    headnote: Mapped[str | None] = mapped_column(Text, nullable=True)
    # AI-generated headnote (migration 0064): original summary writing, never the
    # reporter's editorial headnote. Always presented with an "AI-generated" flag.
    # Shape: app.modules.research.schemas.AiHeadnoteContent.
    ai_headnote: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_headnote_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ai_headnote_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ai_headnote_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(300), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Text extracted from the order/judgment PDF (migration 0040). Searched
    # through its own GIN expression index, not the generated search_vector.
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_extracted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    added_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    citations: Mapped[list["CaseCitation"]] = relationship(
        back_populates="from_judgment",
        foreign_keys="CaseCitation.from_judgment_id",
        cascade="all, delete-orphan",
    )


class CaseCitation(AuditedBase):
    """A directed citation edge between two judgments (or to an external cite)."""

    __tablename__ = "case_citations"

    from_judgment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("judgments.id", ondelete="CASCADE"), index=True
    )
    to_judgment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("judgments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    external_citation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    relationship_type: Mapped[CitationRelationship] = mapped_column(
        String(20), default=CitationRelationship.REFERRED, nullable=False
    )
    added_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    from_judgment: Mapped[Judgment] = relationship(
        back_populates="citations", foreign_keys=[from_judgment_id]
    )
