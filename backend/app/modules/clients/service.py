"""Client master service — clients, tax defaults, and the KYC form flow."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.channels import ChannelMessage, get_channels
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.clients.kyc import (
    BUSINESS_TYPES,
    GST_STATE_CODES,
    STATE_NAME_TO_CODE,
    TDS_SECTIONS,
    Issue,
    validate_client,
)
from app.modules.clients.models import (
    Client,
    ClientKind,
    ClientKycRequest,
    ClientStatus,
    GstTreatment,
    KycRequestStatus,
    KycStatus,
)
from app.modules.clients.repository import ClientRepository
from app.modules.clients.schemas import (
    KYC_FIELDS,
    ClientCreate,
    ClientUpdate,
    KycApply,
    KycRequestCreate,
    KycSubmission,
)
from app.modules.identity.models import User
from app.modules.tenancy.models import Tenant
from app.modules.notifications.models import NotificationChannel, NotificationType
from app.modules.notifications.service import create_notification

log = structlog.get_logger("app.clients")


def _client_dict(client: Client) -> dict:
    """The validatable/editable view of a client as plain values."""
    out: dict = {}
    for f in KYC_FIELDS + ("client_code", "status", "notes", "tags"):
        v = getattr(client, f)
        if isinstance(v, Decimal):
            v = float(v)
        elif hasattr(v, "isoformat"):
            v = v.isoformat()
        out[f] = v
    out["kind"] = str(client.kind)
    return out


def _jsonable(value):  # noqa: ANN001, ANN202
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def client_issues(client: Client) -> list[Issue]:
    return validate_client(str(client.kind), _client_dict(client))


class ClientService:
    """Firm-side: JWT + RBAC, tenant-scoped."""

    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.repo = ClientRepository(session)

    async def _require(self, client_id: uuid.UUID) -> Client:
        client = await self.repo.get(self.tenant_id, client_id)
        if client is None:
            raise NotFoundError("Client not found.")
        return client

    # ── Clients ───────────────────────────────────────────────────
    async def create(self, data: ClientCreate) -> Client:
        values = data.model_dump(exclude_unset=True, exclude={"kind"})
        self._apply_defaults(data.kind, values)
        client = Client(
            tenant_id=self.tenant_id, kind=data.kind,
            created_by=self.user_id, updated_by=self.user_id, **values,
        )
        self._record_consent(client, values, source="staff")
        self.repo.add(client)
        await self.session.flush()
        await self.session.refresh(client)
        return client

    async def update(self, client_id: uuid.UUID, data: ClientUpdate) -> Client:
        client = await self._require(client_id)
        values = data.model_dump(exclude_unset=True)
        if "kind" in values and values["kind"] is not None:
            client.kind = values.pop("kind")
        else:
            values.pop("kind", None)
        self._apply_defaults(client.kind, values, existing=client)
        for k, v in values.items():
            setattr(client, k, v)
        self._record_consent(client, values, source="staff")
        client.updated_by = self.user_id
        await self.session.flush()
        await self.session.refresh(client)
        return client

    async def get(self, client_id: uuid.UUID) -> Client:
        return await self._require(client_id)

    async def list(self, *, q: str | None, kind: ClientKind | None, status: ClientStatus | None) -> list[Client]:
        return await self.repo.list(self.tenant_id, q=q, kind=kind, status=status)

    async def delete(self, client_id: uuid.UUID) -> None:
        client = await self._require(client_id)
        client.deleted_at = datetime.now(UTC)
        await self.session.flush()

    @staticmethod
    def _apply_defaults(kind: ClientKind | str, values: dict, existing: Client | None = None) -> None:
        """Derive what follows from what was given."""
        # State code from the state name (and vice versa) for GST.
        state = values.get("state") or (existing.state if existing else None)
        if state and not values.get("state_code"):
            code = STATE_NAME_TO_CODE.get(state.strip().lower())
            if code:
                values["state_code"] = code
        if values.get("gstin") and not values.get("place_of_supply_code"):
            values["place_of_supply_code"] = values["gstin"][:2]
        # A GSTIN implies GST applies and, absent a choice, a regular registration.
        if values.get("gstin"):
            values.setdefault("gst_applicable", True)
            if not values.get("gst_treatment") and not (existing and existing.gst_treatment != GstTreatment.UNREGISTERED):
                values["gst_treatment"] = GstTreatment.REGISTERED_REGULAR
        # Legal services to a business entity: reverse charge by default — when
        # the client is created GST-registered, or becomes so (e.g. via KYC).
        if (
            str(kind) == "business" and values.get("gst_applicable") and "reverse_charge" not in values
            and (existing is None or not existing.gst_applicable)
        ):
            values["reverse_charge"] = True
        # Display name falls out of the parts when not given.
        if not values.get("display_name") and existing is None:
            if str(kind) == "business":
                values["display_name"] = values.get("legal_name") or values.get("trade_name") or "New business"
            else:
                values["display_name"] = " ".join(x for x in (values.get("first_name"), values.get("last_name")) if x) or "New client"

    @staticmethod
    def _record_consent(client: Client, values: dict, *, source: str) -> None:
        if any(k in values for k in ("consent_email", "consent_mobile", "consent_whatsapp")):
            client.consent_recorded_at = datetime.now(UTC)
            client.consent_source = source

    # ── KYC requests ──────────────────────────────────────────────
    async def kyc_requests(self, client_id: uuid.UUID) -> list[ClientKycRequest]:
        await self._require(client_id)
        return await self.repo.kyc_requests(self.tenant_id, client_id)

    async def kyc_request(self, client_id: uuid.UUID, request_id: uuid.UUID) -> ClientKycRequest:
        req = await self.repo.kyc_request(self.tenant_id, client_id, request_id)
        if req is None:
            raise NotFoundError("KYC request not found.")
        return req

    async def create_kyc_request(self, client_id: uuid.UUID, data: KycRequestCreate) -> ClientKycRequest:
        client = await self._require(client_id)
        # One open request at a time: sending again supersedes the previous link.
        for old in await self.repo.kyc_requests(self.tenant_id, client_id):
            if old.status == KycRequestStatus.SENT:
                old.status = KycRequestStatus.CANCELLED
        req = ClientKycRequest(
            tenant_id=self.tenant_id,
            client_id=client.id,
            token=secrets.token_urlsafe(32),
            sent_to_email=(data.send_to_email or client.email or client.contact_person_email),
            sent_to_mobile=(data.send_to_mobile or client.mobile or client.contact_person_mobile),
            message=data.message,
            expires_at=datetime.now(UTC) + timedelta(days=data.expires_in_days),
            prefill={k: _jsonable(v) for k, v in _client_dict(client).items() if k in KYC_FIELDS},
            initiated_by=self.user_id,
        )
        self.repo.add(req)
        client.kyc_status = KycStatus.PENDING
        await self.session.flush()
        await self.session.refresh(req)
        await self._email_kyc_link(client, req)
        return req

    async def _email_kyc_link(self, client: Client, req: ClientKycRequest) -> None:
        if not req.sent_to_email:
            return
        firm = await self.session.scalar(select(Tenant.name).where(Tenant.id == self.tenant_id))
        provider = get_channels().provider_for(NotificationChannel.EMAIL)
        if provider is None:
            return
        try:
            await provider.send(ChannelMessage(
                to_email=req.sent_to_email,
                to_name=client.display_name,
                subject=f"{firm or 'Your advocate'} — please confirm your details (KYC)",
                body=(
                    f"Dear {client.display_name},\n\n"
                    f"{firm or 'We'} need your details for our records and invoicing. "
                    f"Please review and complete the form at the link below. It expires on "
                    f"{req.expires_at.strftime('%d/%m/%Y')}.\n\n"
                    + (f"{req.message}\n\n" if req.message else "")
                    + f"{kyc_url(req.token)}\n"
                ),
                link=kyc_url(req.token),
            ))
        except Exception as exc:  # noqa: BLE001 — the link is still shown in the app
            log.warning("kyc_email_failed", error=str(exc))

    async def cancel_kyc_request(self, client_id: uuid.UUID, request_id: uuid.UUID) -> ClientKycRequest:
        req = await self.kyc_request(client_id, request_id)
        if req.status in (KycRequestStatus.SENT, KycRequestStatus.SUBMITTED):
            req.status = KycRequestStatus.CANCELLED
            client = await self._require(client_id)
            if client.kyc_status in (KycStatus.PENDING, KycStatus.SUBMITTED):
                client.kyc_status = KycStatus.NOT_STARTED if client.kyc_verified_at is None else KycStatus.VERIFIED
            await self.session.flush()
        return req

    @staticmethod
    def changes(client: Client, req: ClientKycRequest) -> list[dict]:
        """Field-by-field diff between the record and the submission."""
        if not req.submitted_data:
            return []
        current = _client_dict(client)
        out = []
        for field in KYC_FIELDS:
            if field not in req.submitted_data:
                continue
            new, old = _jsonable(req.submitted_data.get(field)), _jsonable(current.get(field))
            if (new or None) != (old or None):
                out.append({"field": field, "current": old, "submitted": new})
        return out

    async def apply_kyc(self, client_id: uuid.UUID, request_id: uuid.UUID, data: KycApply) -> Client:
        """The initiator accepts the submission: copy it onto the record."""
        client = await self._require(client_id)
        req = await self.kyc_request(client_id, request_id)
        if req.status != KycRequestStatus.SUBMITTED or not req.submitted_data:
            raise ValidationError("This request has no submission to apply.")
        wanted = set(data.fields) if data.fields else set(KYC_FIELDS)
        values = {k: v for k, v in req.submitted_data.items() if k in wanted and k in KYC_FIELDS}
        for k in ("date_of_birth", "incorporation_date"):
            if values.get(k):
                values[k] = datetime.fromisoformat(values[k]).date()
        self._apply_defaults(client.kind, values, existing=client)
        for k, v in values.items():
            setattr(client, k, v)
        self._record_consent(client, values, source="kyc_form")
        now = datetime.now(UTC)
        req.status = KycRequestStatus.APPLIED
        req.applied_at = now
        req.applied_by = self.user_id
        if data.mark_verified:
            client.kyc_status = KycStatus.VERIFIED
            client.kyc_verified_at = now
            client.kyc_verified_by = self.user_id
        client.updated_by = self.user_id
        await self.session.flush()
        await self.session.refresh(client)
        return client


def kyc_url(token: str) -> str:
    return f"{settings.PUBLIC_APP_URL.rstrip('/')}/kyc/{token}"


class PublicKycService:
    """The client's side: authenticated by the token, on a bypass-RLS session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ClientRepository(session)

    async def resolve(self, token: str) -> tuple[ClientKycRequest, Client]:
        req = await self.repo.kyc_by_token(token)
        if req is None:
            raise NotFoundError("This KYC link is not valid.")
        expires = req.expires_at if req.expires_at.tzinfo else req.expires_at.replace(tzinfo=UTC)  # SQLite: naive
        if req.status == KycRequestStatus.SENT and expires < datetime.now(UTC):
            req.status = KycRequestStatus.EXPIRED
            await self.session.flush()
        client = await self.repo.client_any_tenant(req.client_id)
        if client is None:
            raise NotFoundError("This KYC link is not valid.")
        return req, client

    async def view(self, token: str) -> dict:
        req, client = await self.resolve(token)
        firm = await self.session.scalar(select(Tenant.name).where(Tenant.id == req.tenant_id))
        return {
            "firm_name": firm or "Your advocate",
            "client_kind": client.kind,
            "display_name": client.display_name,
            "message": req.message,
            "expires_at": req.expires_at,
            "status": req.status,
            "prefill": req.prefill,
            "tds_sections": TDS_SECTIONS,
            "business_types": BUSINESS_TYPES,
            "states": [{"code": c, "name": n} for c, n in GST_STATE_CODES.items()],
        }

    async def submit(self, token: str, data: KycSubmission, *, ip: str | None) -> tuple[ClientKycRequest, list[Issue]]:
        req, client = await self.resolve(token)
        if req.status != KycRequestStatus.SENT:
            raise ValidationError(
                "This form has already been submitted." if req.status == KycRequestStatus.SUBMITTED
                else "This KYC link has expired or was withdrawn. Please ask for a new one."
            )
        if not data.declaration_accepted:
            raise ValidationError("Please confirm that the details are true and complete.")
        submitted = {k: _jsonable(v) for k, v in data.model_dump(exclude_unset=True, exclude={"declaration_accepted"}).items() if k in KYC_FIELDS}
        # Consent is explicit on the form; record what was ticked even if false.
        for k in ("consent_email", "consent_mobile", "consent_whatsapp"):
            submitted[k] = bool(getattr(data, k))
        merged = {**req.prefill, **submitted}
        issues = validate_client(str(client.kind), merged)
        req.submitted_data = submitted
        req.submitted_at = datetime.now(UTC)
        req.submitted_ip = ip
        req.issues = [i.dict() for i in issues]
        req.status = KycRequestStatus.SUBMITTED
        client.kyc_status = KycStatus.SUBMITTED
        await self.session.flush()
        await self._notify_initiator(req, client, issues)
        return req, issues

    async def _notify_initiator(self, req: ClientKycRequest, client: Client, issues: list[Issue]) -> None:
        problems = sum(1 for i in issues if i.severity == "error")
        summary = f"{client.display_name} submitted their KYC form" + (f" — {problems} item(s) need a look" if problems else " — all checks passed")
        link = f"/app/clients/{client.id}?kyc={req.id}"
        try:
            await create_notification(
                self.session, user_id=req.initiated_by, type=NotificationType.KYC_SUBMITTED,
                message=summary, actor_name=client.display_name, link=link,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("kyc_notify_failed", error=str(exc))
        initiator = await self.session.scalar(select(User).where(User.id == req.initiated_by))
        provider = get_channels().provider_for(NotificationChannel.EMAIL)
        if initiator is not None and initiator.email and provider is not None:
            try:
                await provider.send(ChannelMessage(
                    to_email=initiator.email, to_name=initiator.full_name,
                    subject=f"KYC submitted: {client.display_name}",
                    body=f"{summary}.\n\nReview and apply it here: {settings.PUBLIC_APP_URL.rstrip('/')}{link}\n",
                    link=f"{settings.PUBLIC_APP_URL.rstrip('/')}{link}",
                ))
            except Exception as exc:  # noqa: BLE001
                log.warning("kyc_initiator_email_failed", error=str(exc))
