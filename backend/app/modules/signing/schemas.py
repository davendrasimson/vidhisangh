"""API schemas for document e-signatures."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.modules.signing.models import EnvelopeStatus, SignatureStepStatus, SignerKind


class SignerInput(BaseModel):
    kind: SignerKind
    user_id: uuid.UUID | None = None
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    designation: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def internal_user_required(self) -> SignerInput:
        if self.kind == SignerKind.INTERNAL and self.user_id is None:
            raise ValueError("Select an internal user.")
        if self.kind == SignerKind.EXTERNAL:
            self.user_id = None
        return self


class EnvelopeCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    message: str = Field(default="", max_length=3000)
    sequential: bool = True
    signers: list[SignerInput] = Field(min_length=1, max_length=10)

    @field_validator("signers")
    @classmethod
    def distinct_signers(cls, value: list[SignerInput]) -> list[SignerInput]:
        keys = [(str(item.user_id) if item.user_id else item.email.lower()) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("Each signer may appear only once.")
        return value


class SignatureStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    step_order: int
    signer_kind: SignerKind
    signer_user_id: uuid.UUID | None
    signer_name: str
    signer_email: EmailStr
    designation: str | None
    status: SignatureStepStatus
    signed_at: datetime | None
    rejected_at: datetime | None
    signed_name: str | None
    remarks: str | None


class SignatureEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: str
    actor_label: str | None
    detail: dict
    created_at: datetime


class EnvelopeRead(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    source_version_id: uuid.UUID
    source_checksum: str
    title: str
    message: str
    status: EnvelopeStatus
    sequential: bool
    created_by: uuid.UUID
    sent_at: datetime
    completed_at: datetime | None
    final_checksum: str | None
    steps: list[SignatureStepRead]
    events: list[SignatureEventRead] = Field(default_factory=list)


class SignatureSubmit(BaseModel):
    signed_name: str = Field(min_length=2, max_length=200)
    designation: str | None = Field(default=None, max_length=200)
    signature_data: str = Field(min_length=20, max_length=500_000)
    remarks: str | None = Field(default=None, max_length=2000)
    consent: bool

    @field_validator("signature_data")
    @classmethod
    def valid_signature(cls, value: str) -> str:
        if not value.startswith("data:image/png;base64,"):
            raise ValueError("Signature must be a PNG drawing.")
        return value

    @field_validator("consent")
    @classmethod
    def consent_required(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Signing consent is required.")
        return value


class RejectSubmit(BaseModel):
    remarks: str = Field(min_length=3, max_length=2000)


class PublicStepRead(BaseModel):
    document_title: str
    sender_message: str
    signer_name: str
    designation: str | None
    status: SignatureStepStatus
    expires_at: datetime | None
    requires_otp: bool = True


class OtpSubmit(BaseModel):
    otp: str = Field(pattern=r"^\d{6}$")


class SigningSessionRead(BaseModel):
    session_token: str
    expires_at: datetime
