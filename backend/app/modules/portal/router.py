"""Client portal HTTP endpoints.

Firm-side (``/portal/...``) is JWT + RBAC (``client:*``) and tenant-scoped.
Client-side (``/portal/client/{token}``) authenticates by token on a bypass-RLS
session and filters everything by the resolved access's tenant + matter.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import (
    AuthSessionDep,
    CurrentUserDep,
    TenantSessionDep,
    require_permission,
)
from app.core.exceptions import TenantError
from app.core.storage import Storage, get_storage
from app.modules.portal.schemas import (
    ApprovalCreate,
    ApprovalRead,
    ApprovalRespond,
    PortalAccessCreate,
    PortalAccessRead,
    PortalDocumentRead,
    PortalHearing,
    PortalInvoice,
    PortalView,
    UpdateCreate,
    UpdateRead,
)
from app.modules.portal.service import ClientPortalService, FirmPortalService

router = APIRouter(prefix="/portal", tags=["Client Portal"])

StorageDep = Annotated[Storage, Depends(get_storage)]


def _firm(current: CurrentUserDep, session: TenantSessionDep) -> FirmPortalService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return FirmPortalService(session, current.id, current.tenant_id)


# ═══ Firm-side management ════════════════════════════════════════════
@router.post(
    "/access",
    response_model=PortalAccessRead,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a client portal access to a matter",
    dependencies=[require_permission("client:create")],
)
async def create_access(
    data: PortalAccessCreate, current: CurrentUserDep, session: TenantSessionDep
) -> PortalAccessRead:
    access = await _firm(current, session).create_access(data)
    return PortalAccessRead.model_validate(access)


@router.get(
    "/access",
    response_model=list[PortalAccessRead],
    summary="List portal access for a matter",
    dependencies=[require_permission("client:read")],
)
async def list_access(
    current: CurrentUserDep,
    session: TenantSessionDep,
    matter_id: Annotated[uuid.UUID, Query()],
) -> list[PortalAccessRead]:
    rows = await _firm(current, session).list_access(matter_id)
    return [PortalAccessRead.model_validate(a) for a in rows]


@router.post(
    "/access/{access_id}/revoke",
    response_model=PortalAccessRead,
    summary="Revoke a portal access",
    dependencies=[require_permission("client:update")],
)
async def revoke_access(
    access_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> PortalAccessRead:
    access = await _firm(current, session).revoke(access_id)
    return PortalAccessRead.model_validate(access)


@router.post(
    "/matters/{matter_id}/updates",
    response_model=UpdateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Post an update for the client",
    dependencies=[require_permission("client:update")],
)
async def post_update(
    matter_id: uuid.UUID,
    data: UpdateCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> UpdateRead:
    update = await _firm(current, session).post_update(matter_id, data)
    return UpdateRead.model_validate(update)


@router.post(
    "/matters/{matter_id}/approvals",
    response_model=ApprovalRead,
    status_code=status.HTTP_201_CREATED,
    summary="Request client approval",
    dependencies=[require_permission("client:update")],
)
async def request_approval(
    matter_id: uuid.UUID,
    data: ApprovalCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> ApprovalRead:
    approval = await _firm(current, session).request_approval(matter_id, data)
    return ApprovalRead.model_validate(approval)


@router.get(
    "/matters/{matter_id}/approvals",
    response_model=list[ApprovalRead],
    summary="List approval requests (firm view)",
    dependencies=[require_permission("client:read")],
)
async def list_approvals(
    matter_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> list[ApprovalRead]:
    rows = await _firm(current, session).list_approvals(matter_id)
    return [ApprovalRead.model_validate(a) for a in rows]


@router.get(
    "/matters/{matter_id}/documents",
    response_model=list[uuid.UUID],
    summary="IDs of documents shared with the client",
    dependencies=[require_permission("client:read")],
)
async def list_shared_documents(
    matter_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> list[uuid.UUID]:
    return await _firm(current, session).shared_document_ids(matter_id)


@router.post(
    "/matters/{matter_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Share a document with the client",
    dependencies=[require_permission("client:update")],
)
async def share_document(
    matter_id: uuid.UUID,
    document_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> Response:
    await _firm(current, session).share_document(matter_id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/matters/{matter_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop sharing a document",
    dependencies=[require_permission("client:update")],
)
async def unshare_document(
    matter_id: uuid.UUID,
    document_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> Response:
    await _firm(current, session).unshare_document(matter_id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ═══ Client-side (token) ═════════════════════════════════════════════
@router.get(
    "/client/{token}",
    response_model=PortalView,
    summary="Client portal view (token-authenticated)",
)
async def portal_view(
    token: str, session: AuthSessionDep, storage: StorageDep
) -> PortalView:
    data = await ClientPortalService(session, storage).view(token)
    access = data["access"]
    matter = data["matter"]
    return PortalView(
        client_name=access.client_name,
        matter_number=matter.matter_number,
        matter_title=matter.title,
        status=str(matter.status),
        stage=str(matter.stage),
        court=matter.court,
        opened_on=matter.opened_on,
        hearings=[
            PortalHearing(
                scheduled_on=h.scheduled_on, court=h.court, purpose=h.purpose, status=str(h.status)
            )
            for h in matter.hearings
        ],
        updates=[UpdateRead.model_validate(u) for u in data["updates"]],
        approvals=[ApprovalRead.model_validate(a) for a in data["approvals"]],
        documents=[
            PortalDocumentRead(
                id=d.id, name=d.name, size=d.size, version_count=d.version_count, updated_at=d.updated_at
            )
            for d in data["documents"]
        ],
        invoices=[PortalInvoice(
            id=i.id, invoice_number=i.invoice_number, status=str(i.status),
            issue_date=i.issue_date, due_date=i.due_date,
            total=float(i.total), amount_paid=float(i.amount_paid),
        ) for i in data["invoices"]],
    )


@router.post(
    "/client/{token}/approvals/{approval_id}/respond",
    response_model=ApprovalRead,
    summary="Approve or reject a request (client)",
)
async def respond_approval(
    token: str,
    approval_id: uuid.UUID,
    data: ApprovalRespond,
    session: AuthSessionDep,
    storage: StorageDep,
) -> ApprovalRead:
    approval = await ClientPortalService(session, storage).respond_approval(
        token, approval_id, approve=data.approve, note=data.note
    )
    return ApprovalRead.model_validate(approval)


@router.get(
    "/client/{token}/documents/{document_id}/download",
    summary="Download a shared document (client)",
    response_class=Response,
)
async def client_download(
    token: str,
    document_id: uuid.UUID,
    session: AuthSessionDep,
    storage: StorageDep,
) -> Response:
    document, content = await ClientPortalService(session, storage).download(token, document_id)
    return Response(
        content=content,
        media_type=document.content_type,
        headers={"Content-Disposition": f'attachment; filename="{document.name}"'},
    )
