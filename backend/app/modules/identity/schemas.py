"""Pydantic v2 schemas for the identity module (API contracts)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.config import settings

_PASSWORD_RULES = (
    "Password must be at least "
    f"{settings.PASSWORD_MIN_LENGTH} characters and include upper- and "
    "lower-case letters, a digit, and a symbol."
)


def _validate_password_strength(value: str) -> str:
    if len(value) < settings.PASSWORD_MIN_LENGTH:
        raise ValueError(_PASSWORD_RULES)
    checks = [
        re.search(r"[a-z]", value),
        re.search(r"[A-Z]", value),
        re.search(r"\d", value),
        re.search(r"[^\w\s]", value),
    ]
    if not all(checks):
        raise ValueError(_PASSWORD_RULES)
    return value


# ─── Registration & login ───────────────────────────────────────────
class RegisterRequest(BaseModel):
    """Sign up: provisions a new tenant and its owner (org_admin) user."""

    organisation_name: str = Field(min_length=2, max_length=200)
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=settings.PASSWORD_MIN_LENGTH, max_length=128)
    accept_terms: bool = Field(description="Must be true to register.")

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


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_slug: str | None = Field(
        default=None, description="Optional when the email is unique platform-wide."
    )
    mfa_code: str | None = Field(default=None, description="6-digit TOTP or backup code.")
    device_label: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None
    all_devices: bool = False


# ─── Tokens ─────────────────────────────────────────────────────────
class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds.")


class MfaRequiredResponse(BaseModel):
    mfa_required: bool = True
    detail: str = "Multi-factor authentication code required."


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
    email: EmailStr
    full_name: str
    display_name: str | None
    avatar_url: str | None
    is_active: bool
    is_email_verified: bool
    is_superuser: bool
    mfa_enabled: bool
    last_login_at: datetime | None
    roles: list[RoleRead] = []


class UserCreatedRead(BaseModel):
    """Returned once when an admin adds a user — carries the temporary password
    to hand off out-of-band (until an email-invite flow is wired)."""

    user: UserRead
    temporary_password: str


class CurrentUser(BaseModel):
    """Lightweight authenticated principal derived from the access token."""

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    email: str
    is_superuser: bool
    scopes: list[str] = []
    session_id: uuid.UUID | None = None  # the refresh-token/session this token belongs to

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


class MfaEnableResponse(BaseModel):
    mfa_enabled: bool
    backup_codes: list[str] = Field(description="Shown once — store securely.")


# ─── Password change ────────────────────────────────────────────────
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=settings.PASSWORD_MIN_LENGTH, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _validate_password_strength(v)
