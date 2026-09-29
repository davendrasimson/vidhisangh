"""Queries for e-signature envelopes."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.signing.models import EnvelopeStatus, SignatureEnvelope, SignatureStep


class SigningRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _envelopes(self):
        return select(SignatureEnvelope).options(
            selectinload(SignatureEnvelope.steps), selectinload(SignatureEnvelope.events)
        )

    async def get(self, tenant_id: uuid.UUID, envelope_id: uuid.UUID) -> SignatureEnvelope | None:
        row = await self.session.execute(
            self._envelopes().where(
                SignatureEnvelope.id == envelope_id,
                SignatureEnvelope.tenant_id == tenant_id,
                SignatureEnvelope.deleted_at.is_(None),
            )
        )
        return row.scalar_one_or_none()

    async def list(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[SignatureEnvelope]:
        row = await self.session.execute(
            self._envelopes()
            .outerjoin(SignatureStep, SignatureStep.envelope_id == SignatureEnvelope.id)
            .where(
                SignatureEnvelope.tenant_id == tenant_id,
                SignatureEnvelope.deleted_at.is_(None),
                or_(
                    SignatureEnvelope.created_by == user_id, SignatureStep.signer_user_id == user_id
                ),
            )
            .distinct()
            .order_by(SignatureEnvelope.sent_at.desc())
        )
        return list(row.scalars().all())

    async def active_for_document(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> SignatureEnvelope | None:
        row = await self.session.execute(
            self._envelopes().where(
                SignatureEnvelope.tenant_id == tenant_id,
                SignatureEnvelope.document_id == document_id,
                SignatureEnvelope.status == EnvelopeStatus.PENDING,
                SignatureEnvelope.deleted_at.is_(None),
            )
        )
        return row.scalar_one_or_none()

    async def step(self, tenant_id: uuid.UUID, step_id: uuid.UUID) -> SignatureStep | None:
        row = await self.session.execute(
            select(SignatureStep)
            .where(SignatureStep.id == step_id, SignatureStep.tenant_id == tenant_id)
            .options(selectinload(SignatureStep.envelope).selectinload(SignatureEnvelope.steps))
        )
        return row.scalar_one_or_none()

    async def public_step(self, token_hash: str) -> SignatureStep | None:
        row = await self.session.execute(
            select(SignatureStep)
            .where(SignatureStep.token_hash == token_hash)
            .options(selectinload(SignatureStep.envelope).selectinload(SignatureEnvelope.steps))
        )
        return row.scalar_one_or_none()
