from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.storage import Storage, get_storage
from app.modules.sampledata.schemas import SampleDataDelete, SampleDataStatus
from app.modules.sampledata.service import SampleDataService

router = APIRouter(prefix="/sample-data", tags=["Sample data"])
StorageDep = Annotated[Storage, Depends(get_storage)]


def _service(
    current: CurrentUserDep, session: TenantSessionDep, storage: Storage
) -> SampleDataService:
    if current.tenant_id is None:
        raise HTTPException(400, "No tenant is associated with this session.")
    return SampleDataService(session, current.tenant_id, current.id, storage)


@router.get("", response_model=SampleDataStatus, dependencies=[require_permission("tenant:read")])
async def status(current: CurrentUserDep, session: TenantSessionDep, storage: StorageDep) -> dict:
    return await _service(current, session, storage).status()


@router.post(
    "", response_model=SampleDataStatus, dependencies=[require_permission("tenant:update")]
)
async def create(current: CurrentUserDep, session: TenantSessionDep, storage: StorageDep) -> dict:
    return await _service(current, session, storage).create()


@router.post(
    "/delete", response_model=SampleDataStatus, dependencies=[require_permission("tenant:update")]
)
async def clear(
    data: SampleDataDelete,
    current: CurrentUserDep,
    session: TenantSessionDep,
    storage: StorageDep,
) -> dict:
    if not data.confirmed:
        raise HTTPException(400, "Deletion requires explicit confirmation.")
    return await _service(current, session, storage).clear()
