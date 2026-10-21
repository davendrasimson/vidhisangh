"""Billing HTTP endpoints — invoices, line items, pay + reconcile (RBAC-guarded)."""

from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import AuthSessionDep, CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import NotFoundError, TenantError, ValidationError
from app.core.pagination import PageParams, page_params
from app.core.payments import PaymentProvider, get_payment_provider
from app.core.uploads import read_limited, validate_upload
from app.modules.billing.models import BillingReceipt, Invoice, InvoiceStatus, TimeEntryStatus
from app.modules.billing.schemas import (
    BillingBranding,
    BillingSummary,
    BillingVerification,
    FollowUpCreate,
    FollowUpRead,
    InvoiceCreate,
    InvoiceDetail,
    InvoiceRead,
    InvoiceUpdate,
    LineItemCreate,
    MatterInvoicePrepare,
    InvoiceTaxFields,
    PublicInvoiceRead,
    ReceiptCreate,
    ReceiptRead,
    TimeEntryCreate,
    TimeEntryIds,
    TimeEntryRead,
    TimeEntryReject,
    TimeEntryUpdate,
    TimeImportCommit,
    TimeImportPreview,
    TimeInvoiceCreate,
)
from app.modules.billing.service import BillingService
from app.modules.billing.timesheets import TimesheetService, normalise_rows
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import OrderResponse, PaymentVerify
from app.modules.payments.service import PaymentService
from app.modules.tenancy.models import Tenant

router = APIRouter(prefix="/billing", tags=["Billing"])

Pagination = Annotated[PageParams, Depends(page_params)]
PaymentProviderDep = Annotated[PaymentProvider, Depends(get_payment_provider)]


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> BillingService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return BillingService(session, current.id, current.tenant_id)


def _time_svc(current: CurrentUserDep, session: TenantSessionDep) -> TimesheetService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return TimesheetService(session, current.id, current.tenant_id)


async def _public_invoice(session: AuthSessionDep, token: str) -> tuple[Invoice, BillingBranding]:
    invoice = await session.scalar(
        select(Invoice)
        .where(Invoice.payment_token == token, Invoice.deleted_at.is_(None))
        .options(selectinload(Invoice.line_items))
    )
    if invoice is None:
        raise NotFoundError("Invoice link not found.")
    tenant = await session.scalar(select(Tenant).where(Tenant.id == invoice.tenant_id))
    block = dict((tenant.settings if tenant else {}).get("billing") or {})
    if tenant and not block.get("legal_name"):
        block["legal_name"] = tenant.name
    branding = BillingBranding(
        **{key: value for key, value in block.items() if key in BillingBranding.model_fields}
    )
    return invoice, branding


def _public_read(invoice: Invoice, branding: BillingBranding) -> PublicInvoiceRead:
    return PublicInvoiceRead(
        invoice_number=invoice.invoice_number,
        document_type=invoice.document_type,
        client_name=invoice.client_name,
        status=invoice.status,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        currency=invoice.currency,
        subtotal=invoice.subtotal,
        tax_rate=invoice.tax_rate,
        tax_amount=invoice.tax_amount,
        total=invoice.total,
        amount_paid=invoice.amount_paid,
        notes=invoice.notes,
        verification_code=invoice.verification_code,
        line_items=invoice.line_items,
        branding=branding,
        **InvoiceTaxFields.model_validate(invoice, from_attributes=True).model_dump(),
    )


# ─── Public payment and authenticity ───────────────────────────────
@router.get("/public/invoices/{token}", response_model=PublicInvoiceRead)
async def public_invoice(token: str, session: AuthSessionDep) -> PublicInvoiceRead:
    invoice, branding = await _public_invoice(session, token)
    return _public_read(invoice, branding)


@router.post("/public/invoices/{token}/pay", response_model=OrderResponse)
async def public_pay_invoice(
    token: str, session: AuthSessionDep, provider: PaymentProviderDep
) -> OrderResponse:
    invoice, _ = await _public_invoice(session, token)
    payment = await BillingService(session, invoice.created_by, invoice.tenant_id).pay(
        invoice.id, provider
    )
    return OrderResponse(
        payment_id=payment.id,
        order_id=payment.provider_order_id,
        key_id=provider.public_key,
        amount=payment.amount,
        currency=payment.currency,
        provider=payment.provider,
    )


@router.post(
    "/public/invoices/{token}/payments/{payment_id}/verify", response_model=PublicInvoiceRead
)
async def public_verify_payment(
    token: str,
    payment_id: uuid.UUID,
    data: PaymentVerify,
    session: AuthSessionDep,
    provider: PaymentProviderDep,
) -> PublicInvoiceRead:
    invoice, branding = await _public_invoice(session, token)
    payment = await PaymentRepository(session).get(invoice.tenant_id, payment_id)
    if payment is None or payment.invoice_id != invoice.id:
        raise NotFoundError("Payment not found for this invoice.")
    await PaymentService(session, invoice.created_by, invoice.tenant_id, provider).verify(
        payment_id, data
    )
    updated = await BillingService(session, invoice.created_by, invoice.tenant_id).reconcile(
        invoice.id
    )
    return _public_read(updated, branding)


@router.get("/verify/{code}", response_model=BillingVerification)
async def verify_billing_document(code: str, session: AuthSessionDep) -> BillingVerification:
    invoice = await session.scalar(
        select(Invoice).where(
            Invoice.verification_code == code.upper(), Invoice.deleted_at.is_(None)
        )
    )
    if invoice is not None:
        tenant = await session.scalar(select(Tenant).where(Tenant.id == invoice.tenant_id))
        return BillingVerification(
            **{
                "valid": True,
                "document_type": invoice.document_type,
                "number": invoice.invoice_number,
                "firm": tenant.name if tenant else "",
                "client_name": invoice.client_name,
                "issue_date": invoice.issue_date,
                "total": invoice.total,
                "currency": invoice.currency,
                "status": invoice.status,
            }
        )
    receipt = await session.scalar(
        select(BillingReceipt).where(
            BillingReceipt.verification_code == code.upper(), BillingReceipt.deleted_at.is_(None)
        )
    )
    if receipt is not None:
        tenant = await session.scalar(select(Tenant).where(Tenant.id == receipt.tenant_id))
        return BillingVerification(
            **{
                "valid": True,
                "document_type": "receipt",
                "number": receipt.receipt_number,
                "firm": tenant.name if tenant else "",
                "received_on": receipt.received_on,
                "total": receipt.amount,
                "currency": "INR",
                "status": "received",
            }
        )
    raise NotFoundError("No authentic billing document matches this code.")


@router.get("/verify/{code}/qr")
async def billing_document_qr(code: str) -> StreamingResponse:
    import segno

    qr = segno.make(f"{settings.PUBLIC_APP_URL}/verify/invoice/{code.upper()}", error="m")
    output = BytesIO()
    qr.save(output, kind="svg", scale=4, border=2, dark="#173b7a")
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": f'inline; filename="verify-{code.upper()}.svg"',
        },
    )


# ─── Invoices ───────────────────────────────────────────────────────
@router.get(
    "/summary",
    response_model=BillingSummary,
    dependencies=[require_permission("invoice:read")],
)
async def billing_summary(current: CurrentUserDep, session: TenantSessionDep) -> BillingSummary:
    return await _svc(current, session).summary()


@router.get(
    "/invoices/pending",
    response_model=list[InvoiceRead],
    dependencies=[require_permission("invoice:read")],
)
async def pending_invoices(current: CurrentUserDep, session: TenantSessionDep) -> list[InvoiceRead]:
    return [
        InvoiceRead.model_validate(row) for row in await _svc(current, session).pending_invoices()
    ]


@router.get(
    "/follow-ups",
    response_model=list[FollowUpRead],
    dependencies=[require_permission("invoice:read")],
)
async def list_follow_ups(
    page: Pagination, current: CurrentUserDep, session: TenantSessionDep
) -> list[FollowUpRead]:
    rows = await _svc(current, session).list_follow_ups(page.limit, page.offset)
    return [FollowUpRead.model_validate(row) for row in rows]


@router.get(
    "/receipts",
    response_model=list[ReceiptRead],
    dependencies=[require_permission("invoice:read")],
)
async def list_receipts(
    page: Pagination, current: CurrentUserDep, session: TenantSessionDep
) -> list[ReceiptRead]:
    rows = await _svc(current, session).list_receipts(page.limit, page.offset)
    return [ReceiptRead.model_validate(row) for row in rows]


@router.get(
    "/settings/branding",
    response_model=BillingBranding,
    dependencies=[require_permission("invoice:read")],
)
async def get_billing_branding(
    current: CurrentUserDep, session: TenantSessionDep
) -> BillingBranding:
    return await _svc(current, session).branding()


@router.put(
    "/settings/branding",
    response_model=BillingBranding,
    dependencies=[require_permission("tenant:manage")],
)
async def update_billing_branding(
    data: BillingBranding, current: CurrentUserDep, session: TenantSessionDep
) -> BillingBranding:
    return await _svc(current, session).set_branding(data)


# ─── Counsel time and spreadsheet billing ─────────────────────────
@router.get(
    "/time-entries",
    response_model=list[TimeEntryRead],
    dependencies=[require_permission("timeentry:read")],
)
async def list_my_time(
    current: CurrentUserDep,
    session: TenantSessionDep,
    status_filter: Annotated[TimeEntryStatus | None, Query(alias="status")] = None,
) -> list[TimeEntryRead]:
    return await _time_svc(current, session).list(all_users=False, status=status_filter)


@router.get(
    "/time-entries/all",
    response_model=list[TimeEntryRead],
    dependencies=[require_permission("invoice:read")],
)
async def list_firm_time(
    current: CurrentUserDep,
    session: TenantSessionDep,
    status_filter: Annotated[TimeEntryStatus | None, Query(alias="status")] = None,
) -> list[TimeEntryRead]:
    return await _time_svc(current, session).list(all_users=True, status=status_filter)


@router.post(
    "/time-entries",
    response_model=TimeEntryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("timeentry:create")],
)
async def create_time_entry(
    data: TimeEntryCreate, current: CurrentUserDep, session: TenantSessionDep
) -> TimeEntryRead:
    return TimeEntryRead.model_validate(await _time_svc(current, session).create(data))


@router.patch(
    "/time-entries/{entry_id}",
    response_model=TimeEntryRead,
    dependencies=[require_permission("timeentry:create")],
)
async def update_time_entry(
    entry_id: uuid.UUID,
    data: TimeEntryUpdate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> TimeEntryRead:
    return TimeEntryRead.model_validate(await _time_svc(current, session).update(entry_id, data))


@router.delete(
    "/time-entries/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("timeentry:create")],
)
async def delete_time_entry(
    entry_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _time_svc(current, session).delete(entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/time-entries/{entry_id}/submit",
    response_model=TimeEntryRead,
    dependencies=[require_permission("timeentry:create")],
)
async def submit_time_entry(
    entry_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> TimeEntryRead:
    return TimeEntryRead.model_validate(await _time_svc(current, session).submit(entry_id))


@router.post(
    "/time-entries/approve",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("invoice:update")],
)
async def approve_time_entries(
    data: TimeEntryIds, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _time_svc(current, session).approve(data.entry_ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/time-entries/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("invoice:update")],
)
async def reject_time_entries(
    review: TimeEntryReject,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> Response:
    await _time_svc(current, session).approve(review.entry_ids, reject_reason=review.reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/time-entries/invoice",
    response_model=InvoiceDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("invoice:create")],
)
async def invoice_time_entries(
    data: TimeInvoiceCreate, current: CurrentUserDep, session: TenantSessionDep
) -> InvoiceDetail:
    return InvoiceDetail.model_validate(await _time_svc(current, session).invoice(data))


@router.get("/time-import/template", dependencies=[require_permission("timeentry:read")])
async def download_time_template(current: CurrentUserDep) -> Response:
    content = (
        "Date,Counsel Email,Matter Number,Client Name,Hours,Description,Activity Type,Billable\r\n"
        f"{date.today().strftime('%d/%m/%Y')},{current.email},M-0001,,1.5,"
        "Conference and case research,Research,Yes\r\n"
    )
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="vidhisangh-timesheet-template.csv"'},
    )


@router.post(
    "/time-import/preview",
    response_model=TimeImportPreview,
    dependencies=[require_permission("invoice:create")],
)
async def preview_time_import(
    current: CurrentUserDep,
    session: TenantSessionDep,
    file: Annotated[UploadFile, File(description="Excel .xlsx or CSV timesheet")],
) -> TimeImportPreview:
    payload = await read_limited(file)
    validate_upload(payload, file.content_type, file.filename)
    rows = normalise_rows(payload, file.filename or "timesheet.xlsx")
    rows, _ = await _time_svc(current, session).resolve_import(rows, create=False)
    return TimeImportPreview(
        filename=file.filename or "timesheet.xlsx",
        rows=rows,
        valid_count=sum(not row.errors for row in rows),
        error_count=sum(bool(row.errors) for row in rows),
    )


@router.post(
    "/time-import/commit",
    response_model=list[TimeEntryRead],
    dependencies=[require_permission("invoice:create")],
)
async def commit_time_import(
    data: TimeImportCommit, current: CurrentUserDep, session: TenantSessionDep
) -> list[TimeEntryRead]:
    rows, made = await _time_svc(current, session).resolve_import(data.rows, create=True)
    if any(row.errors for row in rows):
        raise ValidationError("Resolve all spreadsheet errors before importing.")
    return [TimeEntryRead.model_validate(entry) for entry in made]


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
    matter_id: uuid.UUID,
    data: MatterInvoicePrepare,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> InvoiceDetail:
    return InvoiceDetail.model_validate(
        await _svc(current, session).prepare_matter_invoice(matter_id, data)
    )


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
    invoices = await _svc(current, session).list_invoices(
        status_filter, page.limit, page.offset, client_id=client_id, matter_id=matter_id
    )
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
    return InvoiceDetail.model_validate(
        await _svc(current, session).update_invoice(invoice_id, data)
    )


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
    return InvoiceDetail.model_validate(
        await _svc(current, session).add_line_item(invoice_id, data)
    )


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


@router.post(
    "/invoices/{invoice_id}/follow-ups",
    response_model=InvoiceDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("invoice:update")],
)
async def add_follow_up(
    invoice_id: uuid.UUID,
    data: FollowUpCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> InvoiceDetail:
    return InvoiceDetail.model_validate(
        await _svc(current, session).add_follow_up(invoice_id, data)
    )


@router.post(
    "/invoices/{invoice_id}/receipts",
    response_model=InvoiceDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("invoice:update")],
)
async def record_receipt(
    invoice_id: uuid.UUID,
    data: ReceiptCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> InvoiceDetail:
    return InvoiceDetail.model_validate(
        await _svc(current, session).record_receipt(invoice_id, data)
    )


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
