"""Documents HTTP endpoints — folders, versioned upload/download, check-in/out.

RBAC-guarded (``document:*``) and tenant-scoped. File bytes flow through the
configured storage backend; the DB holds metadata + version history.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from app.core.ratelimit import upload_rate_limit
from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.core.http_utils import content_disposition, sanitize_filename
from app.core.pagination import PageParams, page_params
from app.core.storage import Storage, get_storage
from app.core.uploads import (
    UnsupportedUploadTypeError,
    UploadTooLargeError,
    read_limited,
    validate_upload,
)
from app.modules.documents.schemas import (
    DocumentRead,
    DocumentUpdate,
    FolderCreate,
    FolderRead,
    VersionRead,
)
from app.modules.documents.service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])

Pagination = Annotated[PageParams, Depends(page_params)]
StorageDep = Annotated[Storage, Depends(get_storage)]


def _svc(
    current: CurrentUserDep, session: TenantSessionDep, storage: StorageDep
) -> DocumentService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return DocumentService(session, current.id, current.tenant_id, storage)


def _parse_tags(raw: str | None) -> list[str]:
    return [t.strip() for t in (raw or "").split(",") if t.strip()]


async def _receive_upload(file: UploadFile) -> tuple[bytes, str]:
    """Read an upload under the size cap and verify its type.

    Returns ``(bytes, verified_content_type)``. Oversize → 413, a type outside
    the allow-list or bytes that contradict the declared type → 415. The
    verified type — never the client's header — is what gets stored and served.
    """
    try:
        data = await read_limited(file)
    except UploadTooLargeError as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc
    try:
        content_type = validate_upload(data, file.content_type, file.filename)
    except UnsupportedUploadTypeError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    return data, content_type


# ─── Folders ────────────────────────────────────────────────────────
@router.post(
    "/folders",
    response_model=FolderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a folder",
    dependencies=[require_permission("document:create")],
)
async def create_folder(
    data: FolderCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> FolderRead:
    folder = await _svc(current, session, storage).create_folder(data)
    return FolderRead.model_validate(folder)


@router.get(
    "/folders",
    response_model=list[FolderRead],
    summary="List folders (by parent / matter)",
    dependencies=[require_permission("document:read")],
)
async def list_folders(
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
    parent_id: Annotated[uuid.UUID | None, Query()] = None,
    matter_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[FolderRead]:
    folders = await _svc(current, session, storage).list_folders(parent_id, matter_id)
    return [FolderRead.model_validate(f) for f in folders]


# ─── Documents ──────────────────────────────────────────────────────
@router.post(
    "",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document (multipart)",
    dependencies=[Depends(upload_rate_limit), require_permission("document:create")],
)
async def upload_document(
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
    folder_id: Annotated[uuid.UUID | None, Form()] = None,
    matter_id: Annotated[uuid.UUID | None, Form()] = None,
    client_id: Annotated[uuid.UUID | None, Form()] = None,
    tags: Annotated[str | None, Form()] = None,
) -> DocumentRead:
    data, content_type = await _receive_upload(file)
    svc = _svc(current, session, storage)
    document = await svc.upload(
        name=sanitize_filename(name or file.filename or "untitled"),
        content_type=content_type,
        data=data,
        folder_id=folder_id,
        matter_id=matter_id,
        client_id=client_id,
        tags=_parse_tags(tags),
    )
    return (await svc.to_read([document]))[0]


@router.get(
    "",
    response_model=list[DocumentRead],
    summary="List / search documents",
    dependencies=[require_permission("document:read")],
)
async def list_documents(
    page: Pagination,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
    folder_id: Annotated[uuid.UUID | None, Query()] = None,
    matter_id: Annotated[uuid.UUID | None, Query()] = None,
    client_id: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> list[DocumentRead]:
    svc = _svc(current, session, storage)
    documents = await svc.list_documents(
        folder_id=folder_id,
        matter_id=matter_id,
        query=q,
        limit=page.limit,
        offset=page.offset,
        client_id=client_id,
    )
    return await svc.to_read(documents)


@router.get(
    "/{document_id}",
    response_model=DocumentRead,
    summary="Get a document",
    dependencies=[require_permission("document:read")],
)
async def get_document(
    document_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> DocumentRead:
    document = await _svc(current, session, storage).get_document(document_id)
    return DocumentRead.model_validate(document)


@router.patch(
    "/{document_id}",
    response_model=DocumentRead,
    summary="Rename / move / retag a document",
    dependencies=[require_permission("document:update")],
)
async def update_document(
    document_id: uuid.UUID,
    data: DocumentUpdate,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> DocumentRead:
    svc = _svc(current, session, storage)
    document = await svc.rename(
        document_id, name=data.name, folder_id=data.folder_id, tags=data.tags,
        client_id=data.client_id, set_client="client_id" in data.model_fields_set,
    )
    return (await svc.to_read([document]))[0]


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    dependencies=[require_permission("document:delete")],
)
async def delete_document(
    document_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> Response:
    await _svc(current, session, storage).delete_document(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Versions ───────────────────────────────────────────────────────
@router.get(
    "/{document_id}/versions",
    response_model=list[VersionRead],
    summary="Version history",
    dependencies=[require_permission("document:read")],
)
async def list_versions(
    document_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> list[VersionRead]:
    versions = await _svc(current, session, storage).list_versions(document_id)
    return [VersionRead.model_validate(v) for v in versions]


@router.post(
    "/{document_id}/versions",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new version",
    dependencies=[require_permission("document:update")],
)
async def add_version(
    document_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
    file: Annotated[UploadFile, File()],
    comment: Annotated[str | None, Form()] = None,
) -> DocumentRead:
    data, content_type = await _receive_upload(file)
    document = await _svc(current, session, storage).add_version(
        document_id,
        content_type=content_type,
        data=data,
        comment=comment,
    )
    return DocumentRead.model_validate(document)


def _download(name: str, content_type: str, data: bytes) -> Response:
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": content_disposition(name),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/{document_id}/download",
    summary="Download the current version",
    response_class=Response,
    dependencies=[require_permission("document:read")],
)
async def download_document(
    document_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> Response:
    document, data = await _svc(current, session, storage).download_current(document_id)
    return _download(document.name, document.content_type, data)


@router.get(
    "/versions/{version_id}/download",
    summary="Download a specific version",
    response_class=Response,
    dependencies=[require_permission("document:read")],
)
async def download_version(
    version_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> Response:
    version, data = await _svc(current, session, storage).download_version(version_id)
    return _download(f"v{version.version_no}", version.content_type, data)


# ─── Check-in / check-out ───────────────────────────────────────────
@router.post(
    "/{document_id}/checkout",
    response_model=DocumentRead,
    summary="Check out (lock) a document",
    dependencies=[require_permission("document:update")],
)
async def checkout(
    document_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> DocumentRead:
    document = await _svc(current, session, storage).checkout(document_id)
    return DocumentRead.model_validate(document)


@router.post(
    "/{document_id}/checkin",
    response_model=DocumentRead,
    summary="Check in (unlock) a document",
    dependencies=[require_permission("document:update")],
)
async def checkin(
    document_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> DocumentRead:
    document = await _svc(current, session, storage).checkin(document_id)
    return DocumentRead.model_validate(document)
