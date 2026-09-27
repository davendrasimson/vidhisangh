"""Client master service — clients, tax defaults, the KYC form flow, the
consent ledger, per-client export and erasure (DPDP s.11–s.12)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.core.channels import ChannelMessage, get_channels
from app.core.config import settings
from app.core.security import hash_link_token
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.modules.audit.service import record_audit
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
    LawfulBasis,
)
from app.modules.clients.repository import ClientRepository
from app.modules.clients.schemas import (
    KYC_FIELDS,
    ClientCreate,
    ClientUpdate,
    ConsentEventCreate,
    KycApply,
    KycRequestCreate,
    KycSubmission,
    PrivacyNoticeSummary,
)
from app.modules.identity.models import User
from app.modules.notifications.models import NotificationChannel, NotificationType
from app.modules.notifications.service import create_notification, send_to_client
from app.modules.privacy.config import privacy_setting
from app.modules.privacy.consent import (
    coarse_ip,
    consent_history,
    record_consent_event,
    record_flag_changes,
)
from app.modules.privacy.models import ClientConsentEvent, ConsentPurpose, ConsentSource, PrivacyRequest
from app.modules.tenancy.models import Tenant

log = structlog.get_logger("app.clients")

ERASED_CLIENT_NAME = "Erased client"


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
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def client_issues(client: Client) -> list[Issue]:
    return validate_client(str(client.kind), _client_dict(client))


def notice_summary() -> PrivacyNoticeSummary:
    """The DPDP s.5 notice block shown on the KYC form (and the notice page)."""
    base = settings.PUBLIC_APP_URL.rstrip("/")
    return PrivacyNoticeSummary(
        version=str(privacy_setting("CURRENT_PRIVACY_NOTICE_VERSION")),
        purposes=[
            "Identifying you and keeping the firm's client records accurate (KYC).",
            "Conducting your matter: filings, correspondence and court work.",
            "Invoicing you correctly under GST and TDS law.",
            "Contacting you about your matter through the channels you tick.",
        ],
        retention=(
            f"Client and matter records are kept for the duration of the engagement and for "
            f"{privacy_setting('LEGAL_HOLD_YEARS')} years after the matter closes (limitation and "
            "professional record-keeping), then erased on request or by schedule."
        ),
        rights=[
            "Access a copy of the personal data held about you.",
            "Have inaccurate data corrected.",
            "Withdraw consent for any contact channel at any time (the original grant stays on record).",
            "Ask for erasure once the legal retention period ends.",
            "Raise a grievance with the firm, then with the Data Protection Board of India.",
        ],
        grievance_officer={
            "name": str(privacy_setting("GRIEVANCE_OFFICER_NAME")),
            "email": str(privacy_setting("GRIEVANCE_OFFICER_EMAIL")),
            "address": str(privacy_setting("GRIEVANCE_OFFICER_ADDRESS")),
        },
        notice_url=f"{base}/privacy",
        firm_is_fiduciary=True,
    )


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
        consent = {k: values.pop(k) for k in ("consent_email", "consent_mobile", "consent_whatsapp") if k in values}
        client = Client(
            tenant_id=self.tenant_id, kind=data.kind,
            created_by=self.user_id, updated_by=self.user_id, **values,
        )
        self.repo.add(client)
        await self.session.flush()
        # A consent ticked at creation is an event like any other (staff source).
        record_flag_changes(self.session, client=client, values=consent, source=ConsentSource.STAFF, actor_id=self.user_id)
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
        # Consent flags are never written directly: each change is an event and
        # the flag follows from it (a withdrawal keeps the original grant).
        consent = {k: values.pop(k) for k in ("consent_email", "consent_mobile", "consent_whatsapp") if k in values}
        for k, v in values.items():
            setattr(client, k, v)
        record_flag_changes(self.session, client=client, values=consent, source=ConsentSource.STAFF, actor_id=self.user_id)
        client.updated_by = self.user_id
        await self.session.flush()
        await self.session.refresh(client)
        return client

    async def get(self, client_id: uuid.UUID) -> Client:
        return await self._require(client_id)

    async def list(self, *, q: str | None, kind: ClientKind | None, status: ClientStatus | None) -> list[Client]:
        return await self.repo.list(self.tenant_id, q=q, kind=kind, status=status)

    async def delete(self, client_id: uuid.UUID) -> None:
        """Soft delete: the record stays for the legal retention period."""
        client = await self._require(client_id)
        client.deleted_at = datetime.now(UTC)
        await self.session.flush()

    # ── Erasure (DPDP s.12) ───────────────────────────────────────
    async def legal_holds(self, client_id: uuid.UUID) -> list[dict]:
        """Matters that block erasure: open, or closed within the hold period."""
        from app.modules.matters.models import Matter, MatterStatus

        years = int(privacy_setting("LEGAL_HOLD_YEARS"))
        cutoff = datetime.now(UTC) - timedelta(days=365 * years)
        rows = (await self.session.execute(
            select(Matter).where(Matter.tenant_id == self.tenant_id, Matter.client_id == client_id, Matter.deleted_at.is_(None))
        )).scalars().all()
        holds: list[dict] = []
        for m in rows:
            if m.status != MatterStatus.CLOSED:
                holds.append({"matter_id": str(m.id), "matter_number": m.matter_number, "reason": "open"})
                continue
            closed = m.disposal_date or (m.updated_at.date() if m.updated_at else None)
            if closed is None or datetime.combine(closed, datetime.min.time(), tzinfo=UTC) > cutoff:
                holds.append({
                    "matter_id": str(m.id), "matter_number": m.matter_number,
                    "reason": f"closed within the {years}-year retention period",
                    "closed_on": closed.isoformat() if closed else None,
                })
        return holds

    async def erase(
        self, client_id: uuid.UUID, *, override_legal_hold: bool, reason: str | None, actor_label: str | None,
        may_override: bool,
    ) -> dict:
        """Hard-delete the client and its identity data; unlink (never delete)
        the matters, documents, drafts, invoices and leads that referenced it.

        Refused (409) while any matter is open or closed inside the legal hold
        period, unless a ``tenant:manage`` holder overrides with a recorded reason.
        """
        from app.modules.billing.models import Invoice
        from app.modules.crm.models import Lead
        from app.modules.documents.models import Document
        from app.modules.drafting.models import Draft
        from app.modules.matters.models import Matter

        client = await self._require(client_id)
        holds = await self.legal_holds(client_id)
        overridden = False
        if holds:
            if not override_legal_hold:
                raise ConflictError(
                    "This client's data is under legal hold (open matters or matters closed within the "
                    "retention period). Close the matters or override the hold with a recorded reason.",
                    details={"legal_holds": holds},
                )
            if not may_override:
                raise PermissionDeniedError("Overriding a legal hold requires the tenant:manage permission.")
            if not (reason or "").strip():
                raise ValidationError("A reason is required to override a legal hold.")
            overridden = True

        unlinked: dict[str, int] = {}
        tid = self.tenant_id
        for label, model, extra in (
            ("matters", Matter, {"client_name": ERASED_CLIENT_NAME}),
            ("invoices", Invoice, {"client_name": ERASED_CLIENT_NAME}),
            ("documents", Document, {}),
            ("drafts", Draft, {}),
            ("leads", Lead, {}),
        ):
            res = await self.session.execute(
                update(model).where(model.tenant_id == tid, model.client_id == client_id)
                .values(client_id=None, **extra).execution_options(synchronize_session=False)
            )
            unlinked[label] = res.rowcount or 0
        await self.session.execute(
            update(PrivacyRequest).where(PrivacyRequest.tenant_id == tid, PrivacyRequest.client_id == client_id)
            .values(client_id=None).execution_options(synchronize_session=False)
        )
        await self.session.execute(delete(ClientConsentEvent).where(ClientConsentEvent.client_id == client_id))
        await self.session.execute(delete(ClientKycRequest).where(ClientKycRequest.client_id == client_id))
        display = client.display_name
        await self.session.delete(client)
        record_audit(
            self.session, tenant_id=tid, actor_id=self.user_id, actor_label=actor_label,
            action="client.erased", entity_type="client", entity_id=str(client_id),
            summary=f"Erased client record {display!r} (DPDP s.12)",
            meta={"legal_hold_overridden": overridden, "reason": reason, "legal_holds": holds, "unlinked": unlinked},
        )
        await self.session.flush()
        log.info("client_erased", client_id=str(client_id), overridden=overridden)
        return {"client_id": client_id, "erased": True, "unlinked": unlinked, "legal_hold_overridden": overridden}

    # ── Export (DPDP s.11) ────────────────────────────────────────
    async def export(self, client_id: uuid.UUID) -> dict:
        from app.modules.billing.models import Invoice
        from app.modules.crm.models import Lead
        from app.modules.documents.models import Document
        from app.modules.drafting.models import Draft
        from app.modules.matters.models import Matter
        from app.modules.privacy.export import row_dict

        client = await self._require(client_id)
        tid = self.tenant_id

        async def rows(model, *cols):  # noqa: ANN001, ANN202
            res = await self.session.execute(
                select(model).where(model.tenant_id == tid, model.client_id == client_id, model.deleted_at.is_(None))
            )
            return [row_dict(r, only=cols or None) for r in res.scalars().all()]

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "subject": "client",
            "client": row_dict(client, exclude={"pan_bidx", "gstin_bidx", "email_bidx"}),
            "kyc_requests": [
                row_dict(r, exclude={"token"}) for r in await self.repo.kyc_requests(tid, client_id)
            ],
            "consent_events": [row_dict(e) for e in await consent_history(self.session, tid, client_id)],
            "matters": await rows(Matter, "id", "matter_number", "title", "status", "stage", "court", "case_number", "opened_on", "disposal_date", "created_at"),
            "documents": await rows(Document, "id", "name", "content_type", "size", "matter_id", "version_count", "created_at"),
            "drafts": await rows(Draft, "id", "title", "status", "matter_id", "word_count", "created_at"),
            "invoices": await rows(Invoice, "id", "invoice_number", "status", "issue_date", "due_date", "total", "amount_paid", "created_at"),
            "leads": await rows(Lead, "id", "name", "status", "source", "created_at"),
            "privacy_requests": [
                row_dict(r) for r in (await self.session.execute(
                    select(PrivacyRequest).where(PrivacyRequest.tenant_id == tid, PrivacyRequest.client_id == client_id)
                )).scalars().all()
            ],
        }

    # ── Consent ledger ────────────────────────────────────────────
    async def consents(self, client_id: uuid.UUID) -> list[ClientConsentEvent]:
        await self._require(client_id)
        return await consent_history(self.session, self.tenant_id, client_id)

    async def record_consent(self, client_id: uuid.UUID, data: ConsentEventCreate, *, ip: str | None = None) -> ClientConsentEvent:
        client = await self._require(client_id)
        if data.purpose == ConsentPurpose.GUARDIAN_CONSENT and data.granted and not client.guardian_name:
            raise ValidationError("Record the guardian's name on the client before recording their consent.")
        event = record_consent_event(
            self.session, client=client, purpose=data.purpose, granted=data.granted,
            source=ConsentSource.STAFF, actor_id=self.user_id, ip=ip, note=data.note,
            notice_version=str(privacy_setting("CURRENT_PRIVACY_NOTICE_VERSION")),
        )
        client.updated_by = self.user_id
        await self.session.flush()
        await self.session.refresh(event)
        return event

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
        # DPDP s.9: a minor's data is processed only with verifiable guardian consent.
        if client.is_minor and client.guardian_consent_recorded_at is None:
            raise ValidationError(
                "This client is a minor. Record the parent's or guardian's consent "
                "(consent purpose 'guardian_consent') before sending a KYC form."
            )
        # One open request at a time: sending again supersedes the previous link.
        for old in await self.repo.kyc_requests(self.tenant_id, client_id):
            if old.status == KycRequestStatus.SENT:
                old.status = KycRequestStatus.CANCELLED
        raw_token = secrets.token_urlsafe(32)
        req = ClientKycRequest(
            tenant_id=self.tenant_id,
            client_id=client.id,
            token=None,
            token_hash=hash_link_token(raw_token),
            sent_to_email=(data.send_to_email or client.email or client.contact_person_email),
            sent_to_mobile=(data.send_to_mobile or client.mobile or client.contact_person_mobile),
            message=data.message,
            expires_at=datetime.now(UTC) + timedelta(days=data.expires_in_days),
            lawful_basis=LawfulBasis.CONTRACT,
            prefill={k: _jsonable(v) for k, v in _client_dict(client).items() if k in KYC_FIELDS},
            initiated_by=self.user_id,
        )
        self.repo.add(req)
        client.kyc_status = KycStatus.PENDING
        await self.session.flush()
        await self.session.refresh(req)
        # Expose the raw token on this instance only (for the email and the
        # creation response) without marking the row dirty — the DB keeps the hash.
        set_committed_value(req, "token", raw_token)
        await self._email_kyc_link(client, req)
        return req

    async def _email_kyc_link(self, client: Client, req: ClientKycRequest) -> None:
        if not req.sent_to_email:
            return
        firm = await self.session.scalar(select(Tenant.name).where(Tenant.id == self.tenant_id))
        # The KYC link is necessary for the engagement itself (DPDP s.7: the
        # purpose the client approached the firm for), so it is sent on the
        # basis of the contract — recorded on the request — not marketing consent.
        outcome = await send_to_client(
            self.session,
            client_id=client.id,
            channel=NotificationChannel.EMAIL,
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
            basis=str(req.lawful_basis),
        )
        if outcome != "sent":
            log.warning("kyc_email_not_sent", outcome=outcome, client_id=str(client.id))

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
                values[k] = date.fromisoformat(str(values[k])[:10])
        self._apply_defaults(client.kind, values, existing=client)
        consent = {k: values.pop(k) for k in ("consent_email", "consent_mobile", "consent_whatsapp") if k in values}
        for k, v in values.items():
            setattr(client, k, v)
        # What the client ticked on the form — every explicit answer is recorded,
        # with the notice version they saw and the (coarsened) submitting network.
        record_flag_changes(
            self.session, client=client, values=consent, source=ConsentSource.KYC_FORM,
            actor_id=None, notice_version=req.notice_version, ip_coarse=req.submitted_ip, only_changes=False,
        )
        now = datetime.now(UTC)
        req.status = KycRequestStatus.APPLIED
        req.applied_at = now
        req.applied_by = self.user_id
        # The record now holds the data; the copy the client saw is no longer needed.
        req.prefill = None
        if data.mark_verified:
            client.kyc_status = KycStatus.VERIFIED
            client.kyc_verified_at = now
            client.kyc_verified_by = self.user_id
        client.updated_by = self.user_id
        await self.session.flush()
        await self.session.refresh(client)
        return client


def kyc_url(token: str | None) -> str | None:
    """The public form link. Only the raw token at creation time can build it —
    stored requests hold a hash, so for them this is ``None``."""
    if not token:
        return None
    return f"{settings.PUBLIC_APP_URL.rstrip('/')}/kyc/{token}"


class PublicKycService:
    """The client's side: authenticated by the token, on a bypass-RLS session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ClientRepository(session)

    async def resolve(self, token: str) -> tuple[ClientKycRequest, Client]:
        req = await self.repo.kyc_by_token_hash(hash_link_token(token))
        if req is None:
            raise NotFoundError("This KYC link is not valid.")
        expires = req.expires_at if req.expires_at.tzinfo else req.expires_at.replace(tzinfo=UTC)  # SQLite: naive
        if req.status == KycRequestStatus.SENT and expires < datetime.now(UTC):
            req.status = KycRequestStatus.EXPIRED
            # Commit before the (fallible) rest of the request so the marker is
            # not rolled back with a later error (audit A-23).
            await self.session.commit()
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
            "prefill": req.prefill or {},
            "tds_sections": TDS_SECTIONS,
            "business_types": BUSINESS_TYPES,
            "states": [{"code": c, "name": n} for c, n in GST_STATE_CODES.items()],
            "notice": notice_summary(),
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
        submitted = {
            k: _jsonable(v)
            for k, v in data.model_dump(exclude_unset=True, exclude={"declaration_accepted", "notice_version"}).items()
            if k in KYC_FIELDS
        }
        # Consent is explicit on the form; record what was ticked even if false.
        for k in ("consent_email", "consent_mobile", "consent_whatsapp"):
            submitted[k] = bool(getattr(data, k))
        merged = {**(req.prefill or {}), **submitted}
        issues = validate_client(str(client.kind), merged)
        req.submitted_data = submitted
        req.submitted_at = datetime.now(UTC)
        req.submitted_ip = coarse_ip(ip)
        req.notice_version = data.notice_version or str(privacy_setting("CURRENT_PRIVACY_NOTICE_VERSION"))
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
