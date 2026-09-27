"""Billing HTTP endpoints — invoices, line items, pay + reconcile (RBAC-guarded)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.core.pagination import PageParams, page_params
from app.core.payments import PaymentProvider, get_payment_provider
from app.modules.billing.models import InvoiceStatus
from app.modules.billing.schemas import (
    InvoiceCreate,
    InvoiceDetail,
    InvoiceRead,
    InvoiceUpdate,
    LineItemCreate,
    MatterInvoicePrepare,
)
from app.modules.billing.service import BillingService
from app.modules.payments.schemas import OrderResponse

router = APIRouter(prefix="/billing", tags=["Billing"])

Pagination = Annotated[PageParams, Depends(page_params)]
PaymentProviderDep = Annotated[PaymentProvider, Depends(get_payment_provider)]


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> BillingService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return BillingService(session, current.id, current.tenant_id)


# ─── Invoices ───────────────────────────────────────────────────────
@router.post(
    "/invoices",
    response_model=InvoiceDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create an invoice",
    dependencies=[require_permission("invoice:create")],
)
async def create_invoice(
    data: InvoiceCreate, current: CurrentUserDep, session: TenantSessionDep
) -> InvoiceDetail:
    return InvoiceDetail.model_validate(await _svc(current, session).create_invoice(data))


@router.post(
    "/matters/{matter_id}/prepare-invoice",
    response_model=InvoiceDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft invoice from unbilled matter fee events",
    dependencies=[require_permission("invoice:create"), require_permission("matter:read")],
)
async def prepare_matter_invoice(
    matter_id: uuid.UUID, data: MatterInvoicePrepare,
    current: CurrentUserDep, session: TenantSessionDep,
) -> InvoiceDetail:
    return InvoiceDetail.model_validate(await _svc(current, session).prepare_matter_invoice(matter_id, data))


@router.get(
    "/invoices",
    response_model=list[InvoiceRead],
    summary="List invoices",
    dependencies=[require_permission("invoice:read")],
)
async def list_invoices(
    page: Pagination,
    current: CurrentUserDep,
    session: TenantSessionDep,
    status_filter: Annotated[InvoiceStatus | None, Query(alias="status")] = None,
    client_id: Annotated[uuid.UUID | None, Query()] = None,
    matter_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[InvoiceRead]:
    invoices = await _svc(current, session).list_invoices(status_filter, page.limit, page.offset, client_id=client_id, matter_id=matter_id)
    return [InvoiceRead.model_validate(i) for i in invoices]


@router.get(
    "/invoices/{invoice_id}",
    response_model=InvoiceDetail,
    summary="Invoice detail",
    dependencies=[require_permission("invoice:read")],
)
async def get_invoice(
    invoice_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> InvoiceDetail:
    return InvoiceDetail.model_validate(await _svc(current, session).get_invoice(invoice_id))


@router.patch(
    "/invoices/{invoice_id}",
    response_model=InvoiceDetail,
    summary="Update an invoice",
    dependencies=[require_permission("invoice:update")],
)
async def update_invoice(
    invoice_id: uuid.UUID,
    data: InvoiceUpdate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> InvoiceDetail:
    return InvoiceDetail.model_validate(await _svc(current, session).update_invoice(invoice_id, data))


@router.delete(
    "/invoices/{invoice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an invoice",
    dependencies=[require_permission("invoice:delete")],
)
async def delete_invoice(
    invoice_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).delete_invoice(invoice_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Line items ─────────────────────────────────────────────────────
@router.post(
    "/invoices/{invoice_id}/line-items",
    response_model=InvoiceDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Add a line item",
    dependencies=[require_permission("invoice:update")],
)
async def add_line_item(
    invoice_id: uuid.UUID,
    data: LineItemCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> InvoiceDetail:
    return InvoiceDetail.model_validate(await _svc(current, session).add_line_item(invoice_id, data))


@router.delete(
    "/line-items/{item_id}",
    response_model=InvoiceDetail,
    summary="Remove a line item",
    dependencies=[require_permission("invoice:update")],
)
async def remove_line_item(
    item_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> InvoiceDetail:
    return InvoiceDetail.model_validate(await _svc(current, session).remove_line_item(item_id))


# ─── Payment ────────────────────────────────────────────────────────
@router.post(
    "/invoices/{invoice_id}/pay",
    response_model=OrderResponse,
    summary="Start online payment for an invoice",
    dependencies=[require_permission("invoice:update")],
)
async def pay_invoice(
    invoice_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    provider: PaymentProviderDep,
) -> OrderResponse:
    payment = await _svc(current, session).pay(invoice_id, provider)
    return OrderResponse(
        payment_id=payment.id,
        order_id=payment.provider_order_id,
        key_id=provider.public_key,
        amount=payment.amount,
        currency=payment.currency,
        provider=payment.provider,
    )


@router.post(
    "/invoices/{invoice_id}/reconcile",
    response_model=InvoiceDetail,
    summary="Reconcile paid amount from captured payments",
    dependencies=[require_permission("invoice:update")],
)
async def reconcile_invoice(
    invoice_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> InvoiceDetail:
    return InvoiceDetail.model_validate(await _svc(current, session).reconcile(invoice_id))
