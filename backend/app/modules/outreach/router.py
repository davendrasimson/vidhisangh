"""Outreach endpoints: one public unsubscribe, the rest for the platform admin."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select

from app.core.deps import AuthSessionDep, CurrentUserDep
from app.core.outreach_mail import OutreachMessage, get_outreach_sender
from app.core.pagination import Page, PageParams, page_params
from app.modules.identity.models import User
from app.modules.outreach import email as invitation
from app.modules.outreach import runner, service
from app.modules.outreach.models import OutreachStatus
from app.modules.support.service import require_platform_admin

router = APIRouter(tags=["Outreach"])


@router.post("/outreach/unsubscribe/{token}", status_code=204,
             summary="Unsubscribe from invitations (link, or one-click from the mail app)")
async def unsubscribe(token: str, session: AuthSessionDep) -> Response:
    # No sign-in and no body needed: Gmail/Outlook POST "List-Unsubscribe=One-Click"
    # here (RFC 8058). Unknown tokens answer the same, so the route reveals nothing.
    if len(token) <= 64:
        await service.unsubscribe(session, token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class OutreachSettingsUpdate(BaseModel):
    paused: bool | None = None
    daily_limit: int | None = Field(default=None, ge=0, le=500)


class TestSend(BaseModel):
    to: EmailStr | None = None


class RemovalRequest(BaseModel):
    note: str | None = Field(default=None, max_length=300)


class ContactRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    name: str | None
    mobile: str | None
    city: str | None
    court: str | None
    source: str
    status: OutreachStatus
    sent_at: datetime | None          # "approached on"
    unsubscribed_at: datetime | None
    joined_user_id: uuid.UUID | None
    removal_requested_at: datetime | None
    removal_note: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


Pagination = Annotated[PageParams, Depends(page_params)]
CONTACT_CSV_COLUMNS = ("email", "name", "mobile", "city", "court", "source", "status", "sent_at",
                       "unsubscribed_at", "removal_requested_at", "removal_note", "added_on")


async def _overview(session) -> dict:  # noqa: ANN001
    return {**await service.overview(session), "sending": runner.is_running()}


@router.get("/platform-admin/outreach", summary="Invitation campaign status")
async def outreach_overview(current: CurrentUserDep, session: AuthSessionDep) -> dict:
    require_platform_admin(current.is_superuser)
    return await _overview(session)


@router.patch("/platform-admin/outreach/settings", summary="Pause/resume and the daily number")
async def outreach_settings(data: OutreachSettingsUpdate, current: CurrentUserDep, session: AuthSessionDep) -> dict:
    require_platform_admin(current.is_superuser)
    await service.update_settings(session, paused=data.paused, daily_limit=data.daily_limit)
    return await _overview(session)


@router.post("/platform-admin/outreach/send-now", summary="Send today's invitations now (the rest of today's number)")
async def outreach_send_now(current: CurrentUserDep, session: AuthSessionDep) -> dict:
    """Starts the batch in the background and returns at once; the overview's
    `sent_today` shows progress. Sends even while scheduled sending is paused,
    never more than the daily number."""
    require_platform_admin(current.is_superuser)
    sender = get_outreach_sender()
    if sender is None:
        raise HTTPException(status_code=503, detail="The invitation mail service is not set up yet (VS_OUTREACH_SMTP_HOST).")
    planned = min(await service.budget_today(session), await service.queued_count(session))
    if planned <= 0:
        detail = ("Nobody is waiting to be invited: upload a CSV of contacts first."
                  if await service.queued_count(session) == 0 else "Today's number has already gone out; the rest go tomorrow.")
        raise HTTPException(status_code=409, detail=detail)
    if not runner.start(sender):
        raise HTTPException(status_code=409, detail="Today's invitations are already being sent.")
    return {"started": True, "planned": planned}


@router.post("/platform-admin/outreach/contacts", summary="Add contacts from a CSV (email, name, city, court, source)")
async def outreach_import(
    current: CurrentUserDep, session: AuthSessionDep,
    file: Annotated[UploadFile, File()], source: Annotated[str | None, Form()] = None,
) -> dict:
    require_platform_admin(current.is_superuser)
    from app.core.uploads import UploadTooLargeError, read_limited

    try:
        data = await read_limited(file, 5 * 1024 * 1024)
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail="The CSV must be under 5 MB.") from exc
    try:
        return await service.import_contacts(session, data, source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/platform-admin/outreach/contacts", response_model=Page[ContactRow],
            summary="The contacts list: who is queued, who was approached and when, who asked out")
async def outreach_contacts(
    current: CurrentUserDep, session: AuthSessionDep, page: Pagination,
    q: Annotated[str | None, Query(max_length=120)] = None,
    status_filter: Annotated[OutreachStatus | None, Query(alias="status")] = None,
) -> Page[ContactRow]:
    require_platform_admin(current.is_superuser)
    rows, total = await service.list_contacts(session, q=q, status=status_filter, limit=page.limit, offset=page.offset)
    return Page.create([ContactRow.model_validate(r) for r in rows], total, page)


@router.get("/platform-admin/outreach/contacts.csv", summary="The same list as a CSV (filters apply)")
async def outreach_contacts_csv(
    current: CurrentUserDep, session: AuthSessionDep,
    q: Annotated[str | None, Query(max_length=120)] = None,
    status_filter: Annotated[OutreachStatus | None, Query(alias="status")] = None,
) -> Response:
    require_platform_admin(current.is_superuser)
    rows, _ = await service.list_contacts(session, q=q, status=status_filter, limit=50_000, offset=0)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CONTACT_CSV_COLUMNS)
    for r in rows:
        writer.writerow([
            r.email, r.name or "", r.mobile or "", r.city or "", r.court or "", r.source, r.status,
            r.sent_at.isoformat() if r.sent_at else "", r.unsubscribed_at.isoformat() if r.unsubscribed_at else "",
            r.removal_requested_at.isoformat() if r.removal_requested_at else "", r.removal_note or "",
            r.created_at.isoformat(),
        ])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="outreach-contacts.csv"'})


@router.post("/platform-admin/outreach/contacts/{contact_id}/removal-request", response_model=ContactRow,
             summary="Flag a contact who asked to be taken off (suppressed, never emailed)")
async def outreach_removal_request(contact_id: uuid.UUID, data: RemovalRequest, current: CurrentUserDep, session: AuthSessionDep) -> ContactRow:
    require_platform_admin(current.is_superuser)
    contact = await service.request_removal(session, contact_id, data.note)
    if contact is None:
        raise HTTPException(status_code=404, detail="No such contact.")
    return ContactRow.model_validate(contact)


@router.delete("/platform-admin/outreach/contacts/{contact_id}", status_code=204,
               summary="Erase a contact's details for good (the address stays suppressed)")
async def outreach_erase(contact_id: uuid.UUID, current: CurrentUserDep, session: AuthSessionDep) -> Response:
    require_platform_admin(current.is_superuser)
    if not await service.erase_contact(session, contact_id):
        raise HTTPException(status_code=404, detail="No such contact.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/platform-admin/outreach/preview", summary="The invitation as recipients see it (HTML)")
async def outreach_preview(current: CurrentUserDep) -> Response:
    require_platform_admin(current.is_superuser)
    _, _, html = invitation.build(name="Adv. Priya Sharma", source="the Delhi High Court Bar Association directory", token="preview")
    return Response(content=html, media_type="text/html", headers={"Content-Security-Policy": "default-src 'none'; img-src https:; style-src 'unsafe-inline'"})


@router.post("/platform-admin/outreach/test", summary="Send the invitation to yourself")
async def outreach_test(data: TestSend, current: CurrentUserDep, session: AuthSessionDep) -> dict:
    require_platform_admin(current.is_superuser)
    sender = get_outreach_sender()
    if sender is None:
        raise HTTPException(status_code=503, detail="The invitation mail service is not set up yet (VS_OUTREACH_SMTP_HOST).")
    to = str(data.to or current.email or "")
    if not to:
        raise HTTPException(status_code=422, detail="Give an address to send the test to.")
    # The token principal carries no name; greet the admin by the account's name.
    name = await session.scalar(select(User.full_name).where(User.id == current.id))
    subject, text, html = invitation.build(name=name, source="a test sent from the admin panel", token="test")
    try:
        await sender.send(OutreachMessage(to=to, subject="[Test] " + subject, text=text, html=html,
                                          one_click_url=invitation.one_click_url("test"),
                                          unsubscribe_page=invitation.unsubscribe_url("test")))
    except Exception as exc:  # noqa: BLE001 - say what the relay said, instead of a bare 500
        raise HTTPException(status_code=502, detail=f"The mail service refused the test: {type(exc).__name__}: {exc}"[:400]) from exc
    return {"sent_to": to}
