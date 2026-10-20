"""Pydantic schemas for the matters (case management) module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator
from pydantic_core import PydanticCustomError

from app.modules.matters.models import (
    AdvocateRole,
    CourtLevel,
    FeeBasis,
    FeeEventKind,
    FeeEventStatus,
    HearingStatus,
    MatterStage,
    MatterStatus,
    MatterType,
    MilestoneStatus,
    MilestoneTrigger,
    PartySide,
    Priority,
    RateBasis,
    RetainerPeriod,
    TaskStatus,
    TeamEndReason,
    TeamRole,
)


class CourtRecord(BaseModel):
    """The Indian court registry fields, shared by create / update / read."""

    cnr_number: str | None = Field(default=None, max_length=16)
    case_type: str | None = Field(default=None, max_length=60)
    case_year: int | None = Field(default=None, ge=1900, le=2200)
    filing_number: str | None = Field(default=None, max_length=60)
    filing_date: date | None = None
    registration_number: str | None = Field(default=None, max_length=60)
    registration_date: date | None = None
    court_level: CourtLevel | None = None
    court_establishment: str | None = Field(default=None, max_length=200)
    state: str | None = Field(default=None, max_length=80)
    district: str | None = Field(default=None, max_length=120)
    coram: str | None = Field(default=None, max_length=300)
    cause_title: str | None = Field(default=None, max_length=400)
    acts: list[str] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)
    next_hearing_date: date | None = None
    last_hearing_date: date | None = None
    hearing_purpose: str | None = Field(default=None, max_length=200)
    disposal_date: date | None = None
    disposal_nature: str | None = Field(default=None, max_length=160)


# Amounts always leave the API as 2-decimal strings ("1500.00"), whatever the DB returned.
Money = Annotated[Decimal, PlainSerializer(lambda v: f"{Decimal(v):.2f}", return_type=str, when_used="json")]


# ─── Matters ────────────────────────────────────────────────────────
class MatterCreate(CourtRecord):
    title: str = Field(min_length=2, max_length=300)
    # Pick a client from the master (preferred) or type a name for a quick intake.
    client_id: uuid.UUID | None = None
    client_name: str | None = Field(default=None, min_length=1, max_length=200)
    # Who is in charge from day one; creates the `lead_counsel` team row.
    lead_counsel_id: uuid.UUID | None = None
    team: list["TeamMemberCreate"] = Field(default_factory=list, max_length=20)
    matter_type: MatterType = MatterType.LITIGATION
    stage: MatterStage = MatterStage.INTAKE
    priority: Priority = Priority.MEDIUM
    practice_area: str | None = Field(default=None, max_length=150)
    court: str | None = Field(default=None, max_length=200)
    case_number: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    opened_on: date | None = None
    limitation_date: date | None = None
    assigned_to: uuid.UUID | None = None
    matter_number: str | None = Field(default=None, max_length=40)


class MatterUpdate(CourtRecord):
    title: str | None = Field(default=None, min_length=2, max_length=300)
    client_id: uuid.UUID | None = None
    client_name: str | None = Field(default=None, min_length=1, max_length=200)
    matter_type: MatterType | None = None
    status: MatterStatus | None = None
    stage: MatterStage | None = None
    priority: Priority | None = None
    practice_area: str | None = Field(default=None, max_length=150)
    court: str | None = Field(default=None, max_length=200)
    case_number: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    opened_on: date | None = None
    limitation_date: date | None = None
    assigned_to: uuid.UUID | None = None


class MatterRead(CourtRecord):
    model_config = ConfigDict(from_attributes=True)
    ecourts_synced_at: datetime | None = None
    ecourts_source: str | None = None
    id: uuid.UUID
    matter_number: str
    title: str
    client_id: uuid.UUID | None = None
    client_name: str
    lead_counsel_id: uuid.UUID | None = None
    lead_counsel_name: str | None = None
    matter_type: MatterType
    status: MatterStatus
    stage: MatterStage
    priority: Priority
    practice_area: str | None
    court: str | None
    case_number: str | None
    description: str | None
    opened_on: date | None
    limitation_date: date | None
    assigned_to: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime


class MatterDetail(MatterRead):
    parties: list["PartyRead"] = Field(default_factory=list)
    advocates: list["AdvocateRead"] = Field(default_factory=list)
    hearings: list["HearingRead"] = Field(default_factory=list)
    tasks: list["TaskRead"] = Field(default_factory=list)
    notes: list["NoteRead"] = Field(default_factory=list)
    team: list["TeamMemberRead"] = Field(default_factory=list)
    fee_arrangements: list["FeeArrangementRead"] = Field(default_factory=list)
    fee_events: list["FeeEventRead"] = Field(default_factory=list)
    authorities: list["AuthorityRead"] = Field(default_factory=list)


class AuthorityCreate(BaseModel):
    kind: str = Field(pattern="^(judgment|statute)$")
    judgment_id: uuid.UUID | None = None
    act_id: str | None = Field(default=None, max_length=80)
    reference: str = Field(min_length=1, max_length=300)
    paragraph_no: int | None = Field(default=None, ge=1)
    quotation: str | None = Field(default=None, max_length=50000)
    proposition: str | None = Field(default=None, max_length=10000)
    stance: str = Field(default="pending_review", pattern="^(favourable|adverse|distinguish|background|pending_review)$")
    source_url: str | None = Field(default=None, max_length=2000)


class AuthorityRead(AuthorityCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    matter_id: uuid.UUID
    created_by: uuid.UUID
    created_at: datetime


# ─── Team ───────────────────────────────────────────────────────────
class TeamMemberCreate(BaseModel):
    user_id: uuid.UUID
    role: TeamRole = TeamRole.ASSOCIATE
    from_date: date | None = None          # defaults to today
    rate_basis: RateBasis | None = None
    rate_amount: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class TeamMemberUpdate(BaseModel):
    role: TeamRole | None = None
    from_date: date | None = None
    rate_basis: RateBasis | None = None
    rate_amount: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class TeamHandover(BaseModel):
    """End one person's stint and (optionally) start the successor's."""

    effective_from: date | None = None     # defaults to today
    reason: TeamEndReason = TeamEndReason.REASSIGNED
    successor_user_id: uuid.UUID | None = None
    successor_role: TeamRole | None = None  # defaults to the outgoing person's role
    notes: str | None = Field(default=None, max_length=2000)


class TeamTransfer(BaseModel):
    """Move every active stint of one person to another — the 'X left the
    firm' case. Limited to `matter_ids` when given, else all open matters."""

    from_user_id: uuid.UUID
    to_user_id: uuid.UUID
    effective_from: date | None = None
    reason: TeamEndReason = TeamEndReason.LEFT_FIRM
    matter_ids: list[uuid.UUID] | None = None
    notes: str | None = Field(default=None, max_length=2000)


class TeamTransferResult(BaseModel):
    moved: int
    matter_numbers: list[str]


class TeamMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    matter_id: uuid.UUID
    user_id: uuid.UUID
    user_name: str | None = None
    user_email: str | None = None
    role: TeamRole
    from_date: date
    to_date: date | None
    end_reason: TeamEndReason | None
    successor_user_id: uuid.UUID | None
    successor_name: str | None = None
    rate_basis: RateBasis | None
    rate_amount: Money | None
    # The person's rate card entry for the same basis (or hourly), for display.
    card_rate_basis: RateBasis | None = None
    card_rate_amount: Money | None = None
    notes: str | None
    is_active: bool = True


class PersonRead(BaseModel):
    """A colleague who can be put on a team (active users of the tenant)."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    email: str | None


# ─── Fee arrangements ───────────────────────────────────────────────
class MilestoneCreate(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    trigger: MilestoneTrigger
    amount: Decimal | None = Field(default=None, ge=0)
    percent: Decimal | None = Field(default=None, ge=0, le=100)
    due_on: date | None = None
    due_days: int = Field(default=7, ge=0, le=365)

    @model_validator(mode="after")
    def _amount_or_percent(self) -> "MilestoneCreate":
        if (self.amount is None) == (self.percent is None):
            raise PydanticCustomError("fee_terms", "Give either an amount or a percentage of the fixed fee.")
        if self.trigger == MilestoneTrigger.ON_DATE and self.due_on is None:
            raise PydanticCustomError("fee_terms", "A dated milestone needs its date.")
        return self


class MilestoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    arrangement_id: uuid.UUID
    sequence: int
    label: str
    trigger: MilestoneTrigger
    amount: Money | None
    percent: Money | None
    due_on: date | None
    due_days: int
    status: MilestoneStatus
    triggered_at: datetime | None
    # Resolved: amount, or percent × fixed fee.
    computed_amount: Money | None = None


class FeeArrangementCreate(BaseModel):
    basis: FeeBasis = FeeBasis.FIXED
    currency: str = Field(default="INR", min_length=3, max_length=3)
    fixed_fee: Decimal | None = Field(default=None, ge=0)
    per_hearing_fee: Decimal | None = Field(default=None, ge=0)
    non_effective_hearing_fee: Decimal | None = Field(default=None, ge=0)
    hourly_rate: Decimal | None = Field(default=None, ge=0)
    retainer_amount: Decimal | None = Field(default=None, ge=0)
    retainer_period: RetainerPeriod | None = None
    retainer_includes: str | None = Field(default=None, max_length=300)
    fee_cap: Decimal | None = Field(default=None, ge=0)
    expenses_billable: bool = True
    gst_applicable: bool = True
    agreed_on: date | None = None
    effective_from: date | None = None      # defaults to today
    terms: str | None = Field(default=None, max_length=8000)
    milestones: list[MilestoneCreate] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def _consistent(self) -> "FeeArrangementCreate":
        if self.basis == FeeBasis.FIXED and self.fixed_fee is None:
            raise PydanticCustomError("fee_terms", "A fixed-fee arrangement needs the fixed fee.")
        if self.basis == FeeBasis.PER_HEARING and self.per_hearing_fee is None:
            raise PydanticCustomError("fee_terms", "A per-hearing arrangement needs the per-hearing fee.")
        if self.basis == FeeBasis.HOURLY and self.hourly_rate is None:
            raise PydanticCustomError("fee_terms", "An hourly arrangement needs the hourly rate.")
        if self.basis == FeeBasis.RETAINER and (self.retainer_amount is None or self.retainer_period is None):
            raise PydanticCustomError("fee_terms", "A retainer needs the amount and the period.")
        if self.basis == FeeBasis.MILESTONE and not self.milestones:
            raise PydanticCustomError("fee_terms", "A milestone arrangement needs at least one milestone.")
        if any(m.percent is not None for m in self.milestones) and self.fixed_fee is None:
            raise PydanticCustomError("fee_terms", "Percentage milestones need a fixed fee to be a percentage of.")
        if self.basis == FeeBasis.PRO_BONO:
            self.fixed_fee = self.per_hearing_fee = self.hourly_rate = self.retainer_amount = None
            self.milestones = []
        return self


class FeeArrangementUpdate(BaseModel):
    """Light edits that do not change the bargain (terms, cap, flags, end date)."""

    expenses_billable: bool | None = None
    gst_applicable: bool | None = None
    agreed_on: date | None = None
    effective_to: date | None = None
    terms: str | None = Field(default=None, max_length=8000)
    fee_cap: Decimal | None = Field(default=None, ge=0)
    retainer_includes: str | None = Field(default=None, max_length=300)


class FeeArrangementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    matter_id: uuid.UUID
    basis: FeeBasis
    currency: str
    fixed_fee: Money | None
    per_hearing_fee: Money | None
    non_effective_hearing_fee: Money | None
    hourly_rate: Money | None
    retainer_amount: Money | None
    retainer_period: RetainerPeriod | None
    retainer_includes: str | None
    fee_cap: Money | None
    expenses_billable: bool
    gst_applicable: bool
    agreed_on: date | None
    effective_from: date
    effective_to: date | None
    terms: str | None
    created_by: uuid.UUID
    created_at: datetime
    milestones: list[MilestoneRead] = Field(default_factory=list)
    is_active: bool = True


class FeeEventCreate(BaseModel):
    """A manual billable event (e.g. an opinion, a conference, a drafting fee)."""

    description: str = Field(min_length=1, max_length=300)
    amount: Decimal = Field(ge=0)
    occurred_on: date | None = None
    due_days: int = Field(default=7, ge=0, le=365)


class FeeEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    matter_id: uuid.UUID
    arrangement_id: uuid.UUID | None
    milestone_id: uuid.UUID | None
    hearing_id: uuid.UUID | None
    kind: FeeEventKind
    description: str
    occurred_on: date
    due_on: date | None
    amount: Money
    currency: str
    status: FeeEventStatus
    invoice_id: uuid.UUID | None
    created_at: datetime


class FeeSummary(BaseModel):
    unbilled_total: Money
    unbilled_count: int
    invoiced_total: Money
    waived_total: Money
    currency: str = "INR"


class TimelineEntry(BaseModel):
    kind: str  # matter | hearing | task | task_done | note
    at: datetime
    title: str
    detail: str | None = None
    status: str | None = None


# ─── Parties ────────────────────────────────────────────────────────
class PartyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=80)
    contact: str | None = Field(default=None, max_length=200)
    side: PartySide = PartySide.OTHER
    position: int | None = Field(default=None, ge=1)
    lawful_basis: str = Field(default="legitimate_use", max_length=20)
    basis_note: str | None = Field(default=None, max_length=300)


class PartyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    role: str
    contact: str | None
    side: PartySide
    position: int | None
    lawful_basis: str = "legitimate_use"
    basis_note: str | None = None


# ─── Advocates on record ────────────────────────────────────────────
class AdvocateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    side: PartySide
    role: AdvocateRole = AdvocateRole.ARGUING_COUNSEL
    bar_enrolment_number: str | None = Field(default=None, max_length=60)
    firm: str | None = Field(default=None, max_length=200)
    party_represented: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=20)
    user_id: uuid.UUID | None = None
    is_lead: bool = False
    notes: str | None = Field(default=None, max_length=2000)


class AdvocateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    side: PartySide | None = None
    role: AdvocateRole | None = None
    bar_enrolment_number: str | None = Field(default=None, max_length=60)
    firm: str | None = Field(default=None, max_length=200)
    party_represented: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=20)
    user_id: uuid.UUID | None = None
    is_lead: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class AdvocateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    side: PartySide
    role: AdvocateRole
    bar_enrolment_number: str | None
    firm: str | None
    party_represented: str | None
    email: str | None
    phone: str | None
    user_id: uuid.UUID | None
    is_lead: bool
    notes: str | None


# ─── eCourts lookup / import ────────────────────────────────────────
class ECourtsLookupRequest(BaseModel):
    """Either a CNR, or case type + number + year (optionally narrowed)."""

    cnr_number: str | None = Field(default=None, max_length=24)
    case_type: str | None = Field(default=None, max_length=60)
    case_number: str | None = Field(default=None, max_length=40)
    case_year: int | None = Field(default=None, ge=1900, le=2200)
    state: str | None = Field(default=None, max_length=80)
    district: str | None = Field(default=None, max_length=120)
    court_establishment: str | None = Field(default=None, max_length=200)


class ECourtsPartyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    role: str
    position: int | None = None


class ECourtsAdvocateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    appears_for: str
    bar_enrolment_number: str | None = None


class ECourtsCaseRead(CourtRecord):
    """A fetched case, before it is saved to a matter."""

    model_config = ConfigDict(from_attributes=True)
    case_number: str | None = None
    status: str | None = None
    stage: str | None = None
    parties: list[ECourtsPartyRead] = Field(default_factory=list)
    advocates: list[ECourtsAdvocateRead] = Field(default_factory=list)
    source: str = "unknown"


class ECourtsImportRequest(ECourtsLookupRequest):
    """Fetch and create a matter in one step."""

    client_id: uuid.UUID | None = None
    client_name: str | None = Field(default=None, min_length=1, max_length=200)
    lead_counsel_id: uuid.UUID | None = None
    # Which side of the cause title we appear for, so advocates and parties are
    # filed as ours vs the opponent's rather than an undifferentiated list.
    our_side_role: str = Field(
        default="petitioner", max_length=80,
        description="The cause-title role our client holds (petitioner/respondent/…).",
    )
    matter_type: MatterType = MatterType.LITIGATION
    assigned_to: uuid.UUID | None = None


# ─── Hearings ───────────────────────────────────────────────────────
class HearingCreate(BaseModel):
    scheduled_on: datetime
    court: str | None = Field(default=None, max_length=200)
    court_room: str | None = Field(default=None, max_length=40)
    item_number: str | None = Field(default=None, max_length=20)
    judge: str | None = Field(default=None, max_length=200)
    purpose: str | None = Field(default=None, max_length=300)


class HearingUpdate(BaseModel):
    scheduled_on: datetime | None = None
    court: str | None = Field(default=None, max_length=200)
    court_room: str | None = Field(default=None, max_length=40)
    item_number: str | None = Field(default=None, max_length=20)
    purpose: str | None = Field(default=None, max_length=300)
    status: HearingStatus | None = None
    notes: str | None = Field(default=None, max_length=5000)
    outcome: str | None = Field(default=None, max_length=5000)
    next_date: datetime | None = None


class HearingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    matter_id: uuid.UUID
    scheduled_on: datetime
    court: str | None
    court_room: str | None = None
    item_number: str | None = None
    judge: str | None
    purpose: str | None
    status: HearingStatus
    notes: str | None
    outcome: str | None
    next_date: datetime | None


# ─── Tasks ──────────────────────────────────────────────────────────
class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    due_on: date | None = None
    assigned_to: uuid.UUID | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    matter_id: uuid.UUID
    title: str
    due_on: date | None
    status: TaskStatus
    assigned_to: uuid.UUID | None
    completed_at: datetime | None


# ─── Notes ──────────────────────────────────────────────────────────
class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    matter_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime
