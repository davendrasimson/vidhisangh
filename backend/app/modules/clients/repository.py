"""Data-access layer for clients. Filters by ``tenant_id`` explicitly alongside RLS."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clients.models import Client, ClientKind, ClientKycRequest, ClientStatus


class ClientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def get(self, tenant_id: uuid.UUID, client_id: uuid.UUID) -> Client | None:
        res = await self.session.execute(
            select(Client).where(
                Client.id == client_id, Client.tenant_id == tenant_id, Client.deleted_at.is_(None)
            )
        )
        return res.scalar_one_or_none()

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        q: str | None = None,
        kind: ClientKind | None = None,
        status: ClientStatus | None = None,
        limit: int = 200,
    ) -> list[Client]:
        stmt = (
            select(Client)
            .where(Client.tenant_id == tenant_id, Client.deleted_at.is_(None))
            .order_by(Client.display_name.asc())
            .limit(limit)
        )
        if kind is not None:
            stmt = stmt.where(Client.kind == kind)
        if status is not None:
            stmt = stmt.where(Client.status == status)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Client.display_name.ilike(like), Client.legal_name.ilike(like),
                    Client.email.ilike(like), Client.mobile.ilike(like), Client.pan.ilike(like),
                    Client.gstin.ilike(like), Client.client_code.ilike(like), Client.city.ilike(like),
                )
            )
        return list((await self.session.execute(stmt)).scalars().all())

    # ── KYC requests ──────────────────────────────────────────────
    async def kyc_requests(self, tenant_id: uuid.UUID, client_id: uuid.UUID) -> list[ClientKycRequest]:
        res = await self.session.execute(
            select(ClientKycRequest)
            .where(ClientKycRequest.tenant_id == tenant_id, ClientKycRequest.client_id == client_id)
            .order_by(ClientKycRequest.created_at.desc())
        )
        return list(res.scalars().all())

    async def kyc_request(
        self, tenant_id: uuid.UUID, client_id: uuid.UUID, request_id: uuid.UUID
    ) -> ClientKycRequest | None:
        res = await self.session.execute(
            select(ClientKycRequest).where(
                ClientKycRequest.id == request_id,
                ClientKycRequest.client_id == client_id,
                ClientKycRequest.tenant_id == tenant_id,
            )
        )
        return res.scalar_one_or_none()

    async def kyc_by_token(self, token: str) -> ClientKycRequest | None:
        """Public lookup — runs on a bypass-RLS session; the token is the credential."""
        res = await self.session.execute(select(ClientKycRequest).where(ClientKycRequest.token == token))
        return res.scalar_one_or_none()

    async def client_any_tenant(self, client_id: uuid.UUID) -> Client | None:
        """For the public form, after the token resolved the tenant."""
        res = await self.session.execute(
            select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
        )
        return res.scalar_one_or_none()
