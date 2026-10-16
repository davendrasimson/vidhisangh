"""Outreach endpoints: one public unsubscribe, the rest for the platform admin."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, EmailStr, Field

from app.core.deps import AuthSessionDep, CurrentUserDep
from app.core.outreach_mail import OutreachMessage, get_outreach_sender
from app.modules.outreach import email as invitation
from app.modules.outreach import service
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


@router.get("/platform-admin/outreach", summary="Invitation campaign status")
async def outreach_overview(current: CurrentUserDep, session: AuthSessionDep) -> dict:
    require_platform_admin(current.is_superuser)
    return await service.overview(session)


@router.patch("/platform-admin/outreach/settings", summary="Pause/resume and the daily number")
async def outreach_settings(data: OutreachSettingsUpdate, current: CurrentUserDep, session: AuthSessionDep) -> dict:
    require_platform_admin(current.is_superuser)
    await service.update_settings(session, paused=data.paused, daily_limit=data.daily_limit)
    return await service.overview(session)


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


@router.get("/platform-admin/outreach/preview", summary="The invitation as recipients see it (HTML)")
async def outreach_preview(current: CurrentUserDep) -> Response:
    require_platform_admin(current.is_superuser)
    _, _, html = invitation.build(name="Adv. Priya Sharma", source="the Delhi High Court Bar Association directory", token="preview")
    return Response(content=html, media_type="text/html", headers={"Content-Security-Policy": "default-src 'none'; img-src https:; style-src 'unsafe-inline'"})


@router.post("/platform-admin/outreach/test", summary="Send the invitation to yourself")
async def outreach_test(data: TestSend, current: CurrentUserDep) -> dict:
    require_platform_admin(current.is_superuser)
    sender = get_outreach_sender()
    if sender is None:
        raise HTTPException(status_code=503, detail="The invitation mail service is not set up yet (VS_OUTREACH_SMTP_HOST).")
    to = str(data.to or current.email or "")
    if not to:
        raise HTTPException(status_code=422, detail="Give an address to send the test to.")
    subject, text, html = invitation.build(name=current.full_name, source="a test sent from the admin panel", token="test")
    await sender.send(OutreachMessage(to=to, subject="[Test] " + subject, text=text, html=html,
                                      one_click_url=invitation.one_click_url("test"),
                                      unsubscribe_page=invitation.unsubscribe_url("test")))
    return {"sent_to": to}
