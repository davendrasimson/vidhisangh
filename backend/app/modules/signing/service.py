"""Secure sequential internal/external document signing."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.channels import ChannelMessage, get_channels
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.core.storage import Storage
from app.modules.audit.service import record_audit
from app.modules.documents.repository import DocumentRepository
from app.modules.identity.repository import UserRepository
from app.modules.notifications.models import NotificationChannel, NotificationType
from app.modules.notifications.service import create_notification
from app.modules.signing.certificate import append_certificate, certificate_pdf
from app.modules.signing.models import (
    EnvelopeStatus,
    SignatureEnvelope,
    SignatureEvent,
    SignatureStep,
    SignatureStepStatus,
    SignerKind,
)
from app.modules.signing.repository import SigningRepository
from app.modules.signing.schemas import EnvelopeCreate, EnvelopeRead, SignatureSubmit

CONSENT = "I reviewed this document and consent to apply my electronic signature to it."


class SigningService:
    def __init__(
        self,
        session: AsyncSession,
        storage: Storage,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> None:
        self.session, self.storage, self.tenant_id, self.user_id = (
            session,
            storage,
            tenant_id,
            user_id,
        )
        self.repo = SigningRepository(session)
        self.documents = DocumentRepository(session)

    async def prepare(
        self, document_id: uuid.UUID, data: EnvelopeCreate
    ) -> tuple[SignatureEnvelope, list[tuple[SignatureStep, str]]]:
        if self.user_id is None:
            raise PermissionDeniedError("Sign in required.")
        document = await self.documents.get_document(self.tenant_id, document_id)
        if document is None or document.current_version_id is None:
            raise NotFoundError("Document not found.")
        if await self.repo.active_for_document(self.tenant_id, document_id):
            raise ConflictError("This document already has an active signature request.")
        version = await self.documents.get_version(self.tenant_id, document.current_version_id)
        if version is None:
            raise NotFoundError("Document version not found.")
        now = datetime.now(UTC)
        envelope = SignatureEnvelope(
            tenant_id=self.tenant_id,
            document_id=document.id,
            source_version_id=version.id,
            source_checksum=version.checksum,
            title=data.title,
            message=data.message,
            sequential=data.sequential,
            created_by=self.user_id,
            sent_at=now,
        )
        self.session.add(envelope)
        await self.session.flush()
        users = UserRepository(self.session)
        for index, signer in enumerate(data.signers, start=1):
            name, email, user_id = signer.name, str(signer.email).lower(), signer.user_id
            if signer.kind == SignerKind.INTERNAL:
                user = await users.get_for_tenant(self.tenant_id, signer.user_id)
                if user is None or not user.is_active:
                    raise ValidationError("An internal signer is unavailable.")
                name, email, user_id = user.full_name, user.email, user.id
            status = (
                SignatureStepStatus.PENDING
                if (not data.sequential or index == 1)
                else SignatureStepStatus.WAITING
            )
            self.session.add(
                SignatureStep(
                    tenant_id=self.tenant_id,
                    envelope_id=envelope.id,
                    step_order=index,
                    signer_kind=signer.kind,
                    signer_user_id=user_id,
                    signer_name=name,
                    signer_email=email,
                    designation=signer.designation,
                    status=status,
                )
            )
        await self.session.flush()
        await self.session.refresh(envelope, ["steps", "events"])
        self._event(
            envelope,
            "sent",
            "Signature request created",
            actor_user_id=self.user_id,
            detail={"signers": len(envelope.steps), "source_checksum": version.checksum},
        )
        notifications = await self._activate(envelope)
        record_audit(
            self.session,
            tenant_id=self.tenant_id,
            actor_id=self.user_id,
            action="document.signature_sent",
            summary=f"Sent {document.name} to {len(envelope.steps)} signer(s)",
            entity_type="signature_envelope",
            entity_id=str(envelope.id),
            meta={"document_id": str(document.id), "source_checksum": version.checksum},
        )
        return envelope, notifications

    async def list(self) -> list[SignatureEnvelope]:
        if self.user_id is None:
            return []
        return await self.repo.list(self.tenant_id, self.user_id)

    async def get(self, envelope_id: uuid.UUID) -> SignatureEnvelope:
        envelope = await self.repo.get(self.tenant_id, envelope_id)
        if envelope is None:
            raise NotFoundError("Signature request not found.")
        if self.user_id not in {envelope.created_by, *(s.signer_user_id for s in envelope.steps)}:
            raise PermissionDeniedError("You cannot view this signature request.")
        return envelope

    async def to_read(self, envelope: SignatureEnvelope) -> EnvelopeRead:
        document = await self.documents.get_document(self.tenant_id, envelope.document_id)
        return EnvelopeRead(
            id=envelope.id,
            document_id=envelope.document_id,
            document_name=document.name if document else "Document",
            source_version_id=envelope.source_version_id,
            source_checksum=envelope.source_checksum,
            title=envelope.title,
            message=envelope.message,
            status=envelope.status,
            sequential=envelope.sequential,
            created_by=envelope.created_by,
            sent_at=envelope.sent_at,
            completed_at=envelope.completed_at,
            final_checksum=envelope.final_checksum,
            steps=envelope.steps,
            events=envelope.events,
        )

    async def internal_sign(
        self, step_id: uuid.UUID, data: SignatureSubmit, ip: str | None, user_agent: str | None
    ) -> SignatureEnvelope:
        step = await self.repo.step(self.tenant_id, step_id)
        if step is None:
            raise NotFoundError("Signature step not found.")
        if step.signer_kind != SignerKind.INTERNAL or step.signer_user_id != self.user_id:
            raise PermissionDeniedError("This signature is assigned to another person.")
        return await self._sign(step, data, ip, user_agent)

    async def internal_reject(
        self, step_id: uuid.UUID, remarks: str, ip: str | None
    ) -> SignatureEnvelope:
        step = await self.repo.step(self.tenant_id, step_id)
        if step is None:
            raise NotFoundError("Signature step not found.")
        if step.signer_kind != SignerKind.INTERNAL or step.signer_user_id != self.user_id:
            raise PermissionDeniedError("This signature is assigned to another person.")
        return await self._reject(step, remarks, ip)

    async def public_step(self, raw_token: str) -> SignatureStep:
        step = await self.repo.public_step(security.hash_link_token(raw_token))
        if step is None or step.signer_kind != SignerKind.EXTERNAL:
            raise NotFoundError("Signing link is invalid.")
        if step.token_expires_at and step.token_expires_at < datetime.now(UTC):
            raise ValidationError("Signing link has expired.")
        return step

    async def send_otp(self, raw_token: str) -> None:
        step = await self.public_step(raw_token)
        self._require_pending(step)
        otp = security.generate_numeric_otp()
        step.otp_hash = security.hash_link_token(f"{step.id}:{otp}")
        step.otp_expires_at = datetime.now(UTC) + timedelta(minutes=10)
        step.otp_attempts = 0
        await self._email(
            step.signer_email,
            step.signer_name,
            "Your VidhiSangh signing code",
            f"Your one-time code is {otp}. It expires in 10 minutes. Do not share this code.",
            None,
        )
        self._event(
            step.envelope,
            "otp_sent",
            "OTP sent to external signer",
            step=step,
            actor_label=step.signer_name,
        )

    async def verify_otp(self, raw_token: str, otp: str) -> tuple[str, datetime]:
        step = await self.public_step(raw_token)
        self._require_pending(step)
        now = datetime.now(UTC)
        if not step.otp_hash or not step.otp_expires_at or step.otp_expires_at < now:
            raise ValidationError("Request a fresh signing code.")
        if step.otp_attempts >= 5:
            raise PermissionDeniedError("Too many attempts. Request a fresh code.")
        step.otp_attempts += 1
        if not security.constant_time_compare(
            step.otp_hash, security.hash_link_token(f"{step.id}:{otp}")
        ):
            raise PermissionDeniedError("The signing code is incorrect.")
        raw_session = security.generate_url_safe_token(32)
        expires = now + timedelta(minutes=30)
        step.session_hash = security.hash_link_token(raw_session)
        step.session_expires_at = expires
        step.otp_hash = None
        step.otp_expires_at = None
        self._event(
            step.envelope,
            "identity_verified",
            "External signer verified by email OTP",
            step=step,
            actor_label=step.signer_name,
        )
        return raw_session, expires

    async def public_document(self, raw_token: str, session_token: str) -> tuple[str, str, bytes]:
        step = await self.public_step(raw_token)
        self._verify_session(step, session_token)
        document = await self.documents.get_document(step.tenant_id, step.envelope.document_id)
        version = await self.documents.get_version(step.tenant_id, step.envelope.source_version_id)
        if document is None or version is None:
            raise NotFoundError("Document is unavailable.")
        return document.name, version.content_type, await self.storage.get(version.storage_key)

    async def public_sign(
        self,
        raw_token: str,
        session_token: str,
        data: SignatureSubmit,
        ip: str | None,
        user_agent: str | None,
    ) -> SignatureEnvelope:
        step = await self.public_step(raw_token)
        self._verify_session(step, session_token)
        return await self._sign(step, data, ip, user_agent)

    async def public_reject(
        self, raw_token: str, session_token: str, remarks: str, ip: str | None
    ) -> SignatureEnvelope:
        step = await self.public_step(raw_token)
        self._verify_session(step, session_token)
        return await self._reject(step, remarks, ip)

    async def cancel(self, envelope_id: uuid.UUID) -> SignatureEnvelope:
        envelope = await self.get(envelope_id)
        if envelope.created_by != self.user_id:
            raise PermissionDeniedError("Only the sender can cancel this request.")
        if envelope.status != EnvelopeStatus.PENDING:
            raise ConflictError("Only a pending request can be cancelled.")
        envelope.status = EnvelopeStatus.CANCELLED
        envelope.cancelled_at = datetime.now(UTC)
        for step in envelope.steps:
            if step.status in (SignatureStepStatus.PENDING, SignatureStepStatus.WAITING):
                step.status = SignatureStepStatus.CANCELLED
        self._event(
            envelope, "cancelled", "Signature request cancelled", actor_user_id=self.user_id
        )
        return envelope

    async def download(
        self, envelope_id: uuid.UUID, certificate: bool = False
    ) -> tuple[str, str, bytes]:
        envelope = await self.get(envelope_id)
        document = await self.documents.get_document(self.tenant_id, envelope.document_id)
        if document is None:
            raise NotFoundError("Document not found.")
        if certificate:
            if not envelope.certificate_storage_key:
                raise ConflictError("The audit certificate is available after completion.")
            return (
                f"{document.name}-signature-certificate.pdf",
                "application/pdf",
                await self.storage.get(envelope.certificate_storage_key),
            )
        key = envelope.final_storage_key
        if envelope.status != EnvelopeStatus.COMPLETED or not key:
            raise ConflictError("The signed copy is available after every signer has signed.")
        if envelope.final_content_type == "application/pdf":
            base = document.name.rsplit(".", 1)[0]
            filename = f"{base}.signed.pdf"
        else:
            filename = f"Signed-{document.name}"
        return (
            filename,
            envelope.final_content_type or document.content_type,
            await self.storage.get(key),
        )

    async def source_download(self, envelope_id: uuid.UUID) -> tuple[str, str, bytes]:
        envelope = await self.get(envelope_id)
        document = await self.documents.get_document(self.tenant_id, envelope.document_id)
        version = await self.documents.get_version(self.tenant_id, envelope.source_version_id)
        if document is None or version is None:
            raise NotFoundError("The frozen document version is unavailable.")
        return document.name, version.content_type, await self.storage.get(version.storage_key)

    async def _sign(
        self, step: SignatureStep, data: SignatureSubmit, ip: str | None, user_agent: str | None
    ) -> SignatureEnvelope:
        self._require_pending(step)
        step.status = SignatureStepStatus.SIGNED
        step.signed_at = datetime.now(UTC)
        step.signed_name = data.signed_name
        step.designation = data.designation or step.designation
        step.signature_data = data.signature_data
        step.consent_text = CONSENT
        step.remarks = data.remarks
        step.ip_address = ip
        step.user_agent = (user_agent or "")[:500]
        self._event(
            step.envelope,
            "signed",
            f"Step {step.step_order} signed",
            step=step,
            actor_user_id=step.signer_user_id,
            actor_label=step.signer_name,
            ip=ip,
        )
        remaining = [
            s
            for s in step.envelope.steps
            if s.status in (SignatureStepStatus.WAITING, SignatureStepStatus.PENDING)
        ]
        if remaining:
            if step.envelope.sequential:
                await self._activate(step.envelope)
        else:
            await self._complete(step.envelope)
        return step.envelope

    async def _reject(self, step: SignatureStep, remarks: str, ip: str | None) -> SignatureEnvelope:
        self._require_pending(step)
        now = datetime.now(UTC)
        step.status = SignatureStepStatus.REJECTED
        step.rejected_at = now
        step.remarks = remarks
        step.ip_address = ip
        step.envelope.status = EnvelopeStatus.REJECTED
        step.envelope.rejected_at = now
        for other in step.envelope.steps:
            if other.status in (SignatureStepStatus.PENDING, SignatureStepStatus.WAITING):
                other.status = SignatureStepStatus.CANCELLED
        self._event(
            step.envelope,
            "rejected",
            f"Step {step.step_order} rejected",
            step=step,
            actor_user_id=step.signer_user_id,
            actor_label=step.signer_name,
            ip=ip,
            detail={"remarks": remarks},
        )
        return step.envelope

    async def _activate(self, envelope: SignatureEnvelope) -> list[tuple[SignatureStep, str]]:
        active = [s for s in envelope.steps if s.status == SignatureStepStatus.PENDING]
        if not active:
            waiting = sorted(
                (s for s in envelope.steps if s.status == SignatureStepStatus.WAITING),
                key=lambda s: s.step_order,
            )
            if waiting:
                waiting[0].status = SignatureStepStatus.PENDING
                active = [waiting[0]]
        sent: list[tuple[SignatureStep, str]] = []
        for step in active:
            if step.signer_kind == SignerKind.EXTERNAL and step.token_hash is None:
                raw = security.generate_url_safe_token(32)
                step.token_hash = security.hash_link_token(raw)
                step.token_expires_at = datetime.now(UTC) + timedelta(days=30)
                sent.append((step, raw))
                await self._email(
                    step.signer_email,
                    step.signer_name,
                    f"Signature requested: {envelope.title}",
                    envelope.message or "A document is awaiting your electronic signature.",
                    f"{settings.PUBLIC_APP_URL.rstrip('/')}/esign/{raw}",
                )
            elif step.signer_user_id:
                await create_notification(
                    self.session,
                    user_id=step.signer_user_id,
                    type=NotificationType.DOCUMENT_SIGNATURE,
                    message=f"{envelope.title} is awaiting your signature.",
                    actor_id=envelope.created_by,
                    link="/app/documents?view=signatures",
                )
        return sent

    async def _complete(self, envelope: SignatureEnvelope) -> None:
        now = datetime.now(UTC)
        envelope.status = EnvelopeStatus.COMPLETED
        envelope.completed_at = now
        document = await self.documents.get_document(envelope.tenant_id, envelope.document_id)
        version = await self.documents.get_version(envelope.tenant_id, envelope.source_version_id)
        if document is None or version is None:
            raise NotFoundError("Source document is unavailable.")
        source = await self.storage.get(version.storage_key)
        lines = [
            f"Document: {document.name}",
            f"Envelope: {envelope.id}",
            f"Source SHA-256: {envelope.source_checksum}",
            f"Completed (UTC): {now.isoformat()}",
            "",
        ]
        for step in envelope.steps:
            sig_hash = hashlib.sha256((step.signature_data or "").encode()).hexdigest()
            lines.extend(
                [
                    f"Step {step.step_order}: "
                    f"{step.signed_name or step.signer_name} ({step.signer_email})",
                    f"Signed (UTC): {step.signed_at.isoformat() if step.signed_at else '-'}",
                    f"Signature evidence SHA-256: {sig_hash}",
                    "",
                ]
            )
        certificate = certificate_pdf(lines)
        final = (
            append_certificate(source, certificate)
            if version.content_type == "application/pdf"
            else source
        )
        final_type = version.content_type
        final_key = f"{envelope.tenant_id}/signatures/{envelope.id}/signed"
        cert_key = f"{envelope.tenant_id}/signatures/{envelope.id}/certificate.pdf"
        await self.storage.put(final_key, final, final_type)
        await self.storage.put(cert_key, certificate, "application/pdf")
        envelope.final_storage_key = final_key
        envelope.final_content_type = final_type
        envelope.final_checksum = hashlib.sha256(final).hexdigest()
        envelope.certificate_storage_key = cert_key
        self._event(
            envelope,
            "completed",
            "All signatures collected and final copy sealed",
            detail={"final_checksum": envelope.final_checksum},
        )
        record_audit(
            self.session,
            tenant_id=envelope.tenant_id,
            actor_id=self.user_id,
            action="document.signature_completed",
            summary=f"Completed signatures for {document.name}",
            entity_type="signature_envelope",
            entity_id=str(envelope.id),
            meta={
                "source_checksum": envelope.source_checksum,
                "final_checksum": envelope.final_checksum,
            },
        )

    def _require_pending(self, step: SignatureStep) -> None:
        if (
            step.envelope.status != EnvelopeStatus.PENDING
            or step.status != SignatureStepStatus.PENDING
        ):
            raise ConflictError("This signature step is not currently available.")
        if step.envelope.sequential and any(
            s.step_order < step.step_order and s.status != SignatureStepStatus.SIGNED
            for s in step.envelope.steps
        ):
            raise ConflictError("An earlier signer must complete their step first.")

    def _verify_session(self, step: SignatureStep, raw: str) -> None:
        if (
            not step.session_hash
            or not step.session_expires_at
            or step.session_expires_at < datetime.now(UTC)
            or not security.constant_time_compare(step.session_hash, security.hash_link_token(raw))
        ):
            raise PermissionDeniedError("Verify your email code before reviewing or signing.")

    def _event(
        self,
        envelope: SignatureEnvelope,
        event_type: str,
        description: str,
        *,
        step: SignatureStep | None = None,
        actor_user_id: uuid.UUID | None = None,
        actor_label: str | None = None,
        ip: str | None = None,
        detail: dict | None = None,
    ) -> None:
        event = SignatureEvent(
            tenant_id=envelope.tenant_id,
            envelope_id=envelope.id,
            step_id=step.id if step else None,
            event_type=event_type,
            actor_user_id=actor_user_id,
            actor_label=actor_label,
            ip_address=ip,
            detail={"description": description, **(detail or {})},
        )
        event.envelope = envelope
        self.session.add(event)

    async def _email(
        self, email: str, name: str, subject: str, body: str, link: str | None
    ) -> None:
        provider = get_channels().provider_for(NotificationChannel.EMAIL)
        if provider:
            await provider.send(
                ChannelMessage(to_email=email, to_name=name, subject=subject, body=body, link=link)
            )
