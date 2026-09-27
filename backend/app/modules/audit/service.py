"""Audit service.

``record_audit`` is a module-level helper other modules call (within their own
transaction) to append an audit event. ``AuditService`` backs the log viewer.

Hash chain (audit A-20)
-----------------------
``record_audit`` stays synchronous (it only stages the row), so the chain is
closed at flush time: a ``before_flush`` listener looks up the tenant's latest
``entry_hash``, sets ``prev_hash`` and computes
``entry_hash = sha256(prev_hash + canonical JSON of the row)``. Rows staged in
the same flush chain onto each other in order. ``verify_chain`` recomputes the
chain for a tenant and reports the first broken link, if any.
"""

from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent
from app.modules.audit.repository import AuditRepository

GENESIS_HASH = "0" * 64


def canonical_content(e: AuditEvent) -> str:
    """Deterministic serialisation of the fields that are hashed (no timestamps:
    ``created_at`` is a server default and unknown before the INSERT)."""
    return json.dumps(
        {
            "id": str(e.id),
            "tenant_id": str(e.tenant_id),
            "actor_id": str(e.actor_id) if e.actor_id else None,
            "actor_label": e.actor_label,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "summary": e.summary,
            "meta": e.meta,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def compute_entry_hash(prev_hash: str, e: AuditEvent) -> str:
    return hashlib.sha256((prev_hash + canonical_content(e)).encode()).hexdigest()


def _latest_hash(session: Session, tenant_id: uuid.UUID) -> str:
    """The chain tip: the row whose ``entry_hash`` no other row references as
    ``prev_hash``. Timestamps cannot be used — every row written in one
    transaction shares the same ``now()``."""
    referenced = select(AuditEvent.prev_hash).where(
        AuditEvent.tenant_id == tenant_id, AuditEvent.prev_hash.is_not(None)
    )
    with session.no_autoflush:
        row = session.execute(
            select(AuditEvent.entry_hash)
            .where(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.entry_hash.is_not(None),
                AuditEvent.entry_hash.not_in(referenced),
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    return row or GENESIS_HASH


@event.listens_for(Session, "before_flush")
def _chain_audit_events(session: Session, _ctx, _instances) -> None:  # noqa: ANN001
    pending = [o for o in session.new if isinstance(o, AuditEvent) and o.entry_hash is None]
    if not pending:
        return
    last_by_tenant: dict[uuid.UUID, str] = {}
    for e in pending:  # session.new preserves insertion order
        if e.id is None:
            e.id = uuid.uuid4()
        prev = last_by_tenant.get(e.tenant_id)
        if prev is None:
            prev = _latest_hash(session, e.tenant_id)
        e.prev_hash = prev
        e.entry_hash = compute_entry_hash(prev, e)
        last_by_tenant[e.tenant_id] = e.entry_hash


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
    """Append an audit event to the caller's transaction (hash-chained at flush)."""
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


async def verify_chain(session: AsyncSession, tenant_id: uuid.UUID) -> tuple[bool, uuid.UUID | None]:
    """Walk the tenant's chain from the genesis hash as a linked list (order
    independent) and recompute every link. Returns ``(ok, first_bad_id)``:
    a row whose hash does not recompute, that is unreachable (orphan / fork),
    or that references a missing predecessor."""
    res = await session.execute(select(AuditEvent).where(AuditEvent.tenant_id == tenant_id))
    # Rows written before migration 0048 carry no hash and are not part of the chain.
    rows = [e for e in res.scalars().all() if e.entry_hash is not None]
    by_prev: dict[str, list[AuditEvent]] = {}
    for e in rows:
        by_prev.setdefault(e.prev_hash or "", []).append(e)
    seen: set[uuid.UUID] = set()
    prev = GENESIS_HASH
    while True:
        nxt = by_prev.get(prev, [])
        if not nxt:
            break
        if len(nxt) > 1:  # fork: two rows claim the same predecessor
            return False, sorted(nxt, key=lambda e: str(e.id))[0].id
        e = nxt[0]
        if e.entry_hash != compute_entry_hash(prev, e):
            return False, e.id
        seen.add(e.id)
        prev = e.entry_hash
    orphans = [e for e in rows if e.id not in seen]
    if orphans:
        return False, sorted(orphans, key=lambda e: str(e.id))[0].id
    return True, None


class AuditService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.repo = AuditRepository(session)

    async def list(self, *, action: str | None, limit: int, offset: int) -> list[AuditEvent]:
        return await self.repo.list(self.tenant_id, action=action, limit=limit, offset=offset)

    async def verify(self) -> tuple[bool, uuid.UUID | None]:
        return await verify_chain(self.session, self.tenant_id)
