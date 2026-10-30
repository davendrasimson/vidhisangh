"""Raise the draft copies that recurring invoices are due for.

Run from the nightly fee sweep (``app.modules.matters.fee_sweep``). A template
invoice (``recurrence`` set) whose ``next_issue_on`` has arrived gets a copy —
same client, matter, lines, tax position and payment terms, dated the due day,
numbered in the firm's sequence, status *draft* so someone looks before it goes
out — and its ``next_issue_on`` moves one period on (None once past
``recur_until``). A cancelled template stops. Copies never recur themselves.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.billing.models import RECURRENCE_MONTHS, Invoice, InvoiceRecurrence, InvoiceStatus
from app.modules.billing.schemas import InvoiceCreate, LineItemCreate
from app.modules.billing.service import BillingService, add_months

# A template that fell far behind (the sweep was down) catches up gradually.
MAX_COPIES_PER_RUN = 3


async def raise_due(session: AsyncSession, today: date) -> int:
    """Raise every copy due on or before ``today``; returns how many. Caller commits."""
    templates = list((await session.execute(
        select(Invoice).options(selectinload(Invoice.line_items)).where(
            Invoice.deleted_at.is_(None),
            Invoice.recurrence.is_not(None),
            Invoice.next_issue_on.is_not(None),
            Invoice.next_issue_on <= today,
            Invoice.status != InvoiceStatus.CANCELLED,
        ).order_by(Invoice.next_issue_on)
    )).scalars().all())
    raised = 0
    for template in templates:
        months = RECURRENCE_MONTHS[InvoiceRecurrence(template.recurrence)]
        svc = BillingService(session, template.created_by, template.tenant_id)
        copies = 0
        while template.next_issue_on is not None and template.next_issue_on <= today and copies < MAX_COPIES_PER_RUN:
            issue_on = template.next_issue_on
            terms = (template.due_date - template.issue_date).days if template.due_date and template.issue_date else None
            copy = await svc.create_invoice(InvoiceCreate(
                client_name=template.client_name,
                client_id=template.client_id,
                matter_id=template.matter_id,
                issue_date=issue_on,
                due_date=issue_on.fromordinal(issue_on.toordinal() + terms) if terms is not None else None,
                currency=template.currency,
                tax_rate=template.tax_rate,
                notes=template.notes,
                document_type=template.document_type,
                line_items=[
                    LineItemCreate(description=li.description, quantity=li.quantity, unit_price=li.unit_price)
                    for li in template.line_items
                ],
            ))
            copy.recurring_from_id = template.id
            following = add_months(issue_on, months)
            template.next_issue_on = None if template.recur_until and following > template.recur_until else following
            copies += 1
        raised += copies
    await session.flush()
    return raised
