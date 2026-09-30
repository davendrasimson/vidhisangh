"""Pydantic v2 schemas for the identity module (API contracts)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.config import settings
from app.core.password_policy import RULES_MESSAGE as _PASSWORD_RULES  # noqa: F401 - re-export
from app.core.password_policy import validate_password


def _validate_password_strength(value: str) -> str:
    return validate_password(value)


# ─── Registration & login ───────────────────────────────────────────
class RegisterRequest(BaseModel):
    """Sign up: provisions a new tenant and its owner (org_admin) user."""

    organisation_name: str | None = Field(default=None, min_length=2, max_length=200)
    practice_type: Literal["individual", "firm"] | None = None
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr | None = None
    phone: str | None = None
    phone_challenge_id: uuid.UUID | None = None
    phone_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    password: str = Field(min_length=settings.PASSWORD_MIN_LENGTH, max_length=128)
    accept_terms: bool = Field(description="Must be true to register.")
    add_sample_data: bool = False
    device_id: str | None = Field(default=None, min_length=16, max_length=64)

    @field_validator("email", "phone", mode="before")
    @classmethod
    def _empty_contact(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        from app.modules.identity.phone_otp import normalize_phone
        return normalize_phone(value) if value else None

    @field_validator("full_name", "organisation_name", mode="before")
    @classmethod
    def _trim_names(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _practice(self) -> RegisterRequest:
        if not self.email and not self.phone:
            raise ValueError("Enter an email address or a mobile number.")
        if self.phone and (not self.phone_challenge_id or not self.phone_code):
            raise ValueError("Verify your mobile number with the WhatsApp code.")
        if self.practice_type == "individual":
            self.organisation_name = self.full_name
        elif self.organisation_name is None:
            raise ValueError("Enter your firm or chamber name.")
        return self

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _validate_password_strength(v)

    @field_validator("accept_terms")
    @classmethod
    def _terms(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must accept the terms of service.")
        return v


class TermsAcceptanceRequest(BaseModel):
    """Explicit acceptance of the currently published Terms and Privacy Notice."""

    accept_terms: bool

    @field_validator("accept_terms")
    @classmethod
    def _accepted(cls, value: bool) -> bool:
        if not value:
            raise ValueError("You must accept the current terms to continue.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)
    tenant_slug: str | None = Field(
        default=None, description="Optional when the email is unique platform-wide."
    )
    mfa_code: str | None = Field(
        default=None, max_length=16, description="6-digit TOTP or backup code."
    )
    device_label: str | None = Field(default=None, max_length=200)
    device_id: str | None = Field(default=None, min_length=16, max_length=64)


class RefreshRequest(BaseModel):
    # Optional: the token normally arrives in the HttpOnly cookie. The body is
    # still accepted for clients that stored it themselves (transition period).
    refresh_token: str | None = Field(default=None, max_length=256)
    device_id: str | None = Field(default=None, min_length=16, max_length=64)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=256)
    all_devices: bool = False


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(min_length=settings.PASSWORD_MIN_LENGTH, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _validate_password_strength(v)


# ─── Tokens ─────────────────────────────────────────────────────────
class TokenPair(BaseModel):
    access_token: str
    # ``None`` once REFRESH_TOKEN_IN_BODY is off: the refresh token then travels
    # only in the HttpOnly cookie scoped to /auth.
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds.")
    password_must_change: bool = Field(
        default=False,
        description="True when the session may only call /auth/change-password.",
    )


class MfaRequiredResponse(BaseModel):
    mfa_required: bool = True
    detail: str = "Multi-factor authentication code required."


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in: int


# ─── Read models ────────────────────────────────────────────────────
class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    module: str


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    is_system: bool


class RoleAssignment(BaseModel):
    role_codes: list[str] = Field(min_length=1, max_length=20)


class AdminUserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    role_codes: list[str] = Field(min_length=1, max_length=20)


class OAuthProviderRead(BaseModel):
    name: str
    display_name: str


class OAuthAuthorizeRequest(BaseModel):
    redirect_uri: str = Field(min_length=1, max_length=500)
    login_hint: EmailStr | None = None


class OAuthAuthorizeResponse(BaseModel):
    authorize_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=1, max_length=128)


class PasskeyRegisterFinish(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    response: dict


class PasskeyAuthBegin(BaseModel):
    email: EmailStr


class PasskeyAuthFinish(BaseModel):
    response: dict


class PasskeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    credential_id: str
    last_used_at: datetime | None
    created_at: datetime


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: EmailStr | None
    phone: str | None = None
    is_phone_verified: bool = False
    full_name: str
    display_name: str | None
    avatar_url: str | None
    is_active: bool
    is_email_verified: bool
    is_superuser: bool
    mfa_enabled: bool
    password_must_change: bool = False
    last_login_at: datetime | None
    # Privacy agent: accepted Terms/Notice version (frontend may re-prompt when
    # it differs from GET /privacy/notice `terms_version`).
    terms_version: str | None = None
    terms_accepted_at: datetime | None = None
    roles: list[RoleRead] = []
    # Transient, never serialised: ``UserAdminService.create_user`` attaches the
    # invitation link to the ORM instance and ``UserCreatedRead`` lifts it out.
    invitation_url: str | None = Field(default=None, exclude=True)


class UserCreatedRead(BaseModel):
    """Returned once when an admin adds a user. Carries the invitation link the
    admin can forward (also emailed when SMTP is configured) and — only when
    ``INVITES_RETURN_TEMP_PASSWORD`` is on — a temporary password."""

    user: UserRead
    temporary_password: str | None = None
    invitation_url: str | None = None

    @model_validator(mode="after")
    def _lift_invitation(self) -> UserCreatedRead:
        if self.invitation_url is None and self.user.invitation_url:
            self.invitation_url = self.user.invitation_url
        return self


class CurrentUser(BaseModel):
    """Lightweight authenticated principal derived from the access token."""

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    email: str
    is_superuser: bool
    scopes: list[str] = []
    session_id: uuid.UUID | None = None  # the refresh-token/session this token belongs to
    token_epoch: int = 0  # ``ep`` claim — see app.core.revocation
    password_must_change: bool = False  # ``pmc`` claim — change-password-only session

    def has_permission(self, code: str) -> bool:
        return self.is_superuser or "*" in self.scopes or code in self.scopes


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    device_label: str | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    expires_at: datetime
    is_current: bool = False


# ─── MFA ────────────────────────────────────────────────────────────
class MfaEnrollResponse(BaseModel):
    secret: str
    otpauth_uri: str = Field(description="Provisioning URI for authenticator apps / QR.")


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class MfaDisableRequest(BaseModel):
    """Disabling the second factor needs both factors again (audit A-18)."""

    password: str = Field(max_length=128)
    code: str = Field(min_length=6, max_length=8, description="Current TOTP or a backup code.")


class MfaEnableResponse(BaseModel):
    mfa_enabled: bool
    backup_codes: list[str] = Field(description="Shown once — store securely.")


# ─── Password change ────────────────────────────────────────────────
class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=settings.PASSWORD_MIN_LENGTH, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _validate_password_strength(v)


class RegistrationPending(BaseModel):
    verification_required: bool = True
    detail: str = "Check your email and open the verification link before signing in."


class PhoneOtpRequest(BaseModel):
    phone: str
    purpose: Literal["register", "login"]

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        from app.modules.identity.phone_otp import normalize_phone
        return normalize_phone(value)


class PhoneOtpResponse(BaseModel):
    challenge_id: uuid.UUID
    expires_in: int = 300
    detail: str = "If this number is eligible, a code has been sent on WhatsApp."


class PhoneLoginRequest(BaseModel):
    challenge_id: uuid.UUID
    code: str = Field(pattern=r"^\d{6}$")
    mfa_code: str | None = Field(default=None, max_length=16)
    device_id: str | None = Field(default=None, min_length=16, max_length=64)
