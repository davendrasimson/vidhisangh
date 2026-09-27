"""Data-access layer for clients. Filters by ``tenant_id`` explicitly alongside RLS."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import BlindIndex
from app.core.db_utils import LIKE_ESCAPE, contains
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
            like = contains(q)
            # Substring search only on plaintext columns; the encrypted
            # identifiers (PAN, GSTIN) and email match exactly via blind index.
            stmt = stmt.where(
                or_(
                    Client.display_name.ilike(like, escape=LIKE_ESCAPE),
                    Client.legal_name.ilike(like, escape=LIKE_ESCAPE),
                    Client.email.ilike(like, escape=LIKE_ESCAPE),
                    Client.client_code.ilike(like, escape=LIKE_ESCAPE),
                    Client.city.ilike(like, escape=LIKE_ESCAPE),
                    Client.pan_bidx == BlindIndex.pan(q),
                    Client.gstin_bidx == BlindIndex.gstin(q),
                    Client.email_bidx == BlindIndex.email(q),
                )
            )
        return list((await self.session.execute(stmt)).scalars().all())

    async def find_by_pan(self, tenant_id: uuid.UUID, pan: str) -> Client | None:
        res = await self.session.execute(
            select(Client).where(
                Client.tenant_id == tenant_id, Client.deleted_at.is_(None),
                Client.pan_bidx == BlindIndex.pan(pan),
            ).limit(1)
        )
        return res.scalar_one_or_none()

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

    async def kyc_by_token_hash(self, token_hash: str) -> ClientKycRequest | None:
        """Public lookup — runs on a bypass-RLS session; the (hashed) token is the credential."""
        res = await self.session.execute(
            select(ClientKycRequest).where(ClientKycRequest.token_hash == token_hash)
        )
        return res.scalar_one_or_none()

    async def client_any_tenant(self, client_id: uuid.UUID) -> Client | None:
        """For the public form, after the token resolved the tenant."""
        res = await self.session.execute(
            select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
        )
        return res.scalar_one_or_none()
