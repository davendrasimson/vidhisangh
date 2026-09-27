"""Payments HTTP endpoints — order creation, verification, webhook, listing."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from app.core.deps import (
    require_flag,
    AuthSessionDep,
    CurrentUserDep,
    TenantSessionDep,
    require_permission,
)
from app.core.exceptions import TenantError
from app.core.pagination import PageParams, page_params
from app.core.payments import PaymentProvider, get_payment_provider
from app.modules.payments.schemas import (
    OrderCreate,
    OrderResponse,
    PaymentRead,
    PaymentVerify,
)
from app.modules.payments.service import PaymentService, handle_webhook

router = APIRouter(prefix="/payments", tags=["Payments"])

Pagination = Annotated[PageParams, Depends(page_params)]
PaymentProviderDep = Annotated[PaymentProvider, Depends(get_payment_provider)]


def _svc(
    current: CurrentUserDep, session: TenantSessionDep, provider: PaymentProviderDep
) -> PaymentService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return PaymentService(session, current.id, current.tenant_id, provider)


@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a payment order (opens Razorpay Checkout on the client)",
    dependencies=[require_flag("online_payments"), require_permission("invoice:create")],
)
async def create_order(
    data: OrderCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
    provider: PaymentProviderDep,
) -> OrderResponse:
    payment = await _svc(current, session, provider).create_order(data)
    return OrderResponse(
        payment_id=payment.id,
        order_id=payment.provider_order_id,
        key_id=provider.public_key,
        amount=payment.amount,
        currency=payment.currency,
        provider=payment.provider,
    )


@router.post(
    "/{payment_id}/verify",
    response_model=PaymentRead,
    summary="Verify a completed checkout (signature)",
    dependencies=[require_flag("online_payments"), require_permission("invoice:create")],
)
async def verify_payment(
    payment_id: uuid.UUID,
    data: PaymentVerify,
    current: CurrentUserDep,
    session: TenantSessionDep,
    provider: PaymentProviderDep,
) -> PaymentRead:
    payment = await _svc(current, session, provider).verify(payment_id, data)
    return PaymentRead.model_validate(payment)


@router.post(
    "/webhook",
    summary="Razorpay webhook (signature-authenticated; no login)",
)
async def webhook(
    request: Request,
    session: AuthSessionDep,
    provider: PaymentProviderDep,
    x_razorpay_signature: Annotated[str | None, Header()] = None,
) -> dict:
    body = await request.body()
    return await handle_webhook(session, provider, body=body, signature=x_razorpay_signature)


@router.get(
    "",
    response_model=list[PaymentRead],
    summary="List payments",
    dependencies=[require_flag("online_payments"), require_permission("invoice:read")],
)
async def list_payments(
    page: Pagination,
    current: CurrentUserDep,
    session: TenantSessionDep,
    provider: PaymentProviderDep,
) -> list[PaymentRead]:
    payments = await _svc(current, session, provider).list(page.limit, page.offset)
    return [PaymentRead.model_validate(p) for p in payments]


@router.get(
    "/{payment_id}",
    response_model=PaymentRead,
    summary="Payment detail",
    dependencies=[require_flag("online_payments"), require_permission("invoice:read")],
)
async def get_payment(
    payment_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    provider: PaymentProviderDep,
) -> PaymentRead:
    payment = await _svc(current, session, provider).get(payment_id)
    return PaymentRead.model_validate(payment)
