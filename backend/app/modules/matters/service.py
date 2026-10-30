"""Matters (case management) service — business logic."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecourts import (
    ECourtsCase,
    ECourtsNotFound,
    get_ecourts_client,
    is_valid_cnr,
    normalise_cnr,
)
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.clients.models import Client
from app.modules.matters.models import (
    AdvocateRole,
    FeeBasis,
    FeeEventKind,
    FeeEventStatus,
    Hearing,
    HearingStatus,
    Matter,
    MatterAdvocate,
    MatterAuthority,
    MatterFeeArrangement,
    MatterFeeEvent,
    MatterFeeMilestone,
    MatterNote,
    MatterParty,
    MatterStage,
    MatterStatus,
    MatterTask,
    MatterTeamMember,
    MilestoneStatus,
    MilestoneTrigger,
    PartySide,
    Priority,
    RateBasis,
    TaskStatus,
    TeamEndReason,
    TeamRole,
)
from app.modules.matters.repository import MatterRepository
from app.modules.notifications.models import NotificationType
from app.modules.notifications.service import create_notification
from app.modules.rates.repository import RateRepository
from app.modules.webhooks.service import emit_event
from app.modules.matters.schemas import (
    AdvocateCreate,
    AdvocateUpdate,
    CourtRecord,
    ECourtsImportRequest,
    ECourtsLookupRequest,
    FeeArrangementCreate,
    FeeArrangementRead,
    FeeArrangementUpdate,
    FeeEventCreate,
    FeeSummary,
    HearingCreate,
    HearingUpdate,
    MatterCreate,
    MatterDetail,
    MatterRead,
    MatterUpdate,
    MilestoneRead,
    NoteCreate,
    PartyCreate,
    PersonRead,
    TaskCreate,
    TeamHandover,
    TeamMemberCreate,
    TeamMemberRead,
    TeamMemberUpdate,
    TeamTransfer,
    TeamTransferResult,
    TeamConflict,
    IntakeConflict,
    BoardCard,
    BoardColumn,
    MatterBoard,
    TimelineEntry,
    WorkloadRow,
    AuthorityCreate,
)

# Which matter stage fires which milestone trigger.
_STAGE_TRIGGERS: dict[MatterStage, MilestoneTrigger] = {
    MatterStage.FILING: MilestoneTrigger.ON_FILING,
    MatterStage.PLEADINGS: MilestoneTrigger.ON_PLEADINGS,
    MatterStage.EVIDENCE: MilestoneTrigger.ON_EVIDENCE,
    MatterStage.ARGUMENTS: MilestoneTrigger.ON_ARGUMENTS,
    MatterStage.JUDGMENT: MilestoneTrigger.ON_JUDGMENT,
}

# The registry fields shared by create/update/read, applied in one place so a
# new column only has to be added to CourtRecord.
_COURT_FIELDS = tuple(CourtRecord.model_fields)


def _apply_court_record(matter: Matter, data: object) -> None:
    """Copy any court-record fields present on `data` onto the matter."""
    supplied = getattr(data, "model_fields_set", set())
    for name in _COURT_FIELDS:
        if name in supplied:
            setattr(matter, name, getattr(data, name))


# Hearing days are Indian court days, whatever the server clock's zone.
_IST = ZoneInfo("Asia/Kolkata")

# Words that do not tell two parties apart ("M/s Sharma Traders Pvt. Ltd." = "Sharma Traders").
_NAME_NOISE = {"m", "s", "ms", "the", "pvt", "private", "ltd", "limited", "llp", "co", "and", "shri", "sh",
               "smt", "mr", "mrs", "dr", "kumari", "km", "inc", "corp", "corporation", "company",
               "adv", "advocate", "sr", "senior", "ors", "anr", "others", "another", "etc"}


def _party_key(name: str | None) -> str:
    words = re.sub(r"[^\w]+", " ", (name or "").lower()).split()
    return " ".join(w for w in words if w not in _NAME_NOISE)


def _name_similarity(a: str, b: str) -> float:
    """How alike two normalised party keys are: exact 1.0; else the better of a
    word-set overlap and a character ratio, so "Ramesh Kumar Sharma" ~ "Sharma Ramesh"
    and "Mohd. Irfan" ~ "Mohammed Irfan" both score, while unrelated names do not."""
    if a == b:
        return 1.0
    wa, wb = set(a.split()), set(b.split())
    if not wa or not wb:
        return 0.0
    # Words count as the same when spelt alike ("varma" ~ "verma", "mohd" ~ "mohammed" does not, the
    # character ratio over the whole name catches that one).
    matched = sum(1 for x in wa if any(x == y or SequenceMatcher(None, x, y).ratio() >= 0.8 for y in wb))
    jaccard = matched / len(wa | wb) if matched < min(len(wa), len(wb)) else matched / max(len(wa), len(wb))
    ratio = SequenceMatcher(None, a, b).ratio()
    return round(max(jaccard, ratio), 3)


SIMILAR_NAME_THRESHOLD = 0.75


def _party_names(names: list[str | None]) -> dict[str, str]:
    """Normalised key → the name as written (first spelling wins); blanks dropped."""
    out: dict[str, str] = {}
    for n in names:
        key = _party_key(n)
        if len(key) >= 3:
            out.setdefault(key, (n or "").strip())
    return out

class MatterService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.repo = MatterRepository(session)

    async def _require_matter(self, matter_id: uuid.UUID, *, detail: bool = False) -> Matter:
        matter = await self.repo.get(self.tenant_id, matter_id, detail=detail)
        if matter is None:
            raise NotFoundError("Matter not found.")
        return matter

    # ── Client resolution ───────────────────────────────────────────
    async def _resolve_client(
        self, client_id: uuid.UUID | None, client_name: str | None
    ) -> tuple[uuid.UUID | None, str]:
        """A matter is for a client from the master (preferred) or a typed name."""
        if client_id is not None:
            client = await self.session.get(Client, client_id)
            if client is None or client.tenant_id != self.tenant_id or client.deleted_at is not None:
                raise NotFoundError("Client not found.")
            return client.id, (client_name or client.display_name)
        if not client_name:
            raise ValidationError("Pick a client from the client master or type the client's name.")
        return None, client_name

    # ── Matters ─────────────────────────────────────────────────────
    async def create_matter(self, data: MatterCreate) -> Matter:
        number = data.matter_number or f"M-{await self.repo.count(self.tenant_id) + 1:04d}"
        client_id, client_name = await self._resolve_client(data.client_id, data.client_name)
        for uid in (data.assigned_to, data.lead_counsel_id):  # audit A-32: tenant FK validation
            if uid is not None:
                await self._require_person(uid)
        matter = Matter(
            tenant_id=self.tenant_id,
            matter_number=number,
            title=data.title,
            client_id=client_id,
            client_name=client_name,
            matter_type=data.matter_type,
            stage=data.stage,
            priority=data.priority,
            practice_area=data.practice_area,
            court=data.court,
            case_number=data.case_number,
            description=data.description,
            opened_on=data.opened_on,
            limitation_date=data.limitation_date,
            assigned_to=data.assigned_to or data.lead_counsel_id,
            created_by=self.user_id,
        )
        _apply_court_record(matter, data)
        self.repo.add(matter)
        await self.session.flush()
        # Day-one team: the lead counsel plus anyone else named.
        if data.lead_counsel_id is not None:
            await self.add_team_member(
                matter.id, TeamMemberCreate(user_id=data.lead_counsel_id, role=TeamRole.LEAD_COUNSEL,
                                            from_date=data.opened_on), matter=matter,
            )
        for member in data.team:
            if data.lead_counsel_id is not None and member.user_id == data.lead_counsel_id:
                continue
            await self.add_team_member(matter.id, member, matter=matter)
        await emit_event(
            self.session,
            tenant_id=self.tenant_id,
            event_type="matter.created",
            data={"id": str(matter.id), "matter_number": matter.matter_number,
                  "title": matter.title, "client_name": matter.client_name},
        )
        return matter

    async def list_matters(
        self, status: MatterStatus | None, limit: int, offset: int,
        *, client_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None,
    ) -> list[Matter]:
        return await self.repo.list(self.tenant_id, status, limit, offset, client_id=client_id, user_id=user_id)

    async def add_authority(self, matter_id: uuid.UUID, data: AuthorityCreate) -> MatterAuthority:
        await self._require_matter(matter_id)
        authority = MatterAuthority(
            tenant_id=self.tenant_id, matter_id=matter_id, created_by=self.user_id,
            **data.model_dump(),
        )
        self.repo.add(authority)
        await self.session.flush()
        return authority

    async def remove_authority(self, matter_id: uuid.UUID, authority_id: uuid.UUID) -> None:
        authority = await self.repo.get_authority(self.tenant_id, matter_id, authority_id)
        if authority is None:
            raise NotFoundError("Authority not found.")
        authority.deleted_at = datetime.now(UTC)

    async def get_matter(self, matter_id: uuid.UUID) -> Matter:
        matter = await self._require_matter(matter_id, detail=True)
        # Dated milestones fall due by the calendar; settle them on read so the
        # page and the fee events never disagree.
        await self._fire_dated_milestones(matter)
        return matter

    async def update_matter(self, matter_id: uuid.UUID, data: MatterUpdate) -> Matter:
        matter = await self._require_matter(matter_id)
        values = data.model_dump(exclude_unset=True)
        for key in ("assigned_to", "lead_counsel_id"):  # audit A-32: tenant FK validation
            if values.get(key) is not None:
                await self._require_person(values[key])
        if "client_id" in values or "client_name" in values:
            # A new client_id refreshes the name from the master unless a name
            # is given too; unlinking (client_id=null) keeps the name on record.
            wants_new_client = values.get("client_id") is not None and values.get("client_id") != matter.client_id
            client_id, client_name = await self._resolve_client(
                values.get("client_id", matter.client_id),
                values.get("client_name") or (None if wants_new_client else matter.client_name),
            )
            values["client_id"], values["client_name"] = client_id, client_name
        old_stage, old_status = matter.stage, matter.status
        for field, value in values.items():
            setattr(matter, field, value)
        await self.session.flush()
        # Stage / closure triggers for fee milestones.
        if matter.stage != old_stage and matter.stage in _STAGE_TRIGGERS:
            await self._fire_milestones(matter, _STAGE_TRIGGERS[matter.stage])
        if matter.status == MatterStatus.CLOSED and old_status != MatterStatus.CLOSED:
            await self._fire_milestones(matter, MilestoneTrigger.ON_CLOSURE)
        return matter

    # ── Read models with names resolved ─────────────────────────────
    async def _user_names(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        return {uid: u.full_name for uid, u in (await self.repo.names(self.tenant_id, ids)).items()}

    async def to_read(self, matters: list[Matter]) -> list[MatterRead]:
        names = await self._user_names({m.lead_counsel_id for m in matters if m.lead_counsel_id})
        out = []
        for m in matters:
            r = MatterRead.model_validate(m)
            r.lead_counsel_name = names.get(m.lead_counsel_id) if m.lead_counsel_id else None
            out.append(r)
        return out

    async def to_detail(self, matter: Matter) -> MatterDetail:
        ids = {t.user_id for t in matter.team} | {t.successor_user_id for t in matter.team if t.successor_user_id}
        if matter.lead_counsel_id:
            ids.add(matter.lead_counsel_id)
        users = await self.repo.names(self.tenant_id, ids)
        today = date.today()
        cards = await RateRepository(self.session).current_for_users(
            self.tenant_id, {t.user_id for t in matter.team if t.to_date is None}, today
        )
        detail = MatterDetail.model_validate(matter)
        detail.lead_counsel_name = users[matter.lead_counsel_id].full_name if matter.lead_counsel_id in users else None
        team: list[TeamMemberRead] = []
        for t in sorted(matter.team, key=lambda x: (x.to_date is not None, x.from_date)):
            r = TeamMemberRead.model_validate(t)
            u = users.get(t.user_id)
            r.user_name, r.user_email = (u.full_name, u.email) if u else (None, None)
            r.successor_name = users[t.successor_user_id].full_name if t.successor_user_id in users else None
            r.is_active = t.to_date is None
            # Same basis as the override, else hourly, else whatever card they have.
            card = (
                cards.get((t.user_id, str(t.rate_basis or RateBasis.HOURLY)))
                or cards.get((t.user_id, "hourly"))
                or next((c for (uid, _), c in cards.items() if uid == t.user_id), None)
            )
            if card is not None:
                r.card_rate_basis, r.card_rate_amount = RateBasis(card.basis), card.amount
            team.append(r)
        detail.team = team
        detail.fee_arrangements = [self._arrangement_read(a) for a in matter.fee_arrangements if a.deleted_at is None]
        return detail

    @staticmethod
    def _milestone_amount(arr: MatterFeeArrangement, ms: MatterFeeMilestone) -> Decimal | None:
        if ms.amount is not None:
            return Decimal(ms.amount)
        if ms.percent is not None and arr.fixed_fee is not None:
            return (Decimal(arr.fixed_fee) * Decimal(ms.percent) / Decimal(100)).quantize(Decimal("0.01"))
        return None

    def _arrangement_read(self, arr: MatterFeeArrangement) -> FeeArrangementRead:
        r = FeeArrangementRead.model_validate(arr)
        r.is_active = arr.effective_to is None or arr.effective_to >= date.today()
        out = []
        for ms in arr.milestones:
            if ms.deleted_at is not None:
                continue
            mr = MilestoneRead.model_validate(ms)
            mr.computed_amount = self._milestone_amount(arr, ms)
            out.append(mr)
        r.milestones = out
        return r

    async def delete_matter(self, matter_id: uuid.UUID) -> None:
        matter = await self._require_matter(matter_id)
        matter.deleted_at = datetime.now(UTC)

    async def timeline(self, matter_id: uuid.UUID) -> list[TimelineEntry]:
        """A chronological (newest-first) view of a matter's activity."""
        matter = await self._require_matter(matter_id, detail=True)
        entries: list[TimelineEntry] = [
            TimelineEntry(
                kind="matter", at=matter.created_at, title="Matter opened",
                detail=matter.matter_number,
            )
        ]
        for hearing in matter.hearings:
            entries.append(
                TimelineEntry(
                    kind="hearing", at=hearing.scheduled_on,
                    title=hearing.purpose or "Hearing", detail=hearing.court,
                    status=str(hearing.status),
                )
            )
        for task in matter.tasks:
            entries.append(
                TimelineEntry(kind="task", at=task.created_at, title=task.title, status=str(task.status))
            )
            if task.completed_at is not None:
                entries.append(
                    TimelineEntry(kind="task_done", at=task.completed_at, title=f"Completed: {task.title}")
                )
        for note in matter.notes:
            entries.append(TimelineEntry(kind="note", at=note.created_at, title="Note", detail=note.body))

        # Strip tzinfo for a uniform sort (SQLite returns naive, PG aware).
        entries.sort(key=lambda e: e.at.replace(tzinfo=None), reverse=True)
        return entries

    # ── Parties ─────────────────────────────────────────────────────
    async def add_party(self, matter_id: uuid.UUID, data: PartyCreate) -> MatterParty:
        await self._require_matter(matter_id)
        party = MatterParty(
            tenant_id=self.tenant_id,
            matter_id=matter_id,
            name=data.name,
            role=data.role,
            contact=data.contact,
            side=data.side,
            position=data.position,
            lawful_basis=data.lawful_basis,
            basis_note=data.basis_note,
        )
        self.repo.add(party)
        await self.session.flush()
        return party

    # ─── Advocates on record ────────────────────────────────────────
    async def add_advocate(self, matter_id: uuid.UUID, data: AdvocateCreate) -> MatterAdvocate:
        await self._require_matter(matter_id)
        if data.user_id is not None:  # audit A-32: an in-house advocate must be one of ours
            await self._require_person(data.user_id)
        advocate = MatterAdvocate(
            tenant_id=self.tenant_id,
            matter_id=matter_id,
            **data.model_dump(),
        )
        self.repo.add(advocate)
        await self.session.flush()
        return advocate

    async def update_advocate(
        self, matter_id: uuid.UUID, advocate_id: uuid.UUID, data: AdvocateUpdate
    ) -> MatterAdvocate:
        advocate = await self.repo.get_advocate(self.tenant_id, matter_id, advocate_id)
        if advocate is None:
            raise NotFoundError("Advocate not found on this matter.")
        if data.model_dump(exclude_unset=True).get("user_id") is not None:
            await self._require_person(data.user_id)  # audit A-32
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(advocate, field, value)
        await self.session.flush()
        return advocate

    async def remove_advocate(self, matter_id: uuid.UUID, advocate_id: uuid.UUID) -> None:
        advocate = await self.repo.get_advocate(self.tenant_id, matter_id, advocate_id)
        if advocate is None:
            raise NotFoundError("Advocate not found on this matter.")
        advocate.deleted_at = datetime.now(UTC)

    async def opposing_counsel_history(self, name: str) -> list[Matter]:
        """Other matters in this tenant where the same advocate appeared against us."""
        return await self.repo.matters_with_opposing_advocate(self.tenant_id, name)

    # ─── eCourts ────────────────────────────────────────────────────
    async def ecourts_lookup(self, data: ECourtsLookupRequest) -> ECourtsCase:
        """Fetch a case from the configured provider. Read-only — writes nothing."""
        client = get_ecourts_client()
        if data.cnr_number:
            cnr = normalise_cnr(data.cnr_number)
            if not is_valid_cnr(cnr):
                raise ValidationError(
                    "A CNR is 16 characters, e.g. DLHC010001232024. "
                    "Otherwise search by case type, number and year."
                )
            return await client.fetch_by_cnr(cnr)

        if not (data.case_type and data.case_number and data.case_year):
            raise ValidationError(
                "Provide a CNR, or all of case type, case number and year."
            )
        results = await client.search(
            case_type=data.case_type,
            case_number=data.case_number,
            case_year=data.case_year,
            state=data.state,
            district=data.district,
            court_establishment=data.court_establishment,
        )
        if not results:
            raise ECourtsNotFound("No case matched those details.")
        return results[0]

    async def import_from_ecourts(self, data: ECourtsImportRequest) -> Matter:
        """Fetch a case and file it as a matter, with both sides' counsel."""
        case = await self.ecourts_lookup(data)

        if case.cnr_number:
            existing = await self.repo.get_by_cnr(self.tenant_id, case.cnr_number)
            if existing is not None:
                raise ConflictError(
                    f"This case is already filed as matter {existing.matter_number}."
                )

        number = f"M-{await self.repo.count(self.tenant_id) + 1:04d}"
        client_id, client_name = await self._resolve_client(data.client_id, data.client_name)
        matter = Matter(
            tenant_id=self.tenant_id,
            matter_number=number,
            title=case.cause_title or f"{case.case_type} {case.case_number}/{case.case_year}",
            client_id=client_id,
            client_name=client_name,
            matter_type=data.matter_type,
            court=case.court_establishment,
            # Bare number only — `case_type` and `case_year` are their own
            # columns now, and the UI composes "W.P.(C) 1234/2024" from all three.
            case_number=case.case_number,
            assigned_to=data.assigned_to or data.lead_counsel_id,
            created_by=self.user_id,
            cnr_number=case.cnr_number,
            case_type=case.case_type,
            case_year=case.case_year,
            filing_number=case.filing_number,
            filing_date=case.filing_date,
            registration_number=case.registration_number,
            registration_date=case.registration_date,
            court_level=case.court_level,
            court_establishment=case.court_establishment,
            state=case.state,
            district=case.district,
            coram=case.coram,
            cause_title=case.cause_title,
            acts=list(case.acts),
            sections=list(case.sections),
            next_hearing_date=case.next_hearing_date,
            last_hearing_date=case.last_hearing_date,
            hearing_purpose=case.hearing_purpose,
            disposal_date=case.disposal_date,
            disposal_nature=case.disposal_nature,
            ecourts_synced_at=datetime.now(UTC),
            ecourts_source=case.source,
        )
        self.repo.add(matter)
        await self.session.flush()

        self._file_sides(matter, case, our_role=data.our_side_role)
        await self.session.flush()
        if data.lead_counsel_id is not None:
            await self.add_team_member(
                matter.id, TeamMemberCreate(user_id=data.lead_counsel_id, role=TeamRole.LEAD_COUNSEL), matter=matter
            )
        await emit_event(
            self.session,
            tenant_id=self.tenant_id,
            event_type="matter.created",
            data={"id": str(matter.id), "matter_number": matter.matter_number,
                  "source": "ecourts", "cnr_number": matter.cnr_number},
        )
        return matter

    async def refresh_from_ecourts(self, matter_id: uuid.UUID) -> Matter:
        """Re-pull registry data for a matter that already has a CNR."""
        matter = await self._require_matter(matter_id, detail=True)
        if not matter.cnr_number:
            raise ValidationError(
                "This matter has no CNR, so there is nothing to sync. "
                "Add one, or import the case from eCourts."
            )
        case = await get_ecourts_client().fetch_by_cnr(matter.cnr_number)

        # Only registry-owned fields are overwritten; the firm's own data
        # (title, client, assignment, notes) is never clobbered by a sync.
        for field in (
            "case_type", "case_year", "filing_number", "filing_date",
            "registration_number", "registration_date", "court_level",
            "court_establishment", "state", "district", "coram", "cause_title",
            "next_hearing_date", "last_hearing_date", "hearing_purpose",
            "disposal_date", "disposal_nature",
        ):
            value = getattr(case, field, None)
            if value is not None:
                setattr(matter, field, value)
        if case.acts:
            matter.acts = list(case.acts)
        if case.sections:
            matter.sections = list(case.sections)
        matter.ecourts_synced_at = datetime.now(UTC)
        matter.ecourts_source = case.source
        await self.session.flush()
        return matter

    def _file_sides(self, matter: Matter, case: ECourtsCase, *, our_role: str) -> None:
        """Split registry parties/advocates into our side and the opponent's.

        The registry does not know which side instructed us, so the caller says
        which cause-title role our client holds and everything else is filed as
        opposing.
        """
        our_role_lc = (our_role or "").strip().lower()

        for party in case.parties:
            role_lc = (party.role or "").lower()
            side = PartySide.OURS if role_lc == our_role_lc else PartySide.OPPOSING
            self.repo.add(
                MatterParty(
                    tenant_id=self.tenant_id,
                    matter_id=matter.id,
                    name=party.name,
                    role=party.role,
                    side=side,
                    position=party.position,
                )
            )

        for advocate in case.advocates:
            appears_lc = (advocate.appears_for or "").lower()
            side = PartySide.OURS if our_role_lc and our_role_lc in appears_lc else PartySide.OPPOSING
            self.repo.add(
                MatterAdvocate(
                    tenant_id=self.tenant_id,
                    matter_id=matter.id,
                    name=advocate.name,
                    side=side,
                    role=AdvocateRole.ARGUING_COUNSEL,
                    bar_enrolment_number=advocate.bar_enrolment_number,
                    party_represented=advocate.appears_for,
                )
            )

    # ── Hearings ────────────────────────────────────────────────────
    async def add_hearing(self, matter_id: uuid.UUID, data: HearingCreate) -> Hearing:
        await self._require_matter(matter_id)
        hearing = Hearing(
            tenant_id=self.tenant_id,
            matter_id=matter_id,
            scheduled_on=data.scheduled_on,
            court=data.court,
            court_room=_blank_to_none(data.court_room),
            item_number=_blank_to_none(data.item_number),
            judge=data.judge,
            purpose=data.purpose,
        )
        self.repo.add(hearing)
        await self.session.flush()
        await self._sync_next_hearing(matter_id)
        return hearing

    async def update_hearing(self, hearing_id: uuid.UUID, data: HearingUpdate) -> Hearing:
        hearing = await self.repo.get_hearing(self.tenant_id, hearing_id)
        if hearing is None:
            raise NotFoundError("Hearing not found.")
        old_status = hearing.status
        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "scheduled_on" and value is None:
                continue
            if field in ("court", "court_room", "item_number", "purpose"):
                value = _blank_to_none(value)
            setattr(hearing, field, value)
        await self.session.flush()
        if hearing.status != old_status and hearing.status in (HearingStatus.HELD, HearingStatus.ADJOURNED):
            await self._on_hearing_outcome(hearing)
        await self._sync_next_hearing(hearing.matter_id)
        return hearing

    async def _sync_next_hearing(self, matter_id: uuid.UUID) -> None:
        """Keep the matter's "Next hearing" (and the 14-day tile) in step with its hearings.

        Next = the earliest scheduled hearing from today on, or the next date an
        adjourned/held hearing was given. Last = the latest hearing that took
        place. With nothing upcoming, a date that has passed or belonged to a
        hearing now held, adjourned or cancelled is cleared; a future date typed
        on the matter by hand (or from eCourts) is kept.
        """
        matter = await self._require_matter(matter_id)
        hearings = await self.repo.matter_hearings(self.tenant_id, matter_id)
        today = datetime.now(_IST).date()

        def day(value: datetime) -> date:
            return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(_IST).date()

        upcoming = [(day(h.scheduled_on), h.purpose) for h in hearings
                    if h.status == HearingStatus.SCHEDULED and day(h.scheduled_on) >= today]
        upcoming += [(day(h.next_date), None) for h in hearings
                     if h.next_date and h.status in (HearingStatus.HELD, HearingStatus.ADJOURNED) and day(h.next_date) >= today]
        past = [day(h.scheduled_on) for h in hearings if h.status in (HearingStatus.HELD, HearingStatus.ADJOURNED)]
        if past:
            matter.last_hearing_date = max(past)
        if upcoming:
            when, purpose = min(upcoming, key=lambda item: (item[0], item[1] is None))
            matter.next_hearing_date = when
            matter.hearing_purpose = purpose
        elif matter.next_hearing_date and (
            matter.next_hearing_date < today
            or matter.next_hearing_date in {day(h.scheduled_on) for h in hearings if h.status != HearingStatus.SCHEDULED}
        ):
            matter.next_hearing_date = None
            matter.hearing_purpose = None
        await self.session.flush()

    async def upcoming_hearings(self, limit: int, offset: int) -> list[Hearing]:
        return await self.repo.upcoming_hearings(self.tenant_id, limit, offset)

    # ── Tasks ───────────────────────────────────────────────────────
    async def add_task(self, matter_id: uuid.UUID, data: TaskCreate) -> MatterTask:
        await self._require_matter(matter_id)
        task = MatterTask(
            tenant_id=self.tenant_id,
            matter_id=matter_id,
            title=data.title,
            due_on=data.due_on,
            assigned_to=data.assigned_to,
        )
        self.repo.add(task)
        await self.session.flush()
        return task

    async def set_task_done(self, task_id: uuid.UUID, done: bool) -> MatterTask:
        task = await self.repo.get_task(self.tenant_id, task_id)
        if task is None:
            raise NotFoundError("Task not found.")
        task.status = TaskStatus.DONE if done else TaskStatus.OPEN
        task.completed_at = datetime.now(UTC) if done else None
        return task

    # ── Notes ───────────────────────────────────────────────────────
    async def add_note(self, matter_id: uuid.UUID, data: NoteCreate) -> MatterNote:
        await self._require_matter(matter_id)
        note = MatterNote(
            tenant_id=self.tenant_id,
            matter_id=matter_id,
            author_id=self.user_id,
            body=data.body,
        )
        self.repo.add(note)
        await self.session.flush()
        return note

    # ── Team ────────────────────────────────────────────────────────
    async def people(self) -> list[PersonRead]:
        return [PersonRead.model_validate(u) for u in await self.repo.people(self.tenant_id)]

    async def intake_conflicts(self, names: list[str], *, exclude_matter: uuid.UUID | None = None) -> list[IntakeConflict]:
        """Firm-wide: where do these names already appear — as a client, on our side, the
        other side, or as opposing counsel — exactly or under a similar spelling?

        For matter intake: the client's name and the opposing party's name are checked
        against every matter of the firm. Advisory, like the team check.
        """
        queries = [(n.strip(), _party_key(n)) for n in names if n and len(_party_key(n)) >= 3]
        if not queries:
            return []
        hits: list[IntakeConflict] = []
        for matter, parties, advocates in await self.repo.names_on_record(self.tenant_id):
            if exclude_matter and matter.id == exclude_matter:
                continue
            on_record: list[tuple[str, str]] = [(matter.client_name, "client")]
            on_record += [(p.name, str(p.side)) for p in parties]
            on_record += [(a.name, "counsel") for a in advocates]
            for query, qkey in queries:
                best: IntakeConflict | None = None
                for name, side in on_record:
                    score = _name_similarity(qkey, _party_key(name))
                    if score < SIMILAR_NAME_THRESHOLD or (best and score <= best.score):
                        continue
                    best = IntakeConflict(
                        query=query, matter_id=matter.id, matter_number=matter.matter_number, title=matter.title,
                        status=matter.status, party_name=name, side=side,
                        match="exact" if score == 1.0 else "similar", score=score,
                    )
                if best:
                    hits.append(best)
        return sorted(hits, key=lambda h: (h.status == MatterStatus.CLOSED, -h.score, h.matter_number))

    async def team_conflicts(self, matter_id: uuid.UUID, user_id: uuid.UUID) -> list[TeamConflict]:
        """Before putting someone on a matter: were they ever on the other side of its parties?

        Compares names (normalised: case, punctuation, "M/s", "Pvt Ltd"…) between this
        matter's sides and every other matter of the firm the person is or was on.
        Advisory: a match is for the partner to look at, not a block.
        """
        matter = await self._require_matter(matter_id, detail=True)
        await self._require_person(user_id)
        parties = [p for p in matter.parties if p.deleted_at is None]
        ours = _party_names([matter.client_name] + [p.name for p in parties if p.side == PartySide.OURS])
        theirs = _party_names([p.name for p in parties if p.side == PartySide.OPPOSING])
        hits: list[TeamConflict] = []
        for other, current, other_parties in await self.repo.stints_with_sides(self.tenant_id, user_id, matter.id):
            their_side = _party_names([p.name for p in other_parties if p.side == PartySide.OPPOSING])
            our_side = _party_names([other.client_name] + [p.name for p in other_parties if p.side == PartySide.OURS])
            for key in sorted(ours.keys() & their_side.keys()):
                hits.append(TeamConflict(matter_id=other.id, matter_number=other.matter_number, title=other.title,
                                         party_name=ours[key], kind="acted_against_client", current=current))
            for key in sorted(theirs.keys() & our_side.keys()):
                hits.append(TeamConflict(matter_id=other.id, matter_number=other.matter_number, title=other.title,
                                         party_name=theirs[key], kind="acted_for_opponent", current=current))
        return sorted(hits, key=lambda h: (not h.current, h.matter_number or "", h.party_name))

    # ── Board ──────────────────────────────────────────────────────
    _STAGE_ORDER = [s for s in MatterStage if s != MatterStage.CLOSED] + [MatterStage.CLOSED]
    _PRIORITY_RANK = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
    _URGENT = {"hearing_today", "limitation_passed", "limitation_soon", "overdue_task"}
    _ATTENTION = _URGENT | {"no_next_step", "stale"}
    # Worst first inside a column.
    _SEVERITY = ["limitation_passed", "hearing_today", "overdue_task", "limitation_soon",
                 "hearing_soon", "no_next_step", "stale", "on_hold"]

    async def board(self, *, user_id: uuid.UUID | None = None) -> MatterBoard:
        """Open matters by stage, each with its owner, next step and what needs attention."""
        matters = await self.repo.board_matters(self.tenant_id, user_id=user_id)
        ids = {m.id for m in matters}
        today = datetime.now(_IST).date()
        day_start = datetime.combine(today, datetime.min.time(), _IST)
        hearings = await self.repo.next_hearings(self.tenant_id, ids, day_start)
        tasks = await self.repo.open_tasks(self.tenant_id, ids)
        activity = await self.repo.last_activity(self.tenant_id, ids)
        owners = {m.lead_counsel_id or m.assigned_to for m in matters} - {None}
        names = await self.repo.names(self.tenant_id, owners)

        def to_ist_date(value: datetime | None) -> date | None:
            if value is None:
                return None
            return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(_IST).date()

        cards: list[BoardCard] = []
        flag_counts: dict[str, int] = {}
        for m in matters:
            hearing = hearings.get(m.id)
            next_on = to_ist_date(hearing.scheduled_on) if hearing else (
                m.next_hearing_date if m.next_hearing_date and m.next_hearing_date >= today else None
            )
            open_tasks = tasks.get(m.id, [])
            overdue = [t for t in open_tasks if t.due_on and t.due_on < today]
            next_task = open_tasks[0] if open_tasks else None
            latest = activity.get(m.id)
            touched = m.updated_at if m.updated_at and m.updated_at.tzinfo else (m.updated_at.replace(tzinfo=UTC) if m.updated_at else None)
            if latest and (touched is None or latest > touched):
                touched = latest
            last_on = to_ist_date(touched)
            idle = (today - last_on).days if last_on else None

            flags: list[str] = []
            if next_on == today:
                flags.append("hearing_today")
            elif next_on and 0 < (next_on - today).days <= 7:
                flags.append("hearing_soon")
            if m.limitation_date:
                left = (m.limitation_date - today).days
                if left < 0:
                    flags.append("limitation_passed")
                elif left <= 30:
                    flags.append("limitation_soon")
            if overdue:
                flags.append("overdue_task")
            if next_on is None and not open_tasks:
                flags.append("no_next_step")
            if m.status == MatterStatus.ON_HOLD:
                flags.append("on_hold")
            elif idle is not None and idle >= 30:
                flags.append("stale")
            for f in flags:
                flag_counts[f] = flag_counts.get(f, 0) + 1

            owner_id = m.lead_counsel_id or m.assigned_to
            owner = names.get(owner_id) if owner_id else None
            cards.append(BoardCard(
                id=m.id, matter_number=m.matter_number, title=m.title, client_name=m.client_name,
                status=m.status, stage=m.stage, priority=m.priority, court=m.court,
                owner_id=owner_id, owner_name=owner.full_name if owner else None,
                next_hearing_on=next_on,
                next_hearing_at=hearing.scheduled_on if hearing else None,
                next_hearing_court=(hearing.court if hearing else None) or m.court if next_on else None,
                next_hearing_purpose=(hearing.purpose if hearing else m.hearing_purpose) if next_on else None,
                next_task_title=next_task.title if next_task else None,
                next_task_due_on=next_task.due_on if next_task else None,
                open_tasks=len(open_tasks), overdue_tasks=len(overdue),
                limitation_date=m.limitation_date, last_activity_on=last_on, days_idle=idle, flags=flags,
            ))

        def sort_key(c: BoardCard) -> tuple:
            worst = min((self._SEVERITY.index(f) for f in c.flags if f in self._SEVERITY), default=len(self._SEVERITY))
            return (worst, c.next_hearing_on or date.max, self._PRIORITY_RANK[c.priority], c.matter_number)

        columns = []
        for stage in self._STAGE_ORDER:
            in_stage = sorted((c for c in cards if c.stage == stage), key=sort_key)
            if in_stage or stage != MatterStage.CLOSED:
                columns.append(BoardColumn(stage=stage, count=len(in_stage), matters=in_stage))
        return MatterBoard(
            columns=columns, total=len(cards),
            attention=sum(1 for c in cards if self._ATTENTION & set(c.flags)),
            flag_counts=flag_counts, generated_at=datetime.now(UTC),
        )

    async def workload(self, days: int = 14) -> list[WorkloadRow]:
        """Who carries what: every active colleague, busiest first (people with nothing too)."""
        stints = await self.repo.open_stints(self.tenant_id)
        start = datetime.combine(datetime.now(_IST).date(), datetime.min.time(), _IST)
        hearings = await self.repo.hearings_per_matter(
            self.tenant_id, {m for _, _, m in stints}, start, start + timedelta(days=days))
        matters: dict[uuid.UUID, set[uuid.UUID]] = {}
        led: dict[uuid.UUID, set[uuid.UUID]] = {}
        roles: dict[uuid.UUID, dict[str, int]] = {}
        for user, role, matter in stints:
            matters.setdefault(user, set()).add(matter)
            if role == TeamRole.LEAD_COUNSEL:
                led.setdefault(user, set()).add(matter)
            per = roles.setdefault(user, {})
            per[str(role)] = per.get(str(role), 0) + 1
        rows = [
            WorkloadRow(
                user_id=u.id, full_name=u.full_name,
                open_matters=len(matters.get(u.id, ())), lead_matters=len(led.get(u.id, ())),
                roles=roles.get(u.id, {}),
                hearings_next_14_days=sum(hearings.get(m, 0) for m in matters.get(u.id, ())),
            )
            for u in await self.repo.people(self.tenant_id)
        ]
        return sorted(rows, key=lambda r: (-r.open_matters, -r.hearings_next_14_days, r.full_name.lower()))

    async def _require_person(self, user_id: uuid.UUID) -> None:
        users = await self.repo.names(self.tenant_id, {user_id})
        if user_id not in users or users[user_id].deleted_at is not None:
            raise NotFoundError("That person is not a member of this organisation.")

    async def _set_lead(self, matter: Matter, user_id: uuid.UUID | None) -> None:
        matter.lead_counsel_id = user_id
        # `assigned_to` predates the team; keep it pointing at the lead so
        # dashboards and "my matters" filters built on it still work.
        matter.assigned_to = user_id

    async def add_team_member(
        self, matter_id: uuid.UUID, data: TeamMemberCreate, *, matter: Matter | None = None, notify: bool = True
    ) -> MatterTeamMember:
        matter = matter or await self._require_matter(matter_id)
        await self._require_person(data.user_id)
        start = data.from_date or date.today()
        active = await self.repo.active_team(self.tenant_id, matter.id)
        for m in active:
            if m.user_id == data.user_id and m.role == data.role:
                raise ConflictError("This person already holds that role on the matter.")
        if data.role == TeamRole.LEAD_COUNSEL:
            # One lead at a time: the outgoing lead's stint ends the day before.
            for m in active:
                if m.role == TeamRole.LEAD_COUNSEL and m.user_id != data.user_id:
                    m.to_date = max(m.from_date, start - timedelta(days=1))
                    m.end_reason = TeamEndReason.REASSIGNED
                    m.successor_user_id = data.user_id
            await self._set_lead(matter, data.user_id)
        member = MatterTeamMember(
            tenant_id=self.tenant_id, matter_id=matter.id, user_id=data.user_id, role=data.role,
            from_date=start, rate_basis=data.rate_basis, rate_amount=data.rate_amount,
            notes=data.notes, added_by=self.user_id,
        )
        self.repo.add(member)
        await self.session.flush()
        if notify:
            await create_notification(
                self.session, user_id=data.user_id, type=NotificationType.MATTER_ASSIGNED,
                actor_id=self.user_id,
                message=f"You are now {data.role.replace('_', ' ')} on {matter.matter_number} — {matter.cause_title or matter.title}",
                link=f"/app/matters/{matter.id}",
            )
        return member

    async def update_team_member(
        self, matter_id: uuid.UUID, member_id: uuid.UUID, data: TeamMemberUpdate
    ) -> MatterTeamMember:
        matter = await self._require_matter(matter_id)
        member = await self.repo.get_team_member(self.tenant_id, matter_id, member_id)
        if member is None:
            raise NotFoundError("Team member not found on this matter.")
        values = data.model_dump(exclude_unset=True)
        new_role = values.get("role")
        if new_role == TeamRole.LEAD_COUNSEL and member.role != TeamRole.LEAD_COUNSEL and member.to_date is None:
            for m in await self.repo.active_team(self.tenant_id, matter_id):
                if m.role == TeamRole.LEAD_COUNSEL and m.id != member.id:
                    m.to_date = date.today()
                    m.end_reason = TeamEndReason.REASSIGNED
                    m.successor_user_id = member.user_id
            await self._set_lead(matter, member.user_id)
        elif member.role == TeamRole.LEAD_COUNSEL and new_role not in (None, TeamRole.LEAD_COUNSEL):
            if matter.lead_counsel_id == member.user_id:
                await self._set_lead(matter, None)
        for field, value in values.items():
            setattr(member, field, value)
        await self.session.flush()
        return member

    async def handover(
        self, matter_id: uuid.UUID, member_id: uuid.UUID, data: TeamHandover
    ) -> list[MatterTeamMember]:
        """End a stint; start the successor's in the same role (or the one given).

        Returns the rows touched: the ended one and, if any, the new one.
        """
        matter = await self._require_matter(matter_id)
        member = await self.repo.get_team_member(self.tenant_id, matter_id, member_id)
        if member is None:
            raise NotFoundError("Team member not found on this matter.")
        if member.to_date is not None:
            raise ValidationError("This stint has already ended.")
        effective = data.effective_from or date.today()
        if effective < member.from_date:
            raise ValidationError("The hand-over cannot be earlier than the day the stint began.")
        member.to_date = effective
        member.end_reason = data.reason
        member.successor_user_id = data.successor_user_id
        if data.notes:
            member.notes = (member.notes + "\n" if member.notes else "") + data.notes
        touched = [member]
        if member.role == TeamRole.LEAD_COUNSEL and matter.lead_counsel_id == member.user_id:
            await self._set_lead(matter, None)
        await self.session.flush()
        if data.successor_user_id is not None:
            if data.successor_user_id == member.user_id:
                raise ValidationError("The successor must be a different person.")
            successor = await self.add_team_member(
                matter_id,
                TeamMemberCreate(
                    user_id=data.successor_user_id, role=data.successor_role or member.role,
                    from_date=effective, notes=f"Took over from the previous {member.role.replace('_', ' ')}.",
                ),
                matter=matter,
            )
            touched.append(successor)
        return touched

    async def transfer(self, data: TeamTransfer) -> TeamTransferResult:
        """Move all of one person's active stints to another (they left, or the
        practice was reorganised) — one call, every open matter, history kept."""
        if data.from_user_id == data.to_user_id:
            raise ValidationError("Choose two different people.")
        await self._require_person(data.to_user_id)
        effective = data.effective_from or date.today()
        stints = await self.repo.active_stints_of(self.tenant_id, data.from_user_id, data.matter_ids)
        numbers: list[str] = []
        for member, matter in stints:
            member.to_date = max(member.from_date, effective)
            member.end_reason = data.reason
            member.successor_user_id = data.to_user_id
            if data.notes:
                member.notes = (member.notes + "\n" if member.notes else "") + data.notes
            if member.role == TeamRole.LEAD_COUNSEL and matter.lead_counsel_id == member.user_id:
                await self._set_lead(matter, None)
            await self.session.flush()
            # Skip if the successor already holds that role on this matter.
            already = any(
                m.user_id == data.to_user_id and m.role == member.role
                for m in await self.repo.active_team(self.tenant_id, matter.id)
            )
            if not already:
                await self.add_team_member(
                    matter.id,
                    TeamMemberCreate(user_id=data.to_user_id, role=member.role, from_date=effective,
                                     notes=f"Transferred ({data.reason.replace('_', ' ')})."),
                    matter=matter, notify=False,
                )
            elif member.role == TeamRole.LEAD_COUNSEL:
                await self._set_lead(matter, data.to_user_id)
            numbers.append(matter.matter_number)
        if numbers:
            await create_notification(
                self.session, user_id=data.to_user_id, type=NotificationType.MATTER_ASSIGNED,
                actor_id=self.user_id,
                message=f"{len(numbers)} matter{'s' if len(numbers) != 1 else ''} transferred to you: {', '.join(numbers[:8])}{'…' if len(numbers) > 8 else ''}",
                link="/app/matters",
            )
        return TeamTransferResult(moved=len(numbers), matter_numbers=numbers)

    async def remove_team_member(self, matter_id: uuid.UUID, member_id: uuid.UUID) -> None:
        """Delete a row added by mistake. Ending a real stint is `handover`."""
        matter = await self._require_matter(matter_id)
        member = await self.repo.get_team_member(self.tenant_id, matter_id, member_id)
        if member is None:
            raise NotFoundError("Team member not found on this matter.")
        member.deleted_at = datetime.now(UTC)
        if member.to_date is None and member.role == TeamRole.LEAD_COUNSEL and matter.lead_counsel_id == member.user_id:
            await self._set_lead(matter, None)

    # ── Fee arrangements ────────────────────────────────────────────
    async def add_arrangement(self, matter_id: uuid.UUID, data: FeeArrangementCreate) -> MatterFeeArrangement:
        matter = await self._require_matter(matter_id)
        start = data.effective_from or date.today()
        # Renegotiation: the open arrangement ends the day before the new one.
        current = await self.repo.active_arrangement(self.tenant_id, matter_id)
        if current is not None:
            if current.effective_from >= start:
                raise ValidationError(
                    f"The current arrangement began on {current.effective_from:%d/%m/%Y}; "
                    "the new one must start after that."
                )
            current.effective_to = start - timedelta(days=1)
        arr = MatterFeeArrangement(
            tenant_id=self.tenant_id, matter_id=matter_id, basis=data.basis, currency=data.currency.upper(),
            fixed_fee=data.fixed_fee, per_hearing_fee=data.per_hearing_fee,
            non_effective_hearing_fee=data.non_effective_hearing_fee, hourly_rate=data.hourly_rate,
            retainer_amount=data.retainer_amount, retainer_period=data.retainer_period,
            retainer_includes=data.retainer_includes, fee_cap=data.fee_cap,
            expenses_billable=data.expenses_billable, gst_applicable=data.gst_applicable,
            agreed_on=data.agreed_on, effective_from=start, terms=data.terms, created_by=self.user_id,
        )
        arr.milestones = [
            MatterFeeMilestone(
                tenant_id=self.tenant_id, matter_id=matter_id, sequence=i + 1, label=m.label, trigger=m.trigger,
                amount=m.amount, percent=m.percent, due_on=m.due_on, due_days=m.due_days,
            )
            for i, m in enumerate(data.milestones)
        ]
        self.repo.add(arr)
        await self.session.flush()
        # The advance falls due on engagement, and a retainer's first period starts now.
        await self._fire_milestones(matter, MilestoneTrigger.ADVANCE, arrangement=arr)
        if arr.retainer_amount is not None and arr.retainer_period is not None:
            self._raise_event(
                matter, arr, kind=FeeEventKind.RETAINER, amount=Decimal(arr.retainer_amount),
                description=f"Retainer — {arr.retainer_period.replace('_', ' ')} period from {start:%d/%m/%Y}",
                occurred_on=start, due_days=7,
            )
        await self.session.flush()
        return arr

    async def update_arrangement(
        self, matter_id: uuid.UUID, arrangement_id: uuid.UUID, data: FeeArrangementUpdate
    ) -> MatterFeeArrangement:
        await self._require_matter(matter_id)
        arr = await self.repo.get_arrangement(self.tenant_id, matter_id, arrangement_id)
        if arr is None:
            raise NotFoundError("Fee arrangement not found.")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(arr, field, value)
        await self.session.flush()
        return arr

    async def delete_arrangement(self, matter_id: uuid.UUID, arrangement_id: uuid.UUID) -> None:
        await self._require_matter(matter_id)
        arr = await self.repo.get_arrangement(self.tenant_id, matter_id, arrangement_id)
        if arr is None:
            raise NotFoundError("Fee arrangement not found.")
        arr.deleted_at = datetime.now(UTC)

    def _raise_event(
        self, matter: Matter, arr: MatterFeeArrangement | None, *, kind: FeeEventKind, amount: Decimal,
        description: str, occurred_on: date, due_days: int, milestone: MatterFeeMilestone | None = None,
        hearing: Hearing | None = None,
    ) -> MatterFeeEvent:
        event = MatterFeeEvent(
            tenant_id=self.tenant_id, matter_id=matter.id, arrangement_id=arr.id if arr else None,
            milestone_id=milestone.id if milestone else None, hearing_id=hearing.id if hearing else None,
            kind=kind, description=description[:300], occurred_on=occurred_on,
            due_on=occurred_on + timedelta(days=due_days), amount=amount,
            currency=arr.currency if arr else "INR", created_by=self.user_id,
        )
        self.repo.add(event)
        return event

    async def _fire_milestones(
        self, matter: Matter, trigger: MilestoneTrigger, *, arrangement: MatterFeeArrangement | None = None
    ) -> list[MatterFeeEvent]:
        arr = arrangement or await self.repo.active_arrangement(self.tenant_id, matter.id)
        if arr is None:
            return []
        raised: list[MatterFeeEvent] = []
        for ms in arr.milestones:
            if ms.trigger != trigger or ms.status != MilestoneStatus.PENDING or ms.deleted_at is not None:
                continue
            raised.append(self._fire_milestone(matter, arr, ms))
        if raised:
            await self.session.flush()
        return raised

    def _fire_milestone(self, matter: Matter, arr: MatterFeeArrangement, ms: MatterFeeMilestone) -> MatterFeeEvent:
        amount = self._milestone_amount(arr, ms) or Decimal(0)
        ms.status = MilestoneStatus.DUE
        ms.triggered_at = datetime.now(UTC)
        return self._raise_event(
            matter, arr, kind=FeeEventKind.MILESTONE, amount=amount, description=ms.label,
            occurred_on=date.today(), due_days=ms.due_days, milestone=ms,
        )

    async def _fire_dated_milestones(self, matter: Matter) -> None:
        today = date.today()
        changed = False
        for arr in matter.fee_arrangements:
            if arr.deleted_at is not None or (arr.effective_to is not None and arr.effective_to < today):
                continue
            for ms in arr.milestones:
                if (ms.trigger == MilestoneTrigger.ON_DATE and ms.status == MilestoneStatus.PENDING
                        and ms.due_on is not None and ms.due_on <= today and ms.deleted_at is None):
                    matter.fee_events.append(self._fire_milestone(matter, arr, ms))
                    changed = True
        if changed:
            await self.session.flush()

    async def trigger_milestone(self, matter_id: uuid.UUID, milestone_id: uuid.UUID) -> MatterFeeEvent:
        """Staff mark a milestone as reached (manual ones, or ahead of the automatic trigger)."""
        matter = await self._require_matter(matter_id)
        ms = await self.repo.get_milestone(self.tenant_id, matter_id, milestone_id)
        if ms is None:
            raise NotFoundError("Milestone not found.")
        if ms.status != MilestoneStatus.PENDING:
            raise ValidationError("This milestone has already fallen due or been waived.")
        arr = await self.repo.get_arrangement(self.tenant_id, matter_id, ms.arrangement_id)
        event = self._fire_milestone(matter, arr, ms)
        await self.session.flush()
        return event

    async def waive_milestone(self, matter_id: uuid.UUID, milestone_id: uuid.UUID) -> MatterFeeMilestone:
        await self._require_matter(matter_id)
        ms = await self.repo.get_milestone(self.tenant_id, matter_id, milestone_id)
        if ms is None:
            raise NotFoundError("Milestone not found.")
        if ms.status == MilestoneStatus.DUE:
            raise ValidationError("This milestone has already fallen due — waive the fee event instead.")
        ms.status = MilestoneStatus.WAIVED
        return ms

    async def _on_hearing_outcome(self, hearing: Hearing) -> None:
        """Per-hearing fees and the first-hearing milestone."""
        matter = await self._require_matter(hearing.matter_id)
        arr = await self.repo.active_arrangement(self.tenant_id, matter.id)
        if arr is None:
            return
        when = hearing.scheduled_on.date() if hearing.scheduled_on else date.today()
        if not await self.repo.hearing_event_exists(self.tenant_id, hearing.id):
            if hearing.status == HearingStatus.HELD and arr.per_hearing_fee:
                self._raise_event(
                    matter, arr, kind=FeeEventKind.HEARING, amount=Decimal(arr.per_hearing_fee),
                    description=f"Appearance on {when:%d/%m/%Y}" + (f" — {hearing.purpose}" if hearing.purpose else ""),
                    occurred_on=when, due_days=7, hearing=hearing,
                )
            elif hearing.status == HearingStatus.ADJOURNED and arr.non_effective_hearing_fee:
                self._raise_event(
                    matter, arr, kind=FeeEventKind.HEARING_NON_EFFECTIVE, amount=Decimal(arr.non_effective_hearing_fee),
                    description=f"Non-effective hearing on {when:%d/%m/%Y}" + (f" — {hearing.purpose}" if hearing.purpose else ""),
                    occurred_on=when, due_days=7, hearing=hearing,
                )
        if hearing.status == HearingStatus.HELD and await self.repo.held_hearing_count(self.tenant_id, matter.id) == 1:
            await self._fire_milestones(matter, MilestoneTrigger.ON_FIRST_HEARING, arrangement=arr)
        await self.session.flush()

    async def add_fee_event(self, matter_id: uuid.UUID, data: FeeEventCreate) -> MatterFeeEvent:
        matter = await self._require_matter(matter_id)
        arr = await self.repo.active_arrangement(self.tenant_id, matter_id)
        event = self._raise_event(
            matter, arr, kind=FeeEventKind.MANUAL, amount=data.amount, description=data.description,
            occurred_on=data.occurred_on or date.today(), due_days=data.due_days,
        )
        await self.session.flush()
        return event

    async def set_fee_event_status(
        self, matter_id: uuid.UUID, event_id: uuid.UUID, status: FeeEventStatus
    ) -> MatterFeeEvent:
        await self._require_matter(matter_id)
        event = await self.repo.get_fee_event(self.tenant_id, matter_id, event_id)
        if event is None:
            raise NotFoundError("Fee event not found.")
        if event.status == FeeEventStatus.INVOICED:
            raise ValidationError("This event is already on an invoice.")
        if status == FeeEventStatus.INVOICED:
            raise ValidationError("Invoices are raised from the billing screen, not by marking an event.")
        event.status = status
        return event

    async def fee_summary(self, matter_id: uuid.UUID) -> FeeSummary:
        matter = await self._require_matter(matter_id, detail=True)
        totals = {s: Decimal(0) for s in FeeEventStatus}
        count = 0
        currency = "INR"
        for e in matter.fee_events:
            if e.deleted_at is not None:
                continue
            totals[e.status] += Decimal(e.amount)
            currency = e.currency
            if e.status == FeeEventStatus.UNBILLED:
                count += 1
        return FeeSummary(
            unbilled_total=totals[FeeEventStatus.UNBILLED], unbilled_count=count,
            invoiced_total=totals[FeeEventStatus.INVOICED], waived_total=totals[FeeEventStatus.WAIVED],
            currency=currency,
        )


def _blank_to_none(value: str | None) -> str | None:
    return (value.strip() or None) if isinstance(value, str) else value
