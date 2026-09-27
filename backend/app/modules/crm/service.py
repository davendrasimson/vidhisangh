"""CRM service — leads, activities, pipeline, convert-to-matter, analytics."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.crm.models import (
    ActivityType,
    Lead,
    LeadActivity,
    LeadSource,
    LeadStatus,
)
from app.modules.crm.repository import CrmRepository
from app.modules.crm.schemas import (
    ActivityCreate,
    LeadCreate,
    LeadRead,
    LeadUpdate,
    PipelineColumn,
    SourceStat,
)
from app.modules.matters.schemas import MatterCreate
from app.modules.matters.service import MatterService
from app.modules.clients.models import ClientKind
from app.modules.clients.repository import ClientRepository
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService


class CrmService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.repo = CrmRepository(session)

    async def _require_lead(self, lead_id: uuid.UUID, *, detail: bool = False) -> Lead:
        lead = await self.repo.get_lead(self.tenant_id, lead_id, detail=detail)
        if lead is None:
            raise NotFoundError("Lead not found.")
        return lead

    # ── Leads ───────────────────────────────────────────────────────
    async def create_lead(self, data: LeadCreate) -> Lead:
        lead = Lead(
            tenant_id=self.tenant_id,
            name=data.name,
            email=data.email,
            phone=data.phone,
            source=data.source,
            practice_area=data.practice_area,
            notes=data.notes,
            estimated_value=data.estimated_value,
            referred_by=data.referred_by,
            assigned_to=data.assigned_to,
            created_by=self.user_id,
        )
        self.repo.add(lead)
        await self.session.flush()
        return lead

    async def list_leads(
        self, status: LeadStatus | None, source: LeadSource | None, limit: int, offset: int
    ) -> list[Lead]:
        return await self.repo.list_leads(
            self.tenant_id, status=status, source=source, limit=limit, offset=offset
        )

    async def get_lead(self, lead_id: uuid.UUID) -> Lead:
        return await self._require_lead(lead_id, detail=True)

    async def update_lead(self, lead_id: uuid.UUID, data: LeadUpdate) -> Lead:
        lead = await self._require_lead(lead_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(lead, field, value)
        return lead

    async def delete_lead(self, lead_id: uuid.UUID) -> None:
        lead = await self._require_lead(lead_id)
        lead.deleted_at = datetime.now(UTC)

    # ── Activities ──────────────────────────────────────────────────
    async def add_activity(self, lead_id: uuid.UUID, data: ActivityCreate) -> LeadActivity:
        await self._require_lead(lead_id)
        activity = LeadActivity(
            tenant_id=self.tenant_id,
            lead_id=lead_id,
            type=data.type,
            subject=data.subject,
            body=data.body,
            due_on=data.due_on,
            created_by=self.user_id,
        )
        self.repo.add(activity)
        await self.session.flush()
        return activity

    async def complete_activity(self, activity_id: uuid.UUID, done: bool) -> LeadActivity:
        activity = await self.repo.get_activity(self.tenant_id, activity_id)
        if activity is None:
            raise NotFoundError("Activity not found.")
        activity.completed = done
        activity.completed_at = datetime.now(UTC) if done else None
        return activity

    # ── Convert to matter ───────────────────────────────────────────
    async def convert_to_matter(self, lead_id: uuid.UUID) -> uuid.UUID:
        lead = await self._require_lead(lead_id)
        if lead.converted_matter_id is not None:
            raise ConflictError("This lead has already been converted.")
        client = None
        clients = ClientRepository(self.session)
        if lead.client_id is not None:
            client = await clients.get(self.tenant_id, lead.client_id)
        if client is None:
            matches = await clients.list(self.tenant_id, q=lead.email or lead.phone or lead.name, limit=20)
            client = next((c for c in matches if (lead.email and c.email == lead.email) or (lead.phone and lead.phone in (c.mobile, c.phone))), None)
        if client is None:
            client = await ClientService(self.session, self.user_id, self.tenant_id).create(ClientCreate(
                kind=ClientKind.INDIVIDUAL, display_name=lead.name, email=lead.email,
                mobile=lead.phone, notes=lead.notes, tags=["CRM lead", str(lead.source)],
            ))
        lead.client_id = client.id
        matter = await MatterService(self.session, self.user_id, self.tenant_id).create_matter(
            MatterCreate(
                title=f"{lead.name}"
                + (f" — {lead.practice_area}" if lead.practice_area else ""),
                client_id=client.id,
                client_name=client.display_name,
                practice_area=lead.practice_area,
                assigned_to=lead.assigned_to,
            )
        )
        lead.converted_matter_id = matter.id
        lead.status = LeadStatus.WON
        return matter.id

    # ── Pipeline & analytics ────────────────────────────────────────
    async def pipeline(self) -> list[PipelineColumn]:
        grouped: dict[LeadStatus, list[Lead]] = defaultdict(list)
        for lead in await self.repo.all_leads(self.tenant_id):
            grouped[lead.status].append(lead)
        columns: list[PipelineColumn] = []
        for status in LeadStatus:
            leads = grouped.get(status, [])
            value = sum((lead.estimated_value or Decimal(0)) for lead in leads)
            columns.append(
                PipelineColumn(
                    status=status,
                    count=len(leads),
                    value=Decimal(value),
                    leads=[LeadRead.model_validate(lead) for lead in leads],
                )
            )
        return columns

    async def source_analytics(self) -> list[SourceStat]:
        return [
            SourceStat(source=source, total=total, won=won)
            for source, total, won in await self.repo.source_stats(self.tenant_id)
        ]
