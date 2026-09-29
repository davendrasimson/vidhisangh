"""Authenticated and tokenised public e-signature endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core import security
from app.core.deps import (
    AuthSessionDep,
    CurrentUserDep,
    TenantSessionDep,
    client_ip,
    require_permission,
)
from app.core.exceptions import TenantError
from app.core.http_utils import content_disposition
from app.core.ratelimit import RateLimiter
from app.core.storage import Storage, get_storage
from app.modules.signing.schemas import (
    EnvelopeCreate,
    EnvelopeRead,
    OtpSubmit,
    PublicStepRead,
    RejectSubmit,
    SignatureSubmit,
    SigningSessionRead,
)
from app.modules.signing.service import SigningService

router = APIRouter(prefix="/signing", tags=["Electronic signatures"])
public_router = APIRouter(prefix="/esign", tags=["Public electronic signature"])
StorageDep = Annotated[Storage, Depends(get_storage)]
otp_limit = RateLimiter(times=5, window_seconds=60, scope="esign-otp", fail_closed=True)
sign_limit = RateLimiter(times=12, window_seconds=60, scope="esign-public", fail_closed=True)


def _svc(current: CurrentUserDep, session: TenantSessionDep, storage: StorageDep) -> SigningService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return SigningService(session, storage, current.tenant_id, current.id)


def _download(name: str, content_type: str, data: bytes) -> Response:
    return Response(
        data,
        media_type=content_type,
        headers={
            "Content-Disposition": content_disposition(name),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/documents/{document_id}",
    response_model=EnvelopeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("document:update")],
)
async def prepare(
    document_id: uuid.UUID,
    data: EnvelopeCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> EnvelopeRead:
    svc = _svc(current, session, storage)
    envelope, _ = await svc.prepare(document_id, data)
    return await svc.to_read(envelope)


@router.get(
    "/envelopes",
    response_model=list[EnvelopeRead],
    dependencies=[require_permission("document:read")],
)
async def list_envelopes(
    current: CurrentUserDep, session: TenantSessionDep, storage: StorageDep
) -> list[EnvelopeRead]:
    svc = _svc(current, session, storage)
    return [await svc.to_read(item) for item in await svc.list()]


@router.get(
    "/envelopes/{envelope_id}",
    response_model=EnvelopeRead,
    dependencies=[require_permission("document:read")],
)
async def get_envelope(
    envelope_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep, storage: StorageDep
) -> EnvelopeRead:
    svc = _svc(current, session, storage)
    return await svc.to_read(await svc.get(envelope_id))


@router.post(
    "/steps/{step_id}/sign",
    response_model=EnvelopeRead,
    dependencies=[require_permission("document:read")],
)
async def internal_sign(
    step_id: uuid.UUID,
    data: SignatureSubmit,
    request: Request,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> EnvelopeRead:
    svc = _svc(current, session, storage)
    envelope = await svc.internal_sign(
        step_id, data, client_ip(request), request.headers.get("user-agent")
    )
    return await svc.to_read(envelope)


@router.post(
    "/steps/{step_id}/reject",
    response_model=EnvelopeRead,
    dependencies=[require_permission("document:read")],
)
async def internal_reject(
    step_id: uuid.UUID,
    data: RejectSubmit,
    request: Request,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> EnvelopeRead:
    svc = _svc(current, session, storage)
    envelope = await svc.internal_reject(step_id, data.remarks, client_ip(request))
    return await svc.to_read(envelope)


@router.post(
    "/envelopes/{envelope_id}/cancel",
    response_model=EnvelopeRead,
    dependencies=[require_permission("document:update")],
)
async def cancel(
    envelope_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep, storage: StorageDep
) -> EnvelopeRead:
    svc = _svc(current, session, storage)
    return await svc.to_read(await svc.cancel(envelope_id))


@router.get("/envelopes/{envelope_id}/download", dependencies=[require_permission("document:read")])
async def download(
    envelope_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
    certificate: Annotated[bool, Query()] = False,
) -> Response:
    name, content_type, data = await _svc(current, session, storage).download(
        envelope_id, certificate
    )
    return _download(name, content_type, data)


@router.get("/envelopes/{envelope_id}/source", dependencies=[require_permission("document:read")])
async def source_download(
    envelope_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> Response:
    name, content_type, data = await _svc(current, session, storage).source_download(envelope_id)
    return _download(name, content_type, data)


def _public(session: AuthSessionDep, storage: StorageDep) -> SigningService:
    return SigningService(session, storage, uuid.UUID(int=0))


@public_router.get("/{token}", response_model=PublicStepRead)
async def public_details(
    token: str, session: AuthSessionDep, storage: StorageDep
) -> PublicStepRead:
    step = await _public(session, storage).public_step(token)
    return PublicStepRead(
        document_title=step.envelope.title,
        sender_message=step.envelope.message,
        signer_name=step.signer_name,
        designation=step.designation,
        status=step.status,
        expires_at=step.token_expires_at,
    )


@public_router.post(
    "/{token}/send-otp", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(otp_limit)]
)
async def public_send_otp(token: str, session: AuthSessionDep, storage: StorageDep) -> Response:
    await _public(session, storage).send_otp(token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_router.post(
    "/{token}/verify-otp", response_model=SigningSessionRead, dependencies=[Depends(otp_limit)]
)
async def public_verify_otp(
    token: str, data: OtpSubmit, session: AuthSessionDep, storage: StorageDep
) -> SigningSessionRead:
    raw, expires = await _public(session, storage).verify_otp(token, data.otp)
    return SigningSessionRead(session_token=raw, expires_at=expires)


@public_router.get("/{token}/document", dependencies=[Depends(sign_limit)])
async def public_document(
    token: str,
    session_token: Annotated[str, Query(min_length=20, max_length=200)],
    session: AuthSessionDep,
    storage: StorageDep,
) -> Response:
    name, content_type, data = await _public(session, storage).public_document(token, session_token)
    return _download(name, content_type, data)


@public_router.post(
    "/{token}/sign", response_model=PublicStepRead, dependencies=[Depends(sign_limit)]
)
async def public_sign(
    token: str,
    data: SignatureSubmit,
    request: Request,
    session: AuthSessionDep,
    storage: StorageDep,
    session_token: Annotated[str, Query(min_length=20, max_length=200)],
) -> PublicStepRead:
    svc = _public(session, storage)
    envelope = await svc.public_sign(
        token, session_token, data, client_ip(request), request.headers.get("user-agent")
    )
    step = next(s for s in envelope.steps if s.token_hash == security.hash_link_token(token))
    return PublicStepRead(
        document_title=envelope.title,
        sender_message=envelope.message,
        signer_name=step.signer_name,
        designation=step.designation,
        status=step.status,
        expires_at=step.token_expires_at,
    )


@public_router.post(
    "/{token}/reject", response_model=PublicStepRead, dependencies=[Depends(sign_limit)]
)
async def public_reject(
    token: str,
    data: RejectSubmit,
    request: Request,
    session: AuthSessionDep,
    storage: StorageDep,
    session_token: Annotated[str, Query(min_length=20, max_length=200)],
) -> PublicStepRead:
    svc = _public(session, storage)
    envelope = await svc.public_reject(token, session_token, data.remarks, client_ip(request))
    step = next(s for s in envelope.steps if s.token_hash == security.hash_link_token(token))
    return PublicStepRead(
        document_title=envelope.title,
        sender_message=envelope.message,
        signer_name=step.signer_name,
        designation=step.designation,
        status=step.status,
        expires_at=step.token_expires_at,
    )
