"""Matter / case management domain models (Phase 3) — tenant-scoped with RLS."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.db.base_class import TenantScopedBase


class MatterType(StrEnum):
    LITIGATION = "litigation"
    ADVISORY = "advisory"
    ARBITRATION = "arbitration"
    CORPORATE = "corporate"
    OTHER = "other"


class MatterStatus(StrEnum):
    OPEN = "open"
    ON_HOLD = "on_hold"
    CLOSED = "closed"


class MatterStage(StrEnum):
    INTAKE = "intake"
    FILING = "filing"
    PLEADINGS = "pleadings"
    EVIDENCE = "evidence"
    ARGUMENTS = "arguments"
    JUDGMENT = "judgment"
    CLOSED = "closed"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CourtLevel(StrEnum):
    """Where the matter sits in the Indian court hierarchy."""

    SUPREME_COURT = "supreme_court"
    HIGH_COURT = "high_court"
    DISTRICT = "district"          # District & Sessions, incl. civil/criminal courts
    TRIBUNAL = "tribunal"          # NCLT, NCLAT, ITAT, CAT, NGT, DRT …
    CONSUMER = "consumer"          # NCDRC / State & District Commissions
    REVENUE = "revenue"            # revenue courts, land tribunals
    OTHER = "other"


class PartySide(StrEnum):
    """Which side of the cause title a party or advocate is on.

    "Ours" is the side this firm appears for; it is deliberately not the same as
    petitioner/respondent, because we may act for either.
    """

    OURS = "ours"
    OPPOSING = "opposing"
    OTHER = "other"                # intervenors, proforma parties, amicus


class AdvocateRole(StrEnum):
    """Role on the vakalatnama / in court."""

    SENIOR_COUNSEL = "senior_counsel"
    ARGUING_COUNSEL = "arguing_counsel"
    ADVOCATE_ON_RECORD = "advocate_on_record"   # AOR — Supreme Court
    JUNIOR = "junior"
    INSTRUCTING = "instructing"                 # instructing/briefing advocate
    PARTY_IN_PERSON = "party_in_person"


class HearingStatus(StrEnum):
    SCHEDULED = "scheduled"
    HELD = "held"
    ADJOURNED = "adjourned"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    OPEN = "open"
    DONE = "done"


class TeamRole(StrEnum):
    """A firm member's role on a matter. `lead_counsel` is the one in charge —
    the "main counsel" — and a matter has at most one active lead at a time."""

    LEAD_COUNSEL = "lead_counsel"
    SUPERVISING_PARTNER = "supervising_partner"
    SENIOR_COUNSEL = "senior_counsel"
    ARGUING_COUNSEL = "arguing_counsel"
    ADVOCATE_ON_RECORD = "advocate_on_record"
    ASSOCIATE = "associate"
    JUNIOR = "junior"
    BRIEFING_COUNSEL = "briefing_counsel"
    PARALEGAL = "paralegal"
    CLERK = "clerk"
    OTHER = "other"


class TeamEndReason(StrEnum):
    """Why a membership ended — kept so a two-year-old matter still explains
    who handled it and why it moved."""

    REASSIGNED = "reassigned"
    LEFT_FIRM = "left_firm"
    WORKLOAD = "workload"
    CLIENT_REQUEST = "client_request"
    CONFLICT = "conflict"
    MATTER_CLOSED = "matter_closed"
    OTHER = "other"


class RateBasis(StrEnum):
    """How a counsel's time or work is priced (rate card / team override)."""

    HOURLY = "hourly"
    PER_HEARING = "per_hearing"
    PER_DAY = "per_day"            # outstation / full-day engagement
    PER_MATTER = "per_matter"      # fixed per case
    PER_DRAFTING = "per_drafting"  # per document / opinion / conference
    RETAINER_MONTHLY = "retainer_monthly"


class FeeBasis(StrEnum):
    """The primary way the client is charged for a matter. Components can be
    combined (e.g. a fixed fee plus a per-hearing fee), so the basis is the
    headline while the amount columns say what actually applies.

    Contingency / success fees are deliberately absent: Bar Council of India
    Rules, Part VI Ch. II s. II Rule 20 bars an advocate from stipulating a
    fee contingent on the result of litigation.
    """

    FIXED = "fixed"                # lump sum for the matter, paid via milestones
    PER_HEARING = "per_hearing"    # per appearance (effective / non-effective)
    HOURLY = "hourly"              # time-based from time entries at team rates
    RETAINER = "retainer"          # periodic retainer, optionally with inclusions
    MILESTONE = "milestone"        # stage-wise payments (advance, filing, …)
    HYBRID = "hybrid"              # e.g. fixed + per hearing, retainer + hourly
    PRO_BONO = "pro_bono"


class RetainerPeriod(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    HALF_YEARLY = "half_yearly"
    YEARLY = "yearly"


class MilestoneTrigger(StrEnum):
    """What makes a milestone fall due. Stage/hearing/closure triggers fire
    automatically from the matter; `on_date` fires when the date arrives;
    `manual` only when staff mark it."""

    ADVANCE = "advance"                    # on engagement (fires when the arrangement is saved)
    ON_FILING = "on_filing"                # stage → filing
    ON_FIRST_HEARING = "on_first_hearing"  # first hearing marked held
    ON_PLEADINGS = "on_pleadings"          # stage → pleadings
    ON_EVIDENCE = "on_evidence"            # stage → evidence
    ON_ARGUMENTS = "on_arguments"          # stage → arguments
    ON_JUDGMENT = "on_judgment"            # stage → judgment / final order
    ON_CLOSURE = "on_closure"              # matter closed: settlement, withdrawal, disposal
    ON_DATE = "on_date"
    MANUAL = "manual"


class MilestoneStatus(StrEnum):
    PENDING = "pending"
    DUE = "due"          # triggered — a fee event exists for it
    WAIVED = "waived"


class FeeEventKind(StrEnum):
    MILESTONE = "milestone"
    HEARING = "hearing"                    # effective hearing
    HEARING_NON_EFFECTIVE = "hearing_non_effective"  # adjournment / mention
    RETAINER = "retainer"
    MANUAL = "manual"


class FeeEventStatus(StrEnum):
    UNBILLED = "unbilled"
    INVOICED = "invoiced"
    WAIVED = "waived"


class MatterFieldType(StrEnum):
    TEXT = "text"
    MULTILINE = "multiline"
    RICH_TEXT = "rich_text"
    NUMBER = "number"
    AMOUNT = "amount"
    DROPDOWN = "dropdown"
    MULTI_SELECT = "multi_select"
    DATE = "date"
    BOOLEAN = "boolean"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"


class MatterCustomSection(TenantScopedBase):
    """A tenant-owned heading used to organise additional matter data."""

    __tablename__ = "matter_custom_sections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="matter_custom_section_name_per_tenant"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(400), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class MatterCustomField(TenantScopedBase):
    """Tenant-configured matter field definition."""

    __tablename__ = "matter_custom_fields"
    __table_args__ = (
        UniqueConstraint("tenant_id", "field_key", name="matter_custom_field_key_per_tenant"),
    )

    section_key: Mapped[str] = mapped_column(String(40), nullable=False, default="additional")
    custom_section_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("matter_custom_sections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    field_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    help_text: Mapped[str | None] = mapped_column(String(400), nullable=True)
    field_type: Mapped[MatterFieldType] = mapped_column(String(24), nullable=False)
    options: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_masked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_reportable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class MatterCustomValue(TenantScopedBase):
    """A value for a tenant-defined field; sensitive values use the encrypted column."""

    __tablename__ = "matter_custom_values"
    __table_args__ = (
        UniqueConstraint("matter_id", "field_id", name="matter_custom_value_per_field"),
    )

    matter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("matters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("matter_custom_fields.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plain_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_value: Mapped[str | None] = mapped_column(EncryptedString(16384), nullable=True)
    updated_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class Matter(TenantScopedBase):
    __tablename__ = "matters"
    __table_args__ = (
        UniqueConstraint("tenant_id", "matter_number", name="matter_number_per_tenant"),
    )

    matter_number: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # The client master record (tax defaults, consent, KYC). `client_name` is
    # kept as the display/denormalised copy so older matters and free-text
    # intakes still work.
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    client_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Denormalised from the active `lead_counsel` team membership.
    lead_counsel_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    matter_type: Mapped[MatterType] = mapped_column(
        String(20), default=MatterType.LITIGATION, nullable=False, index=True
    )
    status: Mapped[MatterStatus] = mapped_column(
        String(20), default=MatterStatus.OPEN, nullable=False, index=True
    )
    stage: Mapped[MatterStage] = mapped_column(
        String(20), default=MatterStage.INTAKE, nullable=False
    )
    priority: Mapped[Priority] = mapped_column(
        String(10), default=Priority.MEDIUM, nullable=False
    )
    practice_area: Mapped[str | None] = mapped_column(String(150), nullable=True)
    court: Mapped[str | None] = mapped_column(String(200), nullable=True)
    case_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Indian court record ─────────────────────────────────────────
    # The CNR (Case Number Record) is the 16-character identifier eCourts gives
    # every case in the district judiciary and most High Courts. It is the one
    # handle that stays constant as a case is re-numbered on registration or
    # transferred, so it is the key we sync on.
    cnr_number: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    case_type: Mapped[str | None] = mapped_column(String(60), nullable=True)   # "W.P.(C)", "CRL.A."
    case_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    filing_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # A case is filed first and *registered* later, often with a new number.
    registration_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    registration_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    court_level: Mapped[CourtLevel | None] = mapped_column(String(20), nullable=True, index=True)
    court_establishment: Mapped[str | None] = mapped_column(String(200), nullable=True)
    state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    coram: Mapped[str | None] = mapped_column(String(300), nullable=True)      # judge(s) hearing it

    # Cause title as the court prints it, e.g. "Ramesh Kumar vs State of Haryana".
    cause_title: Mapped[str | None] = mapped_column(String(400), nullable=True)
    acts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sections: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    next_hearing_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    last_hearing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    hearing_purpose: Mapped[str | None] = mapped_column(String(200), nullable=True)
    disposal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    disposal_nature: Mapped[str | None] = mapped_column(String(160), nullable=True)

    # Provenance of the court data above.
    ecourts_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ecourts_source: Mapped[str | None] = mapped_column(String(60), nullable=True)
    opened_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Limitation / statute-of-limitations deadline for filing action.
    limitation_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    parties: Mapped[list["MatterParty"]] = relationship(
        back_populates="matter", cascade="all, delete-orphan"
    )
    advocates: Mapped[list["MatterAdvocate"]] = relationship(
        back_populates="matter", cascade="all, delete-orphan"
    )
    hearings: Mapped[list["Hearing"]] = relationship(
        back_populates="matter", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["MatterTask"]] = relationship(
        back_populates="matter", cascade="all, delete-orphan"
    )
    notes: Mapped[list["MatterNote"]] = relationship(
        back_populates="matter", cascade="all, delete-orphan"
    )
    team: Mapped[list["MatterTeamMember"]] = relationship(
        back_populates="matter", cascade="all, delete-orphan", order_by="MatterTeamMember.from_date"
    )
    fee_arrangements: Mapped[list["MatterFeeArrangement"]] = relationship(
        back_populates="matter", cascade="all, delete-orphan", order_by="MatterFeeArrangement.effective_from"
    )
    fee_events: Mapped[list["MatterFeeEvent"]] = relationship(
        back_populates="matter", cascade="all, delete-orphan", order_by="MatterFeeEvent.occurred_on"
    )
    authorities: Mapped[list["MatterAuthority"]] = relationship(
        back_populates="matter", cascade="all, delete-orphan", order_by="MatterAuthority.created_at"
    )


class MatterParty(TenantScopedBase):
    __tablename__ = "matter_parties"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(80), nullable=False)  # petitioner, respondent…
    contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Whether this party is on the side we appear for. Distinct from `role`,
    # since we may act for the petitioner in one matter and the respondent in
    # the next — the cause-title position does not tell you who the client is.
    side: Mapped[PartySide] = mapped_column(
        String(10), default=PartySide.OTHER, nullable=False
    )
    # Order as printed in the cause title (Respondent No. 2, etc.).
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # DPDP s.4/s.7: the basis on which a non-client's details are held. Parties
    # to litigation are recorded under the legitimate-use limb by default.
    lawful_basis: Mapped[str] = mapped_column(String(20), nullable=False, default="legitimate_use")
    basis_note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    matter: Mapped[Matter] = relationship(back_populates="parties")


class MatterAdvocate(TenantScopedBase):
    """Counsel appearing in a matter — on our side or against us.

    Kept separate from `MatterParty` because advocates and parties are different
    things: several advocates may appear for one party, and the same advocate may
    appear repeatedly across matters, which is what makes opponent-tracking
    useful.
    """

    __tablename__ = "matter_advocates"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    side: Mapped[PartySide] = mapped_column(String(10), nullable=False, index=True)
    role: Mapped[AdvocateRole] = mapped_column(
        String(24), default=AdvocateRole.ARGUING_COUNSEL, nullable=False
    )
    # Bar Council enrolment number, e.g. "D/1234/2015".
    bar_enrolment_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    firm: Mapped[str | None] = mapped_column(String(200), nullable=True)
    party_represented: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Set when the advocate is a user of this tenant, so "who is on this?" works.
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    is_lead: Mapped[bool] = mapped_column(default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    matter: Mapped[Matter] = relationship(back_populates="advocates")


class Hearing(TenantScopedBase):
    __tablename__ = "hearings"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True
    )
    # timestamptz, matching the database (see calendar.models for the failure
    # a naive mapping causes when the agenda binds an offset-aware range).
    scheduled_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    court: Mapped[str | None] = mapped_column(String(200), nullable=True)
    judge: Mapped[str | None] = mapped_column(String(200), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[HearingStatus] = mapped_column(
        String(20), default=HearingStatus.SCHEDULED, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    matter: Mapped[Matter] = relationship(back_populates="hearings")


class MatterTask(TenantScopedBase):
    __tablename__ = "matter_tasks"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[TaskStatus] = mapped_column(
        String(20), default=TaskStatus.OPEN, nullable=False, index=True
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    matter: Mapped[Matter] = relationship(back_populates="tasks")


class MatterNote(TenantScopedBase):
    __tablename__ = "matter_notes"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    matter: Mapped[Matter] = relationship(back_populates="notes")


class MatterAuthority(TenantScopedBase):
    """A source-linked legal authority pinned to a proposition in the matter."""
    __tablename__ = "matter_authorities"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # judgment | statute
    judgment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    act_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reference: Mapped[str] = mapped_column(String(300), nullable=False)
    paragraph_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quotation: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposition: Mapped[str | None] = mapped_column(Text, nullable=True)
    stance: Mapped[str] = mapped_column(String(20), nullable=False, default="pending_review")
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    matter: Mapped[Matter] = relationship(back_populates="authorities")


# ─── Team, fee arrangement, fee events ──────────────────────────────
class MatterTeamMember(TenantScopedBase):
    """A firm user's stint on a matter, with dates so hand-overs keep history.

    An active membership has `to_date IS NULL`. Moving a matter from X to Y ends
    X's row (with a reason and `successor_user_id`) and opens Y's — nothing is
    overwritten, so two years in you can still see who ran it when.
    """

    __tablename__ = "matter_team"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    role: Mapped[TeamRole] = mapped_column(String(24), nullable=False, default=TeamRole.ASSOCIATE)
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_reason: Mapped[TeamEndReason | None] = mapped_column(String(20), nullable=True)
    successor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    # Per-matter override of the person's rate card (blank = use the card).
    rate_basis: Mapped[RateBasis | None] = mapped_column(String(20), nullable=True)
    rate_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    matter: Mapped[Matter] = relationship(back_populates="team")


class MatterFeeArrangement(TenantScopedBase):
    """How the client pays for this matter. Dated, so a renegotiation adds a
    new arrangement and closes the old one rather than rewriting history.

    Components (all optional, combined as agreed):
    - `fixed_fee`         lump sum for the whole matter, released via milestones
    - `per_hearing_fee`   per effective hearing; `non_effective_hearing_fee`
                          for adjournments / mentions, if charged
    - `hourly_rate`       matter-level default for time entries (team rate
                          cards / overrides take precedence per person)
    - `retainer_amount`   per `retainer_period`, with what it includes
    - `fee_cap`           ceiling on professional fees, if any
    Out-of-pocket expenses (court fees, stamp duty, travel, typing/copying)
    are billed at actuals when `expenses_billable`.
    """

    __tablename__ = "matter_fee_arrangements"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True
    )
    basis: Mapped[FeeBasis] = mapped_column(String(16), nullable=False, default=FeeBasis.FIXED)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    fixed_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    per_hearing_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    non_effective_hearing_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    retainer_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    retainer_period: Mapped[RetainerPeriod | None] = mapped_column(String(12), nullable=True)
    retainer_includes: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fee_cap: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    expenses_billable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    gst_applicable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    agreed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    matter: Mapped[Matter] = relationship(back_populates="fee_arrangements")
    milestones: Mapped[list["MatterFeeMilestone"]] = relationship(
        back_populates="arrangement", cascade="all, delete-orphan", order_by="MatterFeeMilestone.sequence"
    )


class MatterFeeMilestone(TenantScopedBase):
    """A payment point in an arrangement: 'advance ₹50,000', '30% on filing',
    'balance on judgment'. When its trigger fires a fee event is raised — the
    thing invoices will later be generated from."""

    __tablename__ = "matter_fee_milestones"

    arrangement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matter_fee_arrangements.id", ondelete="CASCADE"), index=True
    )
    matter_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    trigger: Mapped[MilestoneTrigger] = mapped_column(String(20), nullable=False)
    # Either an absolute amount or a percentage of `fixed_fee`.
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)      # for `on_date`
    due_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)  # payment terms after trigger
    status: Mapped[MilestoneStatus] = mapped_column(String(10), nullable=False, default=MilestoneStatus.PENDING)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    arrangement: Mapped[MatterFeeArrangement] = relationship(back_populates="milestones")


class MatterFeeEvent(TenantScopedBase):
    """Something billable that happened: a milestone fell due, a hearing was
    held, a retainer period started. Sits unbilled until an invoice picks it
    up (that step is the next deliverable) or staff waive it."""

    __tablename__ = "matter_fee_events"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True
    )
    arrangement_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    hearing_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    kind: Mapped[FeeEventKind] = mapped_column(String(24), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    status: Mapped[FeeEventStatus] = mapped_column(String(10), nullable=False, default=FeeEventStatus.UNBILLED, index=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    matter: Mapped[Matter] = relationship(back_populates="fee_events")
