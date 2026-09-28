"""Privacy service — the Data Principal's rights, exercised.

- ``UserPrivacyService``: export (s.11) and erasure (s.12) for a *user* of the
  platform (VidhiSangh is the Data Fiduciary).
- ``RightsRequestService`` + ``create_rights_request``: the register of
  access/correction/erasure/grievance requests a firm receives from its
  clients (the firm is the Fiduciary; VidhiSangh the Processor).
- ``export_tenant_zip``: the whole tenant as a zip of per-table JSON for
  offboarding (P-13).
- ``notice()``: the public notice facts (grievance officer, versions).
"""

from __future__ import annotations

import io
import json
import secrets
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.db.base_class import Base
from app.modules.apikeys.models import ApiKey
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import record_audit
from app.modules.clients.models import ClientKycRequest
from app.modules.documents.models import Document
from app.modules.drafting.models import Draft
from app.modules.identity.models import (
    MfaBackupCode,
    RefreshToken,
    Role,
    TrustedDevice,
    User,
    WebAuthnCredential,
    user_roles,
)
from app.modules.messaging.models import ConversationParticipant, Message
from app.modules.network.models import Comment, Connection, Follow, NetworkIdentity, Post, PostMention
from app.modules.notifications.models import Notification, NotificationPreference
from app.modules.privacy.config import privacy_setting
from app.modules.privacy.export import SECRET_COLUMNS, jsonable, row_dict
from app.modules.privacy.models import (
    ClientConsentEvent,
    PrivacyRequest,
    PrivacyRequestKind,
    PrivacyRequestSource,
    PrivacyRequestStatus,
)
from app.modules.privacy.schemas import PrivacyRequestCreate, PrivacyRequestUpdate
from app.modules.profile.models import Endorsement, ProfessionalProfile, Recommendation
from app.modules.tenancy.models import Tenant

log = structlog.get_logger("app.privacy")

DELETED_USER_NAME = "Deleted user"
OWNER_ROLE = "org_admin"

SUB_PROCESSORS: list[dict[str, str]] = [
    {"name": "SMTP e-mail provider", "purpose": "Transactional e-mail (KYC links, notifications)", "data": "Name, e-mail address, message"},
    {"name": "Slack (per-tenant webhook)", "purpose": "Firm-configured notifications", "data": "Notification text"},
    {"name": "Razorpay", "purpose": "Subscription and invoice payments", "data": "Name, e-mail, amount"},
    {"name": "Google / Microsoft / LinkedIn", "purpose": "Single sign-on, when you choose it", "data": "E-mail, name, subject id"},
    {"name": "Hosting (India, ap-south-1)", "purpose": "Servers, database and document storage", "data": "All platform data"},
]


def notice() -> dict:
    base = settings.PUBLIC_APP_URL.rstrip("/")
    return {
        "terms_version": str(privacy_setting("CURRENT_TERMS_VERSION")),
        "notice_version": str(privacy_setting("CURRENT_PRIVACY_NOTICE_VERSION")),
        "grievance_officer": {
            "name": str(privacy_setting("GRIEVANCE_OFFICER_NAME")),
            "email": str(privacy_setting("GRIEVANCE_OFFICER_EMAIL")),
            "address": str(privacy_setting("GRIEVANCE_OFFICER_ADDRESS")),
        },
        "notice_url": f"{base}/privacy",
        "terms_url": f"{base}/terms",
        "legal_hold_years": int(privacy_setting("LEGAL_HOLD_YEARS")),
        "tenant_erase_grace_days": int(privacy_setting("TENANT_ERASE_GRACE_DAYS")),
        "retention_days": {
            "notification_deliveries": int(privacy_setting("DATA_RETENTION_DAYS_DELIVERIES")),
            "notifications": int(privacy_setting("DATA_RETENTION_DAYS_NOTIFICATIONS")),
            "revoked_sessions": int(privacy_setting("DATA_RETENTION_DAYS_REVOKED_TOKENS")),
            "deleted_documents": int(privacy_setting("DATA_RETENTION_DAYS_DELETED_DOCUMENTS")),
            "deleted_drafts": int(privacy_setting("DATA_RETENTION_DAYS_DELETED_DRAFTS")),
            "oauth_states": int(privacy_setting("DATA_RETENTION_DAYS_OAUTH_STATES")),
        },
        "sub_processors": SUB_PROCESSORS,
    }


# ─── Users (VidhiSangh as Data Fiduciary) ───────────────────────────
class UserPrivacyService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id

    async def _user(self) -> User:
        user = await self.session.scalar(select(User).where(User.id == self.user_id, User.deleted_at.is_(None)))
        if user is None:
            raise NotFoundError("User not found.")
        return user

    async def _all(self, stmt):  # noqa: ANN001, ANN202
        return list((await self.session.execute(stmt)).scalars().all())

    async def export(self) -> dict:
        """Everything the platform holds *about* this user (not the firm's
        practice data, which belongs to the tenant's export)."""
        user = await self._user()
        uid = self.user_id
        profile = await self.session.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id == uid))
        endorsements = await self._all(select(Endorsement).where(Endorsement.endorser_user_id == uid))
        recommendations = await self._all(select(Recommendation).where(Recommendation.author_user_id == uid))
        sessions = await self._all(select(RefreshToken).where(RefreshToken.user_id == uid))
        notifications = await self._all(select(Notification).where(Notification.user_id == uid))
        prefs = await self._all(select(NotificationPreference).where(NotificationPreference.user_id == uid))
        audit = await self._all(select(AuditEvent).where(AuditEvent.actor_id == uid))
        identity = await self.session.scalar(select(NetworkIdentity).where(NetworkIdentity.user_id == uid))
        connections = await self._all(select(Connection).where((Connection.requester_id == uid) | (Connection.addressee_id == uid)))
        posts = await self._all(select(Post).where(Post.author_id == uid))
        comments = await self._all(select(Comment).where(Comment.author_id == uid))
        messages = await self._all(select(Message).where(Message.sender_id == uid))
        drafts = await self._all(select(Draft).where(Draft.created_by == uid, Draft.deleted_at.is_(None)))
        documents = await self._all(select(Document).where(Document.uploaded_by == uid, Document.deleted_at.is_(None)))
        kyc = await self._all(select(ClientKycRequest).where(ClientKycRequest.initiated_by == uid))
        consents = await self._all(select(ClientConsentEvent).where(ClientConsentEvent.actor_id == uid))
        passkeys = await self._all(select(WebAuthnCredential).where(WebAuthnCredential.user_id == uid))
        devices = await self._all(select(TrustedDevice).where(TrustedDevice.user_id == uid))
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "subject": "user",
            "user": {**row_dict(user), "roles": [r.code for r in user.roles]},
            "profile": row_dict(profile) if profile else None,
            "endorsements_given": [row_dict(e) for e in endorsements],
            "recommendations_written": [row_dict(r) for r in recommendations],
            "sessions": [
                row_dict(
                    s,
                    only=(
                        "id", "device_label", "device_id", "ip_address", "user_agent",
                        "created_at", "expires_at", "revoked_at",
                    ),
                )
                for s in sessions
            ],
            "passkeys": [row_dict(p, only=("id", "name", "created_at", "last_used_at")) for p in passkeys],
            "trusted_devices": [row_dict(d, only=("id", "label", "last_seen_at", "trusted_until")) for d in devices],
            "notifications": [row_dict(n) for n in notifications],
            "notification_preferences": [row_dict(p) for p in prefs],
            "audit_events_as_actor": [row_dict(a) for a in audit],
            "network_identity": row_dict(identity) if identity else None,
            "connections": [row_dict(c) for c in connections],
            "posts": [row_dict(p) for p in posts],
            "comments": [row_dict(c) for c in comments],
            "messages_sent": [row_dict(m) for m in messages],
            "drafts_authored": [row_dict(d, only=("id", "title", "status", "matter_id", "client_id", "word_count", "created_at", "updated_at")) for d in drafts],
            "documents_uploaded": [row_dict(d, only=("id", "name", "content_type", "size", "matter_id", "client_id", "created_at")) for d in documents],
            "kyc_requests_initiated": [row_dict(k, only=("id", "client_id", "status", "sent_to_email", "created_at", "applied_at")) for k in kyc],
            "consent_events_recorded": [row_dict(c) for c in consents],
        }

    async def _other_active_owner_exists(self, user: User) -> bool:
        rows = await self.session.execute(
            select(User.id).join(user_roles, user_roles.c.user_id == User.id).join(Role, Role.id == user_roles.c.role_id)
            .where(User.tenant_id == user.tenant_id, User.id != user.id, User.is_active.is_(True),
                   User.deleted_at.is_(None), Role.code == OWNER_ROLE)
            .limit(1)
        )
        return rows.first() is not None

    async def erase(self, *, password: str, actor_label: str | None) -> dict:
        """Anonymise the account and remove what identifies the person.

        Kept: audit-log rows (legal obligation — DPDP s.17(1)(a)), the firm's
        practice records the user authored (matters, documents, drafts: they
        are the firm's, not the user's), with author snapshots anonymised.
        """
        user = await self._user()
        if user.hashed_password and not security.verify_password(password, user.hashed_password):
            raise AuthenticationError("Password is incorrect.")
        is_owner = any(r.code == OWNER_ROLE for r in user.roles)
        if is_owner and not await self._other_active_owner_exists(user):
            raise ConflictError(
                "You are the only active administrator of this organisation. Make another user an "
                "org_admin first, or delete the organisation from Settings → Privacy & data."
            )
        uid = user.id
        now = datetime.now(UTC)
        anon_email = f"deleted+{uuid.uuid4()}@anonymised.invalid"

        # Sessions & credentials.
        tokens = await self._all(select(RefreshToken).where(RefreshToken.user_id == uid))
        for t in tokens:
            t.revoked_at = t.revoked_at or now
            t.ip_address = None
            t.user_agent = None
            t.device_label = None
            t.device_id = None
        keys = await self._all(select(ApiKey).where(ApiKey.created_by == uid, ApiKey.revoked.is_(False)))
        for k in keys:
            k.revoked = True
        await self.session.execute(delete(MfaBackupCode).where(MfaBackupCode.user_id == uid))
        await self.session.execute(delete(WebAuthnCredential).where(WebAuthnCredential.user_id == uid))
        await self.session.execute(delete(TrustedDevice).where(TrustedDevice.user_id == uid))

        # Professional identity: profile, endorsements given, recommendations written.
        profile = await self.session.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id == uid))
        if profile is not None:
            await self.session.execute(delete(Endorsement).where(Endorsement.profile_id == profile.id))
            await self.session.execute(delete(Recommendation).where(Recommendation.profile_id == profile.id))
            await self.session.delete(profile)
        await self.session.execute(delete(Endorsement).where(Endorsement.endorser_user_id == uid))
        await self.session.execute(delete(Recommendation).where(Recommendation.author_user_id == uid))

        # Network: identity, connections, follows; author snapshots anonymised.
        await self.session.execute(delete(NetworkIdentity).where(NetworkIdentity.user_id == uid))
        await self.session.execute(delete(Connection).where((Connection.requester_id == uid) | (Connection.addressee_id == uid)))
        await self.session.execute(delete(Follow).where((Follow.follower_id == uid) | (Follow.followee_id == uid)))
        anon = {"author_name": DELETED_USER_NAME, "author_avatar_url": None}
        await self.session.execute(update(Post).where(Post.author_id == uid).values(author_headline=None, **anon))
        await self.session.execute(update(Post).where(Post.shared_from_id.in_(select(Post.id).where(Post.author_id == uid)))
                                   .values(shared_author_name=DELETED_USER_NAME, shared_author_avatar_url=None))
        await self.session.execute(update(Comment).where(Comment.author_id == uid).values(**anon))
        await self.session.execute(update(PostMention).where(PostMention.mentioned_user_id == uid).values(mentioned_name=DELETED_USER_NAME))
        await self.session.execute(update(Message).where(Message.sender_id == uid).values(sender_name=DELETED_USER_NAME, sender_avatar_url=None))
        await self.session.execute(update(ConversationParticipant).where(ConversationParticipant.user_id == uid)
                                   .values(participant_name=DELETED_USER_NAME, participant_avatar_url=None))

        # Notifications addressed to the user.
        await self.session.execute(delete(Notification).where(Notification.user_id == uid))
        await self.session.execute(delete(NotificationPreference).where(NotificationPreference.user_id == uid))

        # The account row: anonymised, disabled, soft-deleted (kept as an FK target).
        user.email = anon_email
        user.full_name = DELETED_USER_NAME
        user.display_name = None
        user.phone = None
        user.avatar_url = None
        user.hashed_password = security.hash_password(secrets.token_urlsafe(32))
        user.mfa_enabled = False
        user.mfa_secret = None
        if hasattr(user, "mfa_pending_secret"):
            user.mfa_pending_secret = None
        user.is_active = False
        user.is_email_verified = False
        user.deleted_at = now
        user.roles = []

        record_audit(
            self.session, tenant_id=self.tenant_id, actor_id=uid, actor_label=actor_label,
            action="user.erased", entity_type="user", entity_id=str(uid),
            summary="User account erased at the user's request (DPDP s.12)",
            meta={"sessions_revoked": len(tokens), "api_keys_revoked": len(keys), "legal_basis_for_retained_audit": "s.17(1)(a) legal obligation"},
        )
        await self.session.flush()
        log.info("user_erased", user_id=str(uid))
        return {
            "user_id": uid, "erased": True, "anonymised_email": anon_email,
            "sessions_revoked": len(tokens), "api_keys_revoked": len(keys),
        }


# ─── Rights requests (the firm as Fiduciary for its clients) ─────────
def _due() -> datetime:
    return datetime.now(UTC) + timedelta(days=int(privacy_setting("PRIVACY_REQUEST_SLA_DAYS")))


async def create_rights_request(
    session: AsyncSession, matter_access, kind: PrivacyRequestKind | str, message: str
) -> PrivacyRequest:
    """For the client portal: a Data Principal raises a request through the
    portal link (``matter_access`` is the resolved ``PortalAccess``)."""
    req = PrivacyRequest(
        tenant_id=matter_access.tenant_id,
        kind=PrivacyRequestKind(kind),
        status=PrivacyRequestStatus.OPEN,
        source=PrivacyRequestSource.PORTAL,
        matter_id=matter_access.matter_id,
        subject_name=getattr(matter_access, "client_name", None),
        subject_email=getattr(matter_access, "client_email", None),
        message=message.strip(),
        due_at=_due(),
    )
    session.add(req)
    await session.flush()
    return req


class RightsRequestService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id

    async def list(self, *, status: PrivacyRequestStatus | None = None) -> list[PrivacyRequest]:
        stmt = select(PrivacyRequest).where(PrivacyRequest.tenant_id == self.tenant_id, PrivacyRequest.deleted_at.is_(None))
        if status is not None:
            stmt = stmt.where(PrivacyRequest.status == status)
        return list((await self.session.execute(stmt.order_by(PrivacyRequest.created_at.desc()))).scalars().all())

    async def get(self, request_id: uuid.UUID) -> PrivacyRequest:
        req = await self.session.scalar(
            select(PrivacyRequest).where(PrivacyRequest.id == request_id, PrivacyRequest.tenant_id == self.tenant_id)
        )
        if req is None:
            raise NotFoundError("Privacy request not found.")
        return req

    async def create(self, data: PrivacyRequestCreate, *, actor_label: str | None) -> PrivacyRequest:
        req = PrivacyRequest(
            tenant_id=self.tenant_id, kind=data.kind, status=PrivacyRequestStatus.OPEN,
            source=PrivacyRequestSource.STAFF, client_id=data.client_id, matter_id=data.matter_id,
            subject_name=data.subject_name, subject_email=data.subject_email,
            message=data.message.strip(), created_by=self.user_id, due_at=_due(),
        )
        self.session.add(req)
        await self.session.flush()
        record_audit(
            self.session, tenant_id=self.tenant_id, actor_id=self.user_id, actor_label=actor_label,
            action="privacy.request_created", entity_type="privacy_request", entity_id=str(req.id),
            summary=f"{str(req.kind).title()} request recorded", meta={"client_id": str(data.client_id) if data.client_id else None},
        )
        await self.session.refresh(req)
        return req

    async def update(self, request_id: uuid.UUID, data: PrivacyRequestUpdate, *, actor_label: str | None) -> PrivacyRequest:
        req = await self.get(request_id)
        req.status = data.status
        if data.resolution_note is not None:
            req.resolution_note = data.resolution_note
        if data.status in (PrivacyRequestStatus.RESOLVED, PrivacyRequestStatus.REJECTED):
            req.resolved_at = datetime.now(UTC)
            req.resolved_by = self.user_id
        else:
            req.resolved_at = None
            req.resolved_by = None
        record_audit(
            self.session, tenant_id=self.tenant_id, actor_id=self.user_id, actor_label=actor_label,
            action="privacy.request_updated", entity_type="privacy_request", entity_id=str(req.id),
            summary=f"{str(req.kind).title()} request marked {req.status}",
        )
        await self.session.flush()
        await self.session.refresh(req)
        return req


# ─── Tenant export (offboarding) ─────────────────────────────────────
async def export_tenant_zip(session: AsyncSession, tenant_id: uuid.UUID) -> bytes:
    """A zip with one ``<table>.json`` per tenant-scoped table (secrets and
    blind indexes excluded), plus ``tenant.json`` and a manifest."""
    tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        raise NotFoundError("Tenant not found.")
    buf = io.BytesIO()
    manifest: dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("tenant.json", json.dumps(row_dict(tenant), indent=2))
        for table in Base.metadata.sorted_tables:
            if "tenant_id" not in table.c or table.name == "tenants":
                continue
            cols = [c for c in table.c if c.name not in SECRET_COLUMNS]
            rows = (await session.execute(select(*cols).where(table.c.tenant_id == tenant_id))).mappings().all()
            data = [{k: jsonable(v) for k, v in dict(r).items()} for r in rows]
            manifest[table.name] = len(data)
            zf.writestr(f"{table.name}.json", json.dumps(data, indent=2))
        zf.writestr("manifest.json", json.dumps({
            "generated_at": datetime.now(UTC).isoformat(), "tenant_id": str(tenant_id),
            "slug": tenant.slug, "tables": manifest,
            "note": "Secrets (password hashes, token hashes, MFA secrets, blind indexes) are excluded.",
        }, indent=2))
    return buf.getvalue()
