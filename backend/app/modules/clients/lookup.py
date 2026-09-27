"""Small helpers other modules use to attach a client to their records."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.clients.models import Client


async def require_client(session: AsyncSession, tenant_id: uuid.UUID, client_id: uuid.UUID) -> Client:
    """The client, or 404 — never a client of another tenant."""
    client = await session.get(Client, client_id)
    if client is None or client.tenant_id != tenant_id or client.deleted_at is not None:
        raise NotFoundError("Client not found.")
    return client


async def client_names(
    session: AsyncSession, tenant_id: uuid.UUID, ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    """{client_id: display_name} for the ids given (None / duplicates ignored)."""
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    res = await session.execute(
        select(Client.id, Client.display_name).where(Client.tenant_id == tenant_id, Client.id.in_(wanted))
    )
    return {cid: name for cid, name in res.all()}
