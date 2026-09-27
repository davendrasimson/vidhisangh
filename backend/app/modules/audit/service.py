"""Audit service.

``record_audit`` is a module-level helper other modules call (within their own
transaction) to append an audit event. ``AuditService`` backs the log viewer.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditEvent
from app.modules.audit.repository import AuditRepository


def record_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    action: str,
    summary: str,
    actor_id: uuid.UUID | None = None,
    actor_label: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    meta: dict | None = None,
) -> None:
    """Append an audit event to the caller's transaction."""
    session.add(
        AuditEvent(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_label=actor_label,
            action=action,
            summary=summary,
            entity_type=entity_type,
            entity_id=entity_id,
            meta=meta,
        )
    )


class AuditService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.repo = AuditRepository(session)

    async def list(self, *, action: str | None, limit: int, offset: int) -> list[AuditEvent]:
        return await self.repo.list(self.tenant_id, action=action, limit=limit, offset=offset)
