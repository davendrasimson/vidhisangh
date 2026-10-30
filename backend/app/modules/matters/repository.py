"""Data-access layer for matters. Queries filter by ``tenant_id`` explicitly
(belt-and-suspenders alongside RLS, so isolation holds under the SQLite tests
too)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.identity.models import User
from app.modules.matters.models import (
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
    MatterStatus,
    MatterTask,
    MatterTeamMember,
    PartySide,
    TaskStatus,
)


class MatterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def delete(self, obj: object) -> None:
        await self.session.delete(obj)

    async def count(self, tenant_id: uuid.UUID) -> int:
        res = await self.session.execute(
            select(func.count()).select_from(Matter).where(Matter.tenant_id == tenant_id)
        )
        return int(res.scalar_one())

    async def get(
        self, tenant_id: uuid.UUID, matter_id: uuid.UUID, *, detail: bool = False
    ) -> Matter | None:
        stmt = select(Matter).where(
            Matter.id == matter_id,
            Matter.tenant_id == tenant_id,
            Matter.deleted_at.is_(None),
        )
        if detail:
            stmt = stmt.options(
                selectinload(Matter.parties),
                selectinload(Matter.advocates),
                selectinload(Matter.hearings),
                selectinload(Matter.tasks),
                selectinload(Matter.notes),
                selectinload(Matter.team),
                selectinload(Matter.fee_arrangements).selectinload(MatterFeeArrangement.milestones),
                selectinload(Matter.fee_events),
                selectinload(Matter.authorities),
            )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list(
        self,
        tenant_id: uuid.UUID,
        status: MatterStatus | None,
        limit: int,
        offset: int,
        *,
        client_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[Matter]:
        stmt = select(Matter).where(
            Matter.tenant_id == tenant_id, Matter.deleted_at.is_(None)
        )
        if status is not None:
            stmt = stmt.where(Matter.status == status)
        if client_id is not None:
            stmt = stmt.where(Matter.client_id == client_id)
        if user_id is not None:
            # Matters this person is (currently) on the team of.
            on_team = select(MatterTeamMember.matter_id).where(
                MatterTeamMember.tenant_id == tenant_id,
                MatterTeamMember.user_id == user_id,
                MatterTeamMember.to_date.is_(None),
                MatterTeamMember.deleted_at.is_(None),
            )
            stmt = stmt.where(Matter.id.in_(on_team))
        res = await self.session.execute(
            stmt.order_by(Matter.created_at.desc()).limit(limit).offset(offset)
        )
        return list(res.scalars().all())

    # ── People (for names on team rows / lead counsel) ─────────────
    async def people(self, tenant_id: uuid.UUID, *, active_only: bool = True) -> list[User]:
        stmt = select(User).where(User.tenant_id == tenant_id, User.deleted_at.is_(None))
        if active_only:
            stmt = stmt.where(User.is_active.is_(True))
        res = await self.session.execute(stmt.order_by(User.full_name))
        return list(res.scalars().all())

    async def names(self, tenant_id: uuid.UUID, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
        if not user_ids:
            return {}
        res = await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.id.in_(user_ids))
        )
        return {u.id: u for u in res.scalars().all()}

    # ── Team ───────────────────────────────────────────────────────
    async def get_team_member(
        self, tenant_id: uuid.UUID, matter_id: uuid.UUID, member_id: uuid.UUID
    ) -> MatterTeamMember | None:
        res = await self.session.execute(
            select(MatterTeamMember).where(
                MatterTeamMember.id == member_id,
                MatterTeamMember.matter_id == matter_id,
                MatterTeamMember.tenant_id == tenant_id,
                MatterTeamMember.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def active_team(self, tenant_id: uuid.UUID, matter_id: uuid.UUID) -> list[MatterTeamMember]:
        res = await self.session.execute(
            select(MatterTeamMember).where(
                MatterTeamMember.tenant_id == tenant_id,
                MatterTeamMember.matter_id == matter_id,
                MatterTeamMember.to_date.is_(None),
                MatterTeamMember.deleted_at.is_(None),
            ).order_by(MatterTeamMember.from_date)
        )
        return list(res.scalars().all())

    async def active_stints_of(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, matter_ids: list[uuid.UUID] | None
    ) -> list[tuple[MatterTeamMember, Matter]]:
        """Every open matter this person is currently on, for a bulk transfer."""
        stmt = (
            select(MatterTeamMember, Matter)
            .join(Matter, Matter.id == MatterTeamMember.matter_id)
            .where(
                MatterTeamMember.tenant_id == tenant_id,
                MatterTeamMember.user_id == user_id,
                MatterTeamMember.to_date.is_(None),
                MatterTeamMember.deleted_at.is_(None),
                Matter.deleted_at.is_(None),
                Matter.status != MatterStatus.CLOSED,
            )
        )
        if matter_ids:
            stmt = stmt.where(Matter.id.in_(matter_ids))
        res = await self.session.execute(stmt.order_by(Matter.matter_number))
        return [(m, mt) for m, mt in res.all()]

    async def stints_with_sides(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, exclude_matter: uuid.UUID
    ) -> list[tuple[Matter, bool, list[MatterParty]]]:
        """Every other matter this person is or was on: (matter, still on it, its parties)."""
        res = await self.session.execute(
            select(Matter, MatterTeamMember.to_date)
            .join(MatterTeamMember, MatterTeamMember.matter_id == Matter.id)
            .where(
                MatterTeamMember.tenant_id == tenant_id,
                MatterTeamMember.user_id == user_id,
                MatterTeamMember.deleted_at.is_(None),
                Matter.deleted_at.is_(None),
                Matter.id != exclude_matter,
            )
        )
        current: dict[uuid.UUID, tuple[Matter, bool]] = {}
        for matter, to_date in res.all():
            prev = current.get(matter.id)
            current[matter.id] = (matter, (prev[1] if prev else False) or to_date is None)
        if not current:
            return []
        parties = await self.session.execute(
            select(MatterParty).where(
                MatterParty.tenant_id == tenant_id,
                MatterParty.matter_id.in_(current.keys()),
                MatterParty.deleted_at.is_(None),
            )
        )
        by_matter: dict[uuid.UUID, list[MatterParty]] = {}
        for p in parties.scalars().all():
            by_matter.setdefault(p.matter_id, []).append(p)
        return [(m, now, by_matter.get(mid, [])) for mid, (m, now) in current.items()]

    # ── Board ──────────────────────────────────────────────────────
    async def board_matters(
        self, tenant_id: uuid.UUID, *, user_id: uuid.UUID | None = None, limit: int = 500
    ) -> list[Matter]:
        """Every matter that is not closed; optionally only one person's."""
        stmt = select(Matter).where(
            Matter.tenant_id == tenant_id, Matter.deleted_at.is_(None), Matter.status != MatterStatus.CLOSED
        )
        if user_id is not None:
            on_team = select(MatterTeamMember.matter_id).where(
                MatterTeamMember.tenant_id == tenant_id,
                MatterTeamMember.user_id == user_id,
                MatterTeamMember.to_date.is_(None),
                MatterTeamMember.deleted_at.is_(None),
            )
            stmt = stmt.where(
                (Matter.id.in_(on_team)) | (Matter.lead_counsel_id == user_id) | (Matter.assigned_to == user_id)
            )
        res = await self.session.execute(
            stmt.order_by(Matter.next_hearing_date.asc().nulls_last(), Matter.created_at.desc()).limit(limit)
        )
        return list(res.scalars().all())

    async def next_hearings(
        self, tenant_id: uuid.UUID, matter_ids: set[uuid.UUID], start: datetime
    ) -> dict[uuid.UUID, Hearing]:
        """The earliest scheduled hearing on or after ``start`` for each matter."""
        if not matter_ids:
            return {}
        res = await self.session.execute(
            select(Hearing)
            .where(
                Hearing.tenant_id == tenant_id,
                Hearing.matter_id.in_(matter_ids),
                Hearing.deleted_at.is_(None),
                Hearing.status == HearingStatus.SCHEDULED,
                Hearing.scheduled_on >= start,
            )
            .order_by(Hearing.scheduled_on.asc())
        )
        out: dict[uuid.UUID, Hearing] = {}
        for h in res.scalars().all():
            out.setdefault(h.matter_id, h)
        return out

    async def open_tasks(self, tenant_id: uuid.UUID, matter_ids: set[uuid.UUID]) -> dict[uuid.UUID, list[MatterTask]]:
        """Open tasks per matter, earliest due first (undated last)."""
        if not matter_ids:
            return {}
        res = await self.session.execute(
            select(MatterTask)
            .where(
                MatterTask.tenant_id == tenant_id,
                MatterTask.matter_id.in_(matter_ids),
                MatterTask.deleted_at.is_(None),
                MatterTask.status == TaskStatus.OPEN,
            )
            .order_by(MatterTask.due_on.asc().nulls_last(), MatterTask.created_at.asc())
        )
        out: dict[uuid.UUID, list[MatterTask]] = {}
        for t in res.scalars().all():
            out.setdefault(t.matter_id, []).append(t)
        return out

    async def last_activity(self, tenant_id: uuid.UUID, matter_ids: set[uuid.UUID]) -> dict[uuid.UUID, datetime]:
        """When each matter's hearings, tasks or notes were last touched."""
        if not matter_ids:
            return {}
        out: dict[uuid.UUID, datetime] = {}
        for model in (Hearing, MatterTask, MatterNote):
            res = await self.session.execute(
                select(model.matter_id, func.max(model.updated_at))
                .where(model.tenant_id == tenant_id, model.matter_id.in_(matter_ids), model.deleted_at.is_(None))
                .group_by(model.matter_id)
            )
            for matter_id, latest in res.all():
                if latest is None:
                    continue
                if isinstance(latest, str):  # SQLite returns max() of a datetime column as text
                    latest = datetime.fromisoformat(latest)
                if latest.tzinfo is None:
                    latest = latest.replace(tzinfo=UTC)
                if matter_id not in out or latest > out[matter_id]:
                    out[matter_id] = latest
        return out

    async def open_stints(self, tenant_id: uuid.UUID) -> list[tuple[uuid.UUID, str, uuid.UUID]]:
        """(user, role, matter) for every current stint on a matter that is not closed."""
        res = await self.session.execute(
            select(MatterTeamMember.user_id, MatterTeamMember.role, MatterTeamMember.matter_id)
            .join(Matter, Matter.id == MatterTeamMember.matter_id)
            .where(
                MatterTeamMember.tenant_id == tenant_id,
                MatterTeamMember.to_date.is_(None),
                MatterTeamMember.deleted_at.is_(None),
                Matter.deleted_at.is_(None),
                Matter.status != MatterStatus.CLOSED,
            )
        )
        return [(u, r, m) for u, r, m in res.all()]

    async def hearings_per_matter(
        self, tenant_id: uuid.UUID, matter_ids: set[uuid.UUID], start: datetime, end: datetime
    ) -> dict[uuid.UUID, int]:
        if not matter_ids:
            return {}
        res = await self.session.execute(
            select(Hearing.matter_id, func.count())
            .where(
                Hearing.tenant_id == tenant_id,
                Hearing.matter_id.in_(matter_ids),
                Hearing.deleted_at.is_(None),
                Hearing.status == HearingStatus.SCHEDULED,
                Hearing.scheduled_on >= start,
                Hearing.scheduled_on < end,
            )
            .group_by(Hearing.matter_id)
        )
        return {m: n for m, n in res.all()}

    # ── Fees ───────────────────────────────────────────────────────
    async def get_arrangement(
        self, tenant_id: uuid.UUID, matter_id: uuid.UUID, arrangement_id: uuid.UUID
    ) -> MatterFeeArrangement | None:
        res = await self.session.execute(
            select(MatterFeeArrangement)
            .options(selectinload(MatterFeeArrangement.milestones))
            .where(
                MatterFeeArrangement.id == arrangement_id,
                MatterFeeArrangement.matter_id == matter_id,
                MatterFeeArrangement.tenant_id == tenant_id,
                MatterFeeArrangement.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def active_arrangement(self, tenant_id: uuid.UUID, matter_id: uuid.UUID) -> MatterFeeArrangement | None:
        res = await self.session.execute(
            select(MatterFeeArrangement)
            .options(selectinload(MatterFeeArrangement.milestones))
            .where(
                MatterFeeArrangement.matter_id == matter_id,
                MatterFeeArrangement.tenant_id == tenant_id,
                MatterFeeArrangement.deleted_at.is_(None),
                MatterFeeArrangement.effective_to.is_(None),
            )
            .order_by(MatterFeeArrangement.effective_from.desc())
        )
        return res.scalars().first()

    async def get_milestone(
        self, tenant_id: uuid.UUID, matter_id: uuid.UUID, milestone_id: uuid.UUID
    ) -> MatterFeeMilestone | None:
        res = await self.session.execute(
            select(MatterFeeMilestone).where(
                MatterFeeMilestone.id == milestone_id,
                MatterFeeMilestone.matter_id == matter_id,
                MatterFeeMilestone.tenant_id == tenant_id,
                MatterFeeMilestone.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def get_fee_event(
        self, tenant_id: uuid.UUID, matter_id: uuid.UUID, event_id: uuid.UUID
    ) -> MatterFeeEvent | None:
        res = await self.session.execute(
            select(MatterFeeEvent).where(
                MatterFeeEvent.id == event_id,
                MatterFeeEvent.matter_id == matter_id,
                MatterFeeEvent.tenant_id == tenant_id,
                MatterFeeEvent.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def get_authority(self, tenant_id: uuid.UUID, matter_id: uuid.UUID, authority_id: uuid.UUID) -> MatterAuthority | None:
        return (await self.session.execute(select(MatterAuthority).where(
            MatterAuthority.id == authority_id, MatterAuthority.matter_id == matter_id,
            MatterAuthority.tenant_id == tenant_id, MatterAuthority.deleted_at.is_(None),
        ))).scalar_one_or_none()

    async def held_hearing_count(self, tenant_id: uuid.UUID, matter_id: uuid.UUID) -> int:
        res = await self.session.execute(
            select(func.count()).select_from(Hearing).where(
                Hearing.tenant_id == tenant_id, Hearing.matter_id == matter_id,
                Hearing.status == "held", Hearing.deleted_at.is_(None),
            )
        )
        return int(res.scalar_one())

    async def hearing_event_exists(self, tenant_id: uuid.UUID, hearing_id: uuid.UUID) -> bool:
        res = await self.session.execute(
            select(func.count()).select_from(MatterFeeEvent).where(
                MatterFeeEvent.tenant_id == tenant_id, MatterFeeEvent.hearing_id == hearing_id,
                MatterFeeEvent.deleted_at.is_(None),
            )
        )
        return int(res.scalar_one()) > 0

    async def get_by_cnr(self, tenant_id: uuid.UUID, cnr: str) -> Matter | None:
        """A matter already filed for this CNR — used to refuse duplicate imports."""
        res = await self.session.execute(
            select(Matter).where(
                Matter.tenant_id == tenant_id,
                Matter.cnr_number == cnr,
                Matter.deleted_at.is_(None),
            )
        )
        return res.scalars().first()

    async def get_advocate(
        self, tenant_id: uuid.UUID, matter_id: uuid.UUID, advocate_id: uuid.UUID
    ) -> MatterAdvocate | None:
        res = await self.session.execute(
            select(MatterAdvocate).where(
                MatterAdvocate.id == advocate_id,
                MatterAdvocate.matter_id == matter_id,
                MatterAdvocate.tenant_id == tenant_id,
                MatterAdvocate.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def matters_with_opposing_advocate(
        self, tenant_id: uuid.UUID, name: str
    ) -> list[Matter]:
        """Every matter where this advocate appeared against us.

        Lets a user see what they are walking into before a hearing.
        """
        res = await self.session.execute(
            select(Matter)
            .join(MatterAdvocate, MatterAdvocate.matter_id == Matter.id)
            .where(
                Matter.tenant_id == tenant_id,
                Matter.deleted_at.is_(None),
                MatterAdvocate.deleted_at.is_(None),
                MatterAdvocate.side == PartySide.OPPOSING,
                func.lower(MatterAdvocate.name) == name.strip().lower(),
            )
            .order_by(Matter.created_at.desc())
            .limit(50)
        )
        return list(res.scalars().unique().all())

    async def get_hearing(
        self, tenant_id: uuid.UUID, hearing_id: uuid.UUID
    ) -> Hearing | None:
        res = await self.session.execute(
            select(Hearing).where(
                Hearing.id == hearing_id, Hearing.tenant_id == tenant_id
            )
        )
        return res.scalar_one_or_none()

    async def get_task(self, tenant_id: uuid.UUID, task_id: uuid.UUID) -> MatterTask | None:
        res = await self.session.execute(
            select(MatterTask).where(
                MatterTask.id == task_id, MatterTask.tenant_id == tenant_id
            )
        )
        return res.scalar_one_or_none()

    async def matter_hearings(self, tenant_id: uuid.UUID, matter_id: uuid.UUID) -> list[Hearing]:
        res = await self.session.execute(
            select(Hearing).where(
                Hearing.tenant_id == tenant_id, Hearing.matter_id == matter_id, Hearing.deleted_at.is_(None)
            )
        )
        return list(res.scalars().all())

    async def upcoming_hearings(
        self, tenant_id: uuid.UUID, limit: int, offset: int
    ) -> list[Hearing]:
        res = await self.session.execute(
            select(Hearing)
            .where(Hearing.tenant_id == tenant_id, Hearing.deleted_at.is_(None))
            .order_by(Hearing.scheduled_on.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())
