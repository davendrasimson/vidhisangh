"""Drafting HTTP endpoints — the editor's drafts (tenant-scoped)."""

from __future__ import annotations

import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.core.http_utils import content_disposition
from app.core.storage import Storage, get_storage
from app.modules.documents.schemas import DocumentRead
from app.modules.drafting.schemas import (
    DraftCreate,
    DraftRead,
    DraftSummary,
    DraftUpdate,
    DraftVersionCreate,
    DraftVersionDetail,
    DraftVersionRead,
    FileToLibrary,
)
from app.modules.drafting.service import DraftingService

router = APIRouter(prefix="/drafts", tags=["Drafting"])
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
StorageDep = Annotated[Storage, Depends(get_storage)]


def _svc(current: CurrentUserDep, session: TenantSessionDep, storage: StorageDep) -> DraftingService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return DraftingService(session, current.id, current.tenant_id, storage)


@router.post(
    "",
    response_model=DraftRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a document",
    dependencies=[require_permission("document:create")],
)
async def create_draft(
    data: DraftCreate, current: CurrentUserDep, session: TenantSessionDep, storage: StorageDep
) -> DraftRead:
    return DraftRead.model_validate(await _svc(current, session, storage).create(data))


@router.get(
    "",
    response_model=list[DraftSummary],
    summary="My firm's drafts, most recently edited first",
    dependencies=[require_permission("document:read")],
)
async def list_drafts(
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
    matter_id: Annotated[uuid.UUID | None, Query()] = None,
    client_id: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> list[DraftSummary]:
    svc = _svc(current, session, storage)
    return await svc.to_summary(await svc.list(matter_id=matter_id, q=q, client_id=client_id))


@router.get(
    "/{draft_id}",
    response_model=DraftRead,
    summary="A draft with its content",
    dependencies=[require_permission("document:read")],
)
async def get_draft(
    draft_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep, storage: StorageDep
) -> DraftRead:
    return DraftRead.model_validate(await _svc(current, session, storage).get(draft_id))


@router.patch(
    "/{draft_id}",
    response_model=DraftRead,
    summary="Autosave — send only what changed",
    dependencies=[require_permission("document:update")],
)
async def update_draft(
    draft_id: uuid.UUID,
    data: DraftUpdate,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> DraftRead:
    return DraftRead.model_validate(await _svc(current, session, storage).update(draft_id, data))


@router.delete(
    "/{draft_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a draft",
    dependencies=[require_permission("document:delete")],
)
async def delete_draft(
    draft_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep, storage: StorageDep
) -> Response:
    await _svc(current, session, storage).delete(draft_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Versions ──────────────────────────────────────────────────────
@router.get(
    "/{draft_id}/versions",
    response_model=list[DraftVersionRead],
    summary="Named versions, newest first",
    dependencies=[require_permission("document:read")],
)
async def list_versions(
    draft_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep, storage: StorageDep
) -> list[DraftVersionRead]:
    versions = await _svc(current, session, storage).versions(draft_id)
    return [DraftVersionRead.model_validate(v) for v in versions]


@router.post(
    "/{draft_id}/versions",
    response_model=DraftVersionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Save the current text as a named version",
    dependencies=[require_permission("document:update")],
)
async def create_version(
    draft_id: uuid.UUID,
    data: DraftVersionCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> DraftVersionRead:
    return DraftVersionRead.model_validate(await _svc(current, session, storage).snapshot(draft_id, data.note))


@router.get(
    "/{draft_id}/versions/{version_id}",
    response_model=DraftVersionDetail,
    summary="A version's content (to preview before restoring)",
    dependencies=[require_permission("document:read")],
)
async def get_version(
    draft_id: uuid.UUID,
    version_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> DraftVersionDetail:
    return DraftVersionDetail.model_validate(await _svc(current, session, storage).get_version(draft_id, version_id))


@router.post(
    "/{draft_id}/versions/{version_id}/restore",
    response_model=DraftRead,
    summary="Restore a version (the current text is snapshotted first)",
    dependencies=[require_permission("document:update")],
)
async def restore_version(
    draft_id: uuid.UUID,
    version_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> DraftRead:
    return DraftRead.model_validate(await _svc(current, session, storage).restore(draft_id, version_id))


# ── Export / filing ───────────────────────────────────────────────
@router.get(
    "/{draft_id}/export.docx",
    summary="Download as Word (.docx), built from the document's structure",
    dependencies=[require_permission("document:read")],
    response_class=Response,
)
async def export_docx(
    draft_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep, storage: StorageDep
) -> Response:
    filename, blob = await _svc(current, session, storage).docx(draft_id)
    return Response(
        content=blob,
        media_type=_DOCX,
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.post(
    "/{draft_id}/file",
    response_model=DocumentRead,
    summary="File the draft into the document library as a .docx (new version if already filed)",
    dependencies=[require_permission("document:create")],
)
async def file_to_library(
    draft_id: uuid.UUID,
    data: FileToLibrary,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> DocumentRead:
    return DocumentRead.model_validate(await _svc(current, session, storage).file_to_library(draft_id, data))
