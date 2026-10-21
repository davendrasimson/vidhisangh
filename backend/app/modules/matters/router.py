"""Matters (case management) HTTP endpoints — RBAC-guarded, tenant-scoped."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.core.pagination import PageParams, page_params
from app.modules.matters.models import FeeEventStatus, MatterStatus
from app.modules.matters.schemas import (
    AdvocateCreate,
    AdvocateRead,
    AdvocateUpdate,
    AuthorityCreate,
    AuthorityRead,
    ECourtsCaseRead,
    ECourtsImportRequest,
    ECourtsLookupRequest,
    FeeArrangementCreate,
    FeeArrangementRead,
    FeeArrangementUpdate,
    FeeEventCreate,
    FeeEventRead,
    FeeSummary,
    HearingCreate,
    HearingRead,
    HearingUpdate,
    MatterCreate,
    MatterDetail,
    MatterRead,
    MatterUpdate,
    MilestoneRead,
    NoteCreate,
    NoteRead,
    PartyCreate,
    PartyRead,
    PersonRead,
    TaskCreate,
    TaskRead,
    TeamHandover,
    TeamMemberCreate,
    TeamMemberRead,
    TeamMemberUpdate,
    TeamTransfer,
    TeamTransferResult,
    WorkloadRow,
    TimelineEntry,
)
from app.modules.matters.service import MatterService

router = APIRouter(prefix="/matters", tags=["Matters"])

Pagination = Annotated[PageParams, Depends(page_params)]


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> MatterService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return MatterService(session, current.id, current.tenant_id)


# ─── Matters ────────────────────────────────────────────────────────
@router.post(
    "",
    response_model=MatterDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Register a matter",
    dependencies=[require_permission("matter:create")],
)
async def create_matter(
    data: MatterCreate, current: CurrentUserDep, session: TenantSessionDep
) -> MatterDetail:
    svc = _svc(current, session)
    matter = await svc.create_matter(data)
    return await svc.to_detail(await svc.get_matter(matter.id))


@router.get(
    "",
    response_model=list[MatterRead],
    summary="List matters",
    dependencies=[require_permission("matter:read")],
)
async def list_matters(
    page: Pagination,
    current: CurrentUserDep,
    session: TenantSessionDep,
    status_filter: Annotated[MatterStatus | None, Query(alias="status")] = None,
    client_id: Annotated[uuid.UUID | None, Query()] = None,
    user_id: Annotated[uuid.UUID | None, Query(description="Matters this person is currently on the team of")] = None,
) -> list[MatterRead]:
    svc = _svc(current, session)
    matters = await svc.list_matters(status_filter, page.limit, page.offset, client_id=client_id, user_id=user_id)
    return await svc.to_read(matters)


@router.get(
    "/team/people",
    response_model=list[PersonRead],
    summary="Colleagues who can be put on a matter team",
    dependencies=[require_permission("matter:read")],
)
async def team_people(current: CurrentUserDep, session: TenantSessionDep) -> list[PersonRead]:
    return await _svc(current, session).people()


@router.get(
    "/team/workload",
    response_model=list[WorkloadRow],
    summary="Open matters and coming hearings per colleague",
    description=(
        "Every active member of the organisation with the open matters they are on now "
        "(by role, and how many they lead) and the scheduled hearings on those matters "
        "in the next 14 days. Busiest first, for deciding who takes the next brief."
    ),
    dependencies=[require_permission("matter:manage")],
)
async def team_workload(current: CurrentUserDep, session: TenantSessionDep) -> list[WorkloadRow]:
    return await _svc(current, session).workload()


@router.post(
    "/team/transfer",
    response_model=TeamTransferResult,
    summary="Move all of one person's active matters to another",
    description=(
        "For when someone leaves the firm or a practice is reorganised: every active "
        "stint of `from_user_id` on open matters (or just `matter_ids`) is ended with "
        "the reason and date given, and `to_user_id` takes the same role from that day. "
        "History is kept — nothing is overwritten."
    ),
    dependencies=[require_permission("matter:manage")],
)
async def team_transfer(data: TeamTransfer, current: CurrentUserDep, session: TenantSessionDep) -> TeamTransferResult:
    return await _svc(current, session).transfer(data)


@router.get(
    "/hearings/upcoming",
    response_model=list[HearingRead],
    summary="Upcoming hearings across matters (calendar feed)",
    dependencies=[require_permission("hearing:read")],
)
async def upcoming_hearings(
    page: Pagination, current: CurrentUserDep, session: TenantSessionDep
) -> list[HearingRead]:
    hearings = await _svc(current, session).upcoming_hearings(page.limit, page.offset)
    return [HearingRead.model_validate(h) for h in hearings]


@router.get(
    "/{matter_id}",
    response_model=MatterDetail,
    summary="Matter detail (with parties, hearings, tasks, notes)",
    dependencies=[require_permission("matter:read")],
)
async def get_matter(
    matter_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> MatterDetail:
    svc = _svc(current, session)
    return await svc.to_detail(await svc.get_matter(matter_id))


@router.get(
    "/{matter_id}/timeline",
    response_model=list[TimelineEntry],
    summary="Chronological activity timeline for a matter",
    dependencies=[require_permission("matter:read")],
)
async def matter_timeline(
    matter_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> list[TimelineEntry]:
    return await _svc(current, session).timeline(matter_id)


@router.patch(
    "/{matter_id}",
    response_model=MatterDetail,
    summary="Update a matter",
    dependencies=[require_permission("matter:update")],
)
async def update_matter(
    matter_id: uuid.UUID,
    data: MatterUpdate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> MatterDetail:
    svc = _svc(current, session)
    await svc.update_matter(matter_id, data)
    return await svc.to_detail(await svc.get_matter(matter_id))


@router.delete(
    "/{matter_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a matter",
    dependencies=[require_permission("matter:delete")],
)
async def delete_matter(
    matter_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).delete_matter(matter_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── eCourts ────────────────────────────────────────────────────────
@router.post(
    "/ecourts/lookup",
    response_model=ECourtsCaseRead,
    summary="Look up a case in eCourts by CNR, or case type / number / year",
    description=(
        "Read-only: fetches the registry record without creating anything, so the "
        "user can confirm it is the right case before filing it. Returns 503 when "
        "no eCourts provider is configured."
    ),
    dependencies=[require_permission("matter:read")],
)
async def ecourts_lookup(
    data: ECourtsLookupRequest, current: CurrentUserDep, session: TenantSessionDep
) -> ECourtsCaseRead:
    case = await _svc(current, session).ecourts_lookup(data)
    return ECourtsCaseRead.model_validate(case, from_attributes=True)


@router.post(
    "/ecourts/import",
    response_model=MatterDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a matter from an eCourts case",
    description=(
        "Fetches the case and files it, splitting registry parties and advocates "
        "into our side and the opponent's using `our_side_role`."
    ),
    dependencies=[require_permission("matter:create")],
)
async def ecourts_import(
    data: ECourtsImportRequest, current: CurrentUserDep, session: TenantSessionDep
) -> MatterDetail:
    svc = _svc(current, session)
    matter = await svc.import_from_ecourts(data)
    return await svc.to_detail(await svc.get_matter(matter.id))


@router.post(
    "/{matter_id}/ecourts/refresh",
    response_model=MatterDetail,
    summary="Re-sync a matter's registry data from eCourts",
    description=(
        "Overwrites only registry-owned fields (court, numbers, hearing dates, "
        "disposal). The firm's own data — title, client, assignment, notes — is "
        "left untouched."
    ),
    dependencies=[require_permission("matter:update")],
)
async def ecourts_refresh(
    matter_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> MatterDetail:
    svc = _svc(current, session)
    await svc.refresh_from_ecourts(matter_id)
    return await svc.to_detail(await svc.get_matter(matter_id))


# ─── Advocates on record ────────────────────────────────────────────
@router.post(
    "/{matter_id}/advocates",
    response_model=AdvocateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add counsel (ours or opposing)",
    dependencies=[require_permission("matter:update")],
)
async def add_advocate(
    matter_id: uuid.UUID, data: AdvocateCreate,
    current: CurrentUserDep, session: TenantSessionDep,
) -> AdvocateRead:
    advocate = await _svc(current, session).add_advocate(matter_id, data)
    return AdvocateRead.model_validate(advocate)


@router.patch(
    "/{matter_id}/advocates/{advocate_id}",
    response_model=AdvocateRead,
    summary="Update counsel",
    dependencies=[require_permission("matter:update")],
)
async def update_advocate(
    matter_id: uuid.UUID, advocate_id: uuid.UUID, data: AdvocateUpdate,
    current: CurrentUserDep, session: TenantSessionDep,
) -> AdvocateRead:
    advocate = await _svc(current, session).update_advocate(matter_id, advocate_id, data)
    return AdvocateRead.model_validate(advocate)


@router.delete(
    "/{matter_id}/advocates/{advocate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove counsel",
    dependencies=[require_permission("matter:update")],
)
async def remove_advocate(
    matter_id: uuid.UUID, advocate_id: uuid.UUID,
    current: CurrentUserDep, session: TenantSessionDep,
) -> Response:
    await _svc(current, session).remove_advocate(matter_id, advocate_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/advocates/opposing/{name}/history",
    response_model=list[MatterRead],
    summary="Other matters where this advocate appeared against us",
    dependencies=[require_permission("matter:read")],
)
async def opposing_counsel_history(
    name: str, current: CurrentUserDep, session: TenantSessionDep
) -> list[MatterRead]:
    matters = await _svc(current, session).opposing_counsel_history(name)
    return [MatterRead.model_validate(m) for m in matters]


# ─── Parties ────────────────────────────────────────────────────────
@router.post(
    "/{matter_id}/parties",
    response_model=PartyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a party",
    dependencies=[require_permission("matter:update")],
)
async def add_party(
    matter_id: uuid.UUID,
    data: PartyCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> PartyRead:
    return PartyRead.model_validate(await _svc(current, session).add_party(matter_id, data))


# ─── Hearings ───────────────────────────────────────────────────────
@router.post(
    "/{matter_id}/hearings",
    response_model=HearingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a hearing",
    dependencies=[require_permission("hearing:create")],
)
async def add_hearing(
    matter_id: uuid.UUID,
    data: HearingCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> HearingRead:
    return HearingRead.model_validate(await _svc(current, session).add_hearing(matter_id, data))


@router.patch(
    "/hearings/{hearing_id}",
    response_model=HearingRead,
    summary="Update a hearing (outcome, next date, status)",
    dependencies=[require_permission("hearing:update")],
)
async def update_hearing(
    hearing_id: uuid.UUID,
    data: HearingUpdate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> HearingRead:
    return HearingRead.model_validate(await _svc(current, session).update_hearing(hearing_id, data))


# ─── Tasks ──────────────────────────────────────────────────────────
@router.post(
    "/{matter_id}/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a task / deadline",
    dependencies=[require_permission("task:create")],
)
async def add_task(
    matter_id: uuid.UUID,
    data: TaskCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> TaskRead:
    return TaskRead.model_validate(await _svc(current, session).add_task(matter_id, data))


@router.post(
    "/tasks/{task_id}/done",
    response_model=TaskRead,
    summary="Mark a task done / reopen",
    dependencies=[require_permission("task:update")],
)
async def set_task_done(
    task_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    done: Annotated[bool, Query()] = True,
) -> TaskRead:
    return TaskRead.model_validate(await _svc(current, session).set_task_done(task_id, done))


# ─── Notes ──────────────────────────────────────────────────────────
@router.post(
    "/{matter_id}/notes",
    response_model=NoteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a note",
    dependencies=[require_permission("matter:update")],
)
async def add_note(
    matter_id: uuid.UUID,
    data: NoteCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> NoteRead:
    return NoteRead.model_validate(await _svc(current, session).add_note(matter_id, data))


# ─── Team ───────────────────────────────────────────────────────────
async def _team_rows(svc: MatterService, matter_id: uuid.UUID, ids: list[uuid.UUID]) -> list[TeamMemberRead]:
    """The named team rows, resolved with names/rates, in the order asked for."""
    detail = await svc.to_detail(await svc.get_matter(matter_id))
    by_id = {t.id: t for t in detail.team}
    return [by_id[i] for i in ids if i in by_id]


@router.post(
    "/{matter_id}/team",
    response_model=TeamMemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="Put a colleague on the matter team",
    description="Adding a `lead_counsel` ends the current lead's stint (reason: reassigned) — one lead at a time.",
    dependencies=[require_permission("matter:update")],
)
async def add_team_member(
    matter_id: uuid.UUID, data: TeamMemberCreate, current: CurrentUserDep, session: TenantSessionDep
) -> TeamMemberRead:
    svc = _svc(current, session)
    member = await svc.add_team_member(matter_id, data)
    return (await _team_rows(svc, matter_id, [member.id]))[0]


@router.patch(
    "/{matter_id}/team/{member_id}",
    response_model=TeamMemberRead,
    summary="Change a team member's role, dates or rate override",
    dependencies=[require_permission("matter:update")],
)
async def update_team_member(
    matter_id: uuid.UUID, member_id: uuid.UUID, data: TeamMemberUpdate,
    current: CurrentUserDep, session: TenantSessionDep,
) -> TeamMemberRead:
    svc = _svc(current, session)
    member = await svc.update_team_member(matter_id, member_id, data)
    return (await _team_rows(svc, matter_id, [member.id]))[0]


@router.post(
    "/{matter_id}/team/{member_id}/handover",
    response_model=list[TeamMemberRead],
    summary="End a stint and hand the role to a successor",
    description=(
        "Mid-matter change: the stint ends on `effective_from` with a reason "
        "(reassigned, left the firm, workload, client request, conflict…) and, when a "
        "`successor_user_id` is given, the successor starts the same day in the same role. "
        "Returns the ended row and the new one."
    ),
    dependencies=[require_permission("matter:update")],
)
async def handover(
    matter_id: uuid.UUID, member_id: uuid.UUID, data: TeamHandover,
    current: CurrentUserDep, session: TenantSessionDep,
) -> list[TeamMemberRead]:
    svc = _svc(current, session)
    rows = await svc.handover(matter_id, member_id, data)
    return await _team_rows(svc, matter_id, [r.id for r in rows])


@router.delete(
    "/{matter_id}/team/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a team row added by mistake (use hand-over to end a real stint)",
    dependencies=[require_permission("matter:update")],
)
async def remove_team_member(
    matter_id: uuid.UUID, member_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).remove_team_member(matter_id, member_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Fees ───────────────────────────────────────────────────────────
@router.post(
    "/{matter_id}/fees",
    response_model=FeeArrangementRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record how the client pays for this matter",
    description=(
        "Fixed fee, per hearing, hourly, retainer, milestone-based or a hybrid — with "
        "milestones (advance, on filing, first hearing, evidence, arguments, judgment, "
        "closure, a date, or manual). An existing open arrangement is closed the day before "
        "the new one starts, so renegotiations keep their history. The advance milestone and "
        "the first retainer period raise fee events immediately."
    ),
    dependencies=[require_permission("matter:update")],
)
async def add_fee_arrangement(
    matter_id: uuid.UUID, data: FeeArrangementCreate, current: CurrentUserDep, session: TenantSessionDep
) -> FeeArrangementRead:
    svc = _svc(current, session)
    arr = await svc.add_arrangement(matter_id, data)
    return svc._arrangement_read(await svc.repo.get_arrangement(current.tenant_id, matter_id, arr.id))  # noqa: SLF001


@router.patch(
    "/{matter_id}/fees/{arrangement_id}",
    response_model=FeeArrangementRead,
    summary="Edit terms, cap, flags or end date of an arrangement",
    dependencies=[require_permission("matter:update")],
)
async def update_fee_arrangement(
    matter_id: uuid.UUID, arrangement_id: uuid.UUID, data: FeeArrangementUpdate,
    current: CurrentUserDep, session: TenantSessionDep,
) -> FeeArrangementRead:
    svc = _svc(current, session)
    arr = await svc.update_arrangement(matter_id, arrangement_id, data)
    return svc._arrangement_read(arr)  # noqa: SLF001


@router.delete(
    "/{matter_id}/fees/{arrangement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a fee arrangement",
    dependencies=[require_permission("matter:update")],
)
async def delete_fee_arrangement(
    matter_id: uuid.UUID, arrangement_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).delete_arrangement(matter_id, arrangement_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{matter_id}/fees/milestones/{milestone_id}/trigger",
    response_model=FeeEventRead,
    summary="Mark a milestone reached — raises its fee event",
    dependencies=[require_permission("matter:update")],
)
async def trigger_milestone(
    matter_id: uuid.UUID, milestone_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> FeeEventRead:
    return FeeEventRead.model_validate(await _svc(current, session).trigger_milestone(matter_id, milestone_id))


@router.post(
    "/{matter_id}/fees/milestones/{milestone_id}/waive",
    response_model=MilestoneRead,
    summary="Waive a pending milestone",
    dependencies=[require_permission("matter:update")],
)
async def waive_milestone(
    matter_id: uuid.UUID, milestone_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> MilestoneRead:
    return MilestoneRead.model_validate(await _svc(current, session).waive_milestone(matter_id, milestone_id))


@router.get(
    "/{matter_id}/fees/summary",
    response_model=FeeSummary,
    summary="Unbilled / invoiced / waived totals for the matter",
    dependencies=[require_permission("matter:read")],
)
async def fee_summary(matter_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep) -> FeeSummary:
    return await _svc(current, session).fee_summary(matter_id)


@router.post(
    "/{matter_id}/fees/events",
    response_model=FeeEventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a manual billable event (opinion, conference, drafting…)",
    dependencies=[require_permission("matter:update")],
)
async def add_fee_event(
    matter_id: uuid.UUID, data: FeeEventCreate, current: CurrentUserDep, session: TenantSessionDep
) -> FeeEventRead:
    return FeeEventRead.model_validate(await _svc(current, session).add_fee_event(matter_id, data))


@router.post(
    "/{matter_id}/fees/events/{event_id}/status",
    response_model=FeeEventRead,
    summary="Waive an unbilled fee event, or put a waived one back",
    dependencies=[require_permission("matter:update")],
)
async def set_fee_event_status(
    matter_id: uuid.UUID, event_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep,
    new_status: Annotated[FeeEventStatus, Query(alias="status")] = FeeEventStatus.WAIVED,
) -> FeeEventRead:
    return FeeEventRead.model_validate(
        await _svc(current, session).set_fee_event_status(matter_id, event_id, new_status)
    )


@router.post(
    "/{matter_id}/authorities", response_model=AuthorityRead,
    status_code=status.HTTP_201_CREATED, summary="Pin a source-linked authority to a matter",
    dependencies=[require_permission("matter:update"), require_permission("research:use")],
)
async def add_authority(
    matter_id: uuid.UUID, data: AuthorityCreate,
    current: CurrentUserDep, session: TenantSessionDep,
) -> AuthorityRead:
    return AuthorityRead.model_validate(await _svc(current, session).add_authority(matter_id, data))


@router.delete(
    "/{matter_id}/authorities/{authority_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("matter:update")],
)
async def remove_authority(
    matter_id: uuid.UUID, authority_id: uuid.UUID,
    current: CurrentUserDep, session: TenantSessionDep,
) -> Response:
    await _svc(current, session).remove_authority(matter_id, authority_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
