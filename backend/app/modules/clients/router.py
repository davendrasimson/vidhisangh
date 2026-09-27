"""Client master HTTP endpoints.

Firm-side (``/clients``): JWT + RBAC ``client:*``, tenant-scoped.
Client-side (``/kyc/{token}``): public, authenticated by the form token on a
bypass-RLS session — the token is the credential, like the client portal.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.core.ratelimit import public_token_rate_limit
from app.core.deps import AuthSessionDep, CurrentUserDep, TenantSessionDep, client_ip, require_permission
from app.core.exceptions import TenantError
from app.modules.clients.kyc import BUSINESS_TYPES, GST_STATE_CODES, TDS_SECTIONS
from app.modules.clients.models import ClientKind, ClientStatus
from app.modules.clients.schemas import (
    ClientCreate,
    ClientEraseResult,
    ClientRead,
    ClientSummary,
    ClientUpdate,
    ConsentEventCreate,
    ConsentEventRead,
    KycApply,
    KycPublicView,
    KycRequestCreate,
    KycRequestDetail,
    KycRequestRead,
    KycSubmission,
    KycSubmitResult,
    KycSubmission as _KycSubmission,  # noqa: F401 — re-export for OpenAPI clarity
    ValidationIssue,
)
from app.modules.clients.service import ClientService, PublicKycService, client_issues, kyc_url

router = APIRouter(prefix="/clients", tags=["Clients"])
public_router = APIRouter(prefix="/kyc", tags=["Clients (public KYC)"])


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> ClientService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return ClientService(session, current.id, current.tenant_id)


def _read(client) -> ClientRead:  # noqa: ANN001
    out = ClientRead.model_validate(client)
    out.issues = [ValidationIssue(**i.dict()) for i in client_issues(client)]
    return out


def _kyc_read(req, detail: bool = False, client=None):  # noqa: ANN001
    cls = KycRequestDetail if detail else KycRequestRead
    out = cls.model_validate(req)
    out.issues = [ValidationIssue(**i) for i in (req.issues or [])]
    out.url = kyc_url(req.token) if req.status in ("sent", "submitted") else None
    if detail and client is not None:
        out.changes = ClientService.changes(client, req)
    return out


# ═══ Reference data ═════════════════════════════════════════════════
@router.get("/reference", summary="Dropdown values: TDS sections, business types, GST states")
async def reference(current: CurrentUserDep) -> dict:
    return {
        "tds_sections": TDS_SECTIONS,
        "business_types": BUSINESS_TYPES,
        "states": [{"code": c, "name": n} for c, n in GST_STATE_CODES.items()],
    }


# ═══ Clients ════════════════════════════════════════════════════════
@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED,
             summary="Add a client (individual or business)", dependencies=[require_permission("client:create")])
async def create_client(data: ClientCreate, current: CurrentUserDep, session: TenantSessionDep) -> ClientRead:
    return _read(await _svc(current, session).create(data))


@router.get("", response_model=list[ClientSummary], summary="Clients, alphabetical",
            dependencies=[require_permission("client:read")])
async def list_clients(
    current: CurrentUserDep,
    session: TenantSessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    kind: Annotated[ClientKind | None, Query()] = None,
    status_: Annotated[ClientStatus | None, Query(alias="status")] = None,
) -> list[ClientSummary]:
    clients = await _svc(current, session).list(q=q, kind=kind, status=status_)
    return [ClientSummary.model_validate(c) for c in clients]


@router.get("/{client_id}", response_model=ClientRead, summary="A client with validation findings",
            dependencies=[require_permission("client:read")])
async def get_client(client_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep) -> ClientRead:
    return _read(await _svc(current, session).get(client_id))


@router.patch("/{client_id}", response_model=ClientRead, summary="Update a client (partial)",
              dependencies=[require_permission("client:update")])
async def update_client(
    client_id: uuid.UUID, data: ClientUpdate, current: CurrentUserDep, session: TenantSessionDep
) -> ClientRead:
    return _read(await _svc(current, session).update(client_id, data))


@router.delete(
    "/{client_id}",
    summary="Delete a client (soft by default; `?erase=true` hard-deletes the identity data — DPDP s.12)",
    dependencies=[require_permission("client:delete")],
    responses={204: {"description": "Soft-deleted"}, 200: {"model": ClientEraseResult, "description": "Erased"},
               409: {"description": "Legal hold: open matters or matters closed within the retention period"}},
)
async def delete_client(
    client_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    erase: Annotated[bool, Query(description="Hard-delete the client, its KYC and consent records; unlink matters/documents/invoices.")] = False,
    override_legal_hold: Annotated[bool, Query(description="tenant:manage only — proceed despite a legal hold; `reason` is recorded in the audit log.")] = False,
    reason: Annotated[str | None, Query(max_length=500)] = None,
) -> Response:
    svc = _svc(current, session)
    if not erase:
        await svc.delete(client_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    result = await svc.erase(
        client_id, override_legal_hold=override_legal_hold, reason=reason,
        actor_label=current.email, may_override=current.has_permission("tenant:manage"),
    )
    return JSONResponse(status_code=200, content=ClientEraseResult(**result).model_dump(mode="json"))


@router.get("/{client_id}/export", summary="Everything held about this client, as JSON (DPDP s.11 access)",
            dependencies=[require_permission("client:read")])
async def export_client(client_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep) -> Response:
    bundle = await _svc(current, session).export(client_id)
    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": f'attachment; filename="client-{client_id}.json"'},
    )


@router.get("/{client_id}/legal-holds", summary="Matters that block erasure of this client",
            dependencies=[require_permission("client:read")])
async def client_legal_holds(client_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep) -> list[dict]:
    svc = _svc(current, session)
    await svc.get(client_id)
    return await svc.legal_holds(client_id)


# ═══ Consent ledger (append-only) ═══════════════════════════════════
@router.get("/{client_id}/consents", response_model=list[ConsentEventRead],
            summary="Consent history for this client — every grant and withdrawal, newest first",
            dependencies=[require_permission("client:read")])
async def list_consents(client_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep) -> list[ConsentEventRead]:
    return [ConsentEventRead.model_validate(e) for e in await _svc(current, session).consents(client_id)]


@router.post("/{client_id}/consents", response_model=ConsentEventRead, status_code=status.HTTP_201_CREATED,
             summary="Record a consent grant or withdrawal on the client's behalf (staff source)",
             dependencies=[require_permission("client:update")])
async def record_consent(
    client_id: uuid.UUID, data: ConsentEventCreate, request: Request, current: CurrentUserDep, session: TenantSessionDep
) -> ConsentEventRead:
    event = await _svc(current, session).record_consent(client_id, data, ip=client_ip(request))
    return ConsentEventRead.model_validate(event)


# ═══ KYC (firm side) ═══════════════════════════════════════════════
@router.get("/{client_id}/kyc", response_model=list[KycRequestRead], summary="KYC requests sent to this client",
            dependencies=[require_permission("client:read")])
async def list_kyc(client_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep) -> list[KycRequestRead]:
    return [_kyc_read(r) for r in await _svc(current, session).kyc_requests(client_id)]


@router.post("/{client_id}/kyc", response_model=KycRequestRead, status_code=status.HTTP_201_CREATED,
             summary="Send a tokenised KYC form to the client (email if configured; the link is returned)",
             dependencies=[require_permission("client:update")])
async def send_kyc(
    client_id: uuid.UUID, data: KycRequestCreate, current: CurrentUserDep, session: TenantSessionDep
) -> KycRequestRead:
    return _kyc_read(await _svc(current, session).create_kyc_request(client_id, data))


@router.get("/{client_id}/kyc/{request_id}", response_model=KycRequestDetail,
            summary="A KYC request with the submission and a field-by-field diff",
            dependencies=[require_permission("client:read")])
async def get_kyc(
    client_id: uuid.UUID, request_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> KycRequestDetail:
    svc = _svc(current, session)
    client = await svc.get(client_id)
    return _kyc_read(await svc.kyc_request(client_id, request_id), detail=True, client=client)


@router.post("/{client_id}/kyc/{request_id}/apply", response_model=ClientRead,
             summary="Accept the submission: update the client and mark KYC verified",
             dependencies=[require_permission("client:update")])
async def apply_kyc(
    client_id: uuid.UUID, request_id: uuid.UUID, data: KycApply, current: CurrentUserDep, session: TenantSessionDep
) -> ClientRead:
    return _read(await _svc(current, session).apply_kyc(client_id, request_id, data))


@router.post("/{client_id}/kyc/{request_id}/cancel", response_model=KycRequestRead,
             summary="Withdraw a KYC link", dependencies=[require_permission("client:update")])
async def cancel_kyc(
    client_id: uuid.UUID, request_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> KycRequestRead:
    return _kyc_read(await _svc(current, session).cancel_kyc_request(client_id, request_id))


# ═══ KYC (client side, public) ══════════════════════════════════════
@public_router.get("/{token}", response_model=KycPublicView, summary="The KYC form for a token (public)",
                   dependencies=[Depends(public_token_rate_limit)])
async def kyc_view(token: str, session: AuthSessionDep) -> KycPublicView:
    return KycPublicView(**await PublicKycService(session).view(token))


@public_router.post("/{token}", response_model=KycSubmitResult, summary="Submit the KYC form (public)",
                    dependencies=[Depends(public_token_rate_limit)])
async def kyc_submit(token: str, data: KycSubmission, request: Request, session: AuthSessionDep) -> KycSubmitResult:
    req, issues = await PublicKycService(session).submit(token, data, ip=client_ip(request))
    errors = [i for i in issues if i.severity == "error"]
    return KycSubmitResult(
        status=req.status,
        issues=[ValidationIssue(**i.dict()) for i in issues],
        message=(
            "Thank you — your details have been received."
            + (" A few items will be checked with you." if errors else "")
        ),
    )
