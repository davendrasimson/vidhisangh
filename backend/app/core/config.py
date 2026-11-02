"""Application configuration.

All settings are sourced from the environment (12-factor). Secrets are never
hard-coded; in production they are injected from a secrets manager. The
``VS_`` prefix namespaces every variable to avoid collisions.

Secret material (2026-09 hardening, audit A-7):

- ``SECRET_KEY`` is **required** (no default) and is the root secret.
- ``REFRESH_TOKEN_PEPPER``, ``BACKUP_CODE_PEPPER``, ``LINK_TOKEN_PEPPER`` and
  ``FIELD_ENCRYPTION_KEYS`` are separate secrets. Each **defaults to a value
  derived from ``SECRET_KEY``** so an existing deployment keeps working
  (existing refresh-token / backup-code hashes and encrypted columns stay
  valid); set them explicitly in production and ``assert_production_ready``
  logs a warning while they are derived.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import (
    PostgresDsn,
    computed_field,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

_log = logging.getLogger("app.config")


class Environment(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


def _derive(secret: str, label: str) -> str:
    """Deterministic, label-separated sub-key of ``secret`` (sha256-HKDF style)."""
    return hashlib.sha256(f"vidhisangh:{label}:{secret}".encode()).hexdigest()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ─── Runtime ────────────────────────────────────────────────────
    ENVIRONMENT: Environment = Environment.LOCAL
    DEBUG: bool = False
    PROJECT_NAME: str = "VidhiSangh"
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    # Comma-separated in env; exposed as a parsed list via `cors_origins`.
    BACKEND_CORS_ORIGINS: str = ""
    # Where the SPA is served — used to build links sent outside the app
    # (client KYC forms, portal invitations, password-reset / invite emails).
    PUBLIC_APP_URL: str = "https://vidhisangh.com"
    # Serve /docs, /redoc and openapi.json even in production (default: off there).
    EXPOSE_API_DOCS: bool = False
    # When set, /metrics requires ``Authorization: Bearer <METRICS_TOKEN>``.
    METRICS_TOKEN: str | None = None

    # ─── Database ───────────────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "vidhisangh"
    POSTGRES_PASSWORD: str = "vidhisangh"  # noqa: S105 - development default; rejected in prod
    POSTGRES_DB: str = "vidhisangh"
    POSTGRES_POOL_SIZE: int = 10
    POSTGRES_MAX_OVERFLOW: int = 20
    DATABASE_URL: str | None = None  # optional explicit async DSN override
    # Refuse to boot in production when the DB role is SUPERUSER or BYPASSRLS
    # (either silently disables row-level security). Only ever disable for a
    # one-off maintenance run.
    DB_ROLE_CHECK: bool = True

    # ─── Redis / Celery ─────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ─── Security / JWT ─────────────────────────────────────────────
    # REQUIRED. Root secret (>= 32 chars). Never has a default.
    SECRET_KEY: str
    # Separate secrets, each derived from SECRET_KEY unless set explicitly.
    REFRESH_TOKEN_PEPPER: str | None = None
    BACKUP_CODE_PEPPER: str | None = None
    LINK_TOKEN_PEPPER: str | None = None  # portal / KYC / reset / invite tokens
    BLIND_INDEX_PEPPER: str | None = None  # HMAC pepper for searchable encrypted columns
    # Comma-separated Fernet keys, NEWEST FIRST. Ciphertext is prefixed with a
    # key id so keys can be rotated by prepending a new one.
    FIELD_ENCRYPTION_KEYS: str | None = None
    JWT_ALGORITHM: Literal["HS256", "RS256", "ES256"] = "HS256"
    JWT_PRIVATE_KEY_PATH: str | None = None
    JWT_PUBLIC_KEY_PATH: str | None = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    # A refresh token presented again within this many seconds of being
    # rotated is a client race (two tabs booting, a reload mid-rotation), not
    # theft: it gets a fresh pair. Beyond it, reuse revokes every session.
    REFRESH_REUSE_GRACE_SECONDS: int = 60
    # The phone app (X-VidhiSangh-Client: app): stay signed in until sign-out.
    # Sliding: every refresh starts a new period. A rotated token presented
    # again from the same app (its reply was lost on a weak network) is a
    # retry, not theft, for this long.
    REFRESH_TOKEN_EXPIRE_DAYS_APP: int = 365
    REFRESH_REUSE_GRACE_SECONDS_APP: int = 7 * 86400
    # The HttpOnly cookie is always set. Browser sessions keep refresh tokens
    # exclusively there; body delivery may be enabled only for a separately
    # reviewed non-browser client.
    REFRESH_TOKEN_IN_BODY: bool = False
    REFRESH_COOKIE_NAME: str = "vs_refresh"
    PASSWORD_MIN_LENGTH: int = 8
    MFA_ISSUER: str = "VidhiSangh"
    LOGIN_MAX_FAILED_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    INVITE_TOKEN_EXPIRE_DAYS: int = 7
    # 30 days (owner, 2 Nov 2026; was 48 hours): advocates open the mail days later.
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 720
    # Admin "add user" returns a temporary password in the API response only
    # when this is on; the default hands off via an invitation link instead.
    INVITES_RETURN_TEMP_PASSWORD: bool = False
    # Client-portal links expire this many days after they are issued.
    PORTAL_ACCESS_EXPIRE_DAYS: int = 90
    # Opaque WebSocket tickets (Redis-backed) live this long.
    WS_TICKET_TTL_SECONDS: int = 60
    # Redirect URIs accepted for OAuth authorize (origins). PUBLIC_APP_URL and
    # the CORS origins are always allowed; add extra origins here (comma-separated).
    OAUTH_ALLOWED_REDIRECT_ORIGINS: str = ""
    # The built-in mock IdP is a full sign-in bypass: opt in explicitly, never in
    # production (refused at start-up).
    OAUTH_MOCK_ENABLED: bool = False
    # "Continue with Google" for someone without an account creates one from
    # the provider's verified email (an individual account). Off = sign-in only.
    OAUTH_SIGNUP_ENABLED: bool = True

    # ─── Rate limiting ──────────────────────────────────────────────
    # Master switch (tests turn it off; never off in production).
    RATE_LIMITING_ENABLED: bool = True
    # Reverse proxies whose X-Forwarded-For we trust (IPs or CIDRs, comma-separated).
    TRUSTED_PROXY_IPS: str = "127.0.0.1,::1"
    RATE_LIMIT_PER_MINUTE: int = 120
    # Credential attempts (login, register, OAuth/passkey exchanges) per IP.
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10
    # Credential attempts per account (lower-cased email), regardless of IP.
    AUTH_ACCOUNT_RATE_LIMIT_PER_MINUTE: int = 10
    # New-organisation sign-ups per IP (also throttles email enumeration via 409).
    REGISTER_RATE_LIMIT_PER_MINUTE: int = 5
    # Token refreshes per IP. A refresh token is an unguessable secret, so this
    # is not a brute-force guard — it only stops a runaway client. It must be
    # generous: a whole firm behind one NAT address shares it, and every hard
    # refresh of every tab spends one.
    REFRESH_RATE_LIMIT_PER_MINUTE: int = 120
    MFA_RATE_LIMIT_PER_MINUTE: int = 10
    # Public token-authenticated routes (KYC form, client portal) per IP.
    PUBLIC_TOKEN_RATE_LIMIT_PER_MINUTE: int = 30
    LINK_PREVIEW_RATE_LIMIT_PER_MINUTE: int = 20
    UPLOAD_RATE_LIMIT_PER_MINUTE: int = 30
    WS_HANDSHAKE_RATE_LIMIT_PER_MINUTE: int = 30

    # Legal news ingestion. JSON array of {name, url, category}; intentionally
    # empty by default so production never fetches an unreviewed source.
    NEWS_FEEDS: str = "[]"

    # ─── Object storage ─────────────────────────────────────────────
    S3_ENDPOINT_URL: str | None = None
    S3_REGION: str = "ap-south-1"
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None
    S3_BUCKET: str = "vidhisangh-documents"
    S3_USE_SSL: bool = True

    # ─── Search ─────────────────────────────────────────────────────
    OPENSEARCH_URL: str = "http://localhost:9200"

    # ─── AI / LLM ───────────────────────────────────────────────────
    LLM_PROVIDER: Literal["anthropic", "openai", "azure_openai", "local"] = "anthropic"
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None
    LOCAL_LLM_BASE_URL: str | None = None
    VECTOR_DB_URL: str | None = None

    # ─── Notifications (SMTP) ───────────────────────────────────────
    REGISTRATION_ALERT_EMAIL: str = "ds@simsononline.com"
    REGISTRATION_REQUIRE_VERIFICATION: bool = True
    WA_PHONE_NUMBER_ID: str = ""
    WA_ACCESS_TOKEN: str = ""
    WA_ACCESS_TOKEN_FILE: str = ""
    WA_API_VERSION: str = "v25.0"
    # VidhiSangh's own number (+91 73411 00692) and its approved authentication
    # template; see phone_otp.send_whatsapp_code for the parameter names.
    WA_OTP_TEMPLATE: str = "vidhisangh_otp"
    WA_OTP_TEMPLATE_LANG: str = "en_US"
    WA_OTP_TEMPLATE_PARAMS: str = "code"
    WA_OTP_CALL_NUMBER: str = "+917341100692"
    WA_OTP_CONTACT: str = "+917341100692"
    # Evening WhatsApp list of tomorrow's hearings (utility template; members
    # opt in under Settings → Notifications). Empty disables the job.
    # Firebase service-account key for push notifications (systemd credential
    # in production). Empty: no push is sent.
    FCM_CREDENTIALS_FILE: str = ""
    WA_REMINDER_TEMPLATE: str = "hearing_reminder"
    WA_REMINDER_TEMPLATE_LANG: str = "en"
    # Morning digest of matters needing attention (matter board flags). Empty:
    # no WhatsApp template approved yet, so the digest goes by push only.
    WA_BOARD_DIGEST_TEMPLATE: str = ""
    WA_BOARD_DIGEST_TEMPLATE_LANG: str = "en"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    # Prefer a systemd credential path in production so the password remains
    # encrypted at rest instead of being written to the environment file.
    SMTP_PASSWORD_FILE: str | None = None
    SMTP_FROM: str = "no-reply@vidhisangh.com"
    SMTP_TLS: bool = True  # STARTTLS; only ever false against a local relay
    SMTP_SSL: bool = False  # implicit TLS, normally port 465

    # Daily official-order retrieval and opted-in digest. Headnotes use the
    # established external export/import workflow; no model API is called.
    SC_DAILY_ENABLED: bool = False

    # ─── Outreach (invitation emails to non-members) ────────────────
    # A separate mail service on its own sub-domain (news.vidhisangh.com), so
    # complaints about invitations never touch the deliverability of sign-up
    # and verification mail sent through SMTP_* above. Unset = nothing is sent.
    OUTREACH_SMTP_HOST: str | None = None
    OUTREACH_SMTP_PORT: int = 587
    OUTREACH_SMTP_USER: str | None = None
    OUTREACH_SMTP_PASSWORD: str | None = None
    OUTREACH_SMTP_PASSWORD_FILE: str | None = None
    OUTREACH_FROM: str = "VidhiSangh <invite@news.vidhisangh.com>"
    OUTREACH_REPLY_TO: str = "grievance@vidhisangh.com"
    # Hard ceiling; the admin can lower it, never raise it above this.
    OUTREACH_DAILY_LIMIT: int = 500  # ceiling; 50 → 100 (31 Oct 2026) → 500 (2 Nov 2026, owner: pace rises as the domain warms)
    # Who the email says it is from (footer); the owner chose not to name the company.
    OUTREACH_SENDER_LINE: str = "Sent by VidhiSangh, India"
    # The relay (Brevo) posts delivery/bounce/complaint events to
    # POST /api/v1/outreach/events/<this secret>. Unset = the route answers 404.
    OUTREACH_WEBHOOK_SECRET: str | None = None

    @property
    def outreach_smtp_password(self) -> str:
        if self.OUTREACH_SMTP_PASSWORD:
            return self.OUTREACH_SMTP_PASSWORD
        if not self.OUTREACH_SMTP_PASSWORD_FILE:
            return ""
        return Path(self.OUTREACH_SMTP_PASSWORD_FILE).read_text(encoding="utf-8").strip()

    @property
    def smtp_password(self) -> str:
        if self.SMTP_PASSWORD:
            return self.SMTP_PASSWORD
        if not self.SMTP_PASSWORD_FILE:
            return ""
        try:
            password = Path(self.SMTP_PASSWORD_FILE).read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as exc:
            raise RuntimeError("SMTP password credential is unavailable") from exc
        if not password:
            raise RuntimeError("SMTP password credential is empty")
        return password

    # ─── WebAuthn / passkeys ────────────────────────────────────────
    WEBAUTHN_RP_ID: str = "localhost"
    WEBAUTHN_RP_NAME: str = "VidhiSangh"
    WEBAUTHN_ORIGIN: str = "http://localhost:4200"

    # ─── Object storage & uploads (audit A-13, A-22) ────────────────
    STORAGE_BACKEND: Literal["local", "s3", "memory"] = "local"
    STORAGE_DIR: str | None = None  # required when local; never a temp dir
    MAX_UPLOAD_BYTES: int = 26_214_400  # 25 MiB (nginx client_max_body_size must match)
    ALLOWED_UPLOAD_TYPES: str = ""  # comma list of MIME types/extensions; empty = built-in set
    MALWARE_SCAN_REQUIRED: bool = False
    CLAMAV_SOCKET: str = "/run/clamav/clamd.ctl"
    S3_KMS_KEY_ID: str | None = None  # SSE-KMS when set, else SSE-S3 (AES256)

    # ─── Database hardening (audit A-29) ────────────────────────────
    DB_SSL_MODE: Literal["disable", "require", "verify-ca", "verify-full"] | None = (
        None  # None = derive from host
    )
    DB_SSL_ROOT_CERT: str | None = None
    DB_STATEMENT_TIMEOUT_MS: int = 30_000
    DB_IDLE_IN_TRANSACTION_TIMEOUT_MS: int = 60_000

    # ─── Privacy / DPDP (audit P-1, P-4, P-13, P-14) ────────────────
    CURRENT_TERMS_VERSION: str = "2026-09-27"
    CURRENT_PRIVACY_NOTICE_VERSION: str = "2026-10-25"
    GRIEVANCE_OFFICER_NAME: str = "Salil Shaida"
    GRIEVANCE_OFFICER_EMAIL: str = "grievance@vidhisangh.com"
    GRIEVANCE_OFFICER_ADDRESS: str = "VidhiSangh, India"
    LEGAL_HOLD_YEARS: int = 8  # matters: Limitation Act / Advocates Act practice
    TENANT_ERASE_GRACE_DAYS: int = 30
    PRIVACY_REQUEST_SLA_DAYS: int = 30
    DATA_RETENTION_DAYS_DELIVERIES: int = 90
    DATA_RETENTION_DAYS_NOTIFICATIONS: int = 365
    DATA_RETENTION_DAYS_REVOKED_TOKENS: int = 30
    DATA_RETENTION_DAYS_DELETED_DOCUMENTS: int = 30
    DATA_RETENTION_DAYS_DELETED_DRAFTS: int = 30
    DATA_RETENTION_DAYS_OAUTH_STATES: int = 1

    # ─── Derived ────────────────────────────────────────────────────
    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == Environment.PRODUCTION

    @computed_field  # type: ignore[prop-decorator]
    @property
    def async_database_url(self) -> str:
        """Async (asyncpg) DSN used by the application at runtime."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_HOST,
                port=self.POSTGRES_PORT,
                path=self.POSTGRES_DB,
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        """Sync (psycopg) DSN used by Alembic migrations."""
        return self.async_database_url.replace("postgresql+asyncpg", "postgresql+psycopg")

    # ── Secret material (explicit value, else derived from SECRET_KEY) ──
    @property
    def refresh_token_pepper(self) -> str:
        # Identity-derivation on purpose: existing refresh-token hashes were
        # computed with SECRET_KEY itself, so the default keeps every current
        # session valid. Setting VS_REFRESH_TOKEN_PEPPER signs everyone out once.
        return self.REFRESH_TOKEN_PEPPER or self.SECRET_KEY

    @property
    def backup_code_pepper(self) -> str:
        # Same reasoning: existing backup codes were hashed with SECRET_KEY.
        return self.BACKUP_CODE_PEPPER or self.SECRET_KEY

    @property
    def link_token_pepper(self) -> str:
        # New in 2026-09 (tokens were stored in clear before): a fresh label.
        return self.LINK_TOKEN_PEPPER or _derive(self.SECRET_KEY, "link-token")

    @property
    def field_encryption_keys(self) -> list[str]:
        """Fernet keys, newest first (explicit or the legacy SECRET_KEY-derived one)."""
        if self.FIELD_ENCRYPTION_KEYS:
            return [k.strip() for k in self.FIELD_ENCRYPTION_KEYS.split(",") if k.strip()]
        return []

    @property
    def derived_secrets_in_use(self) -> list[str]:
        """Names of secret settings still falling back to SECRET_KEY derivation."""
        out = []
        if not self.REFRESH_TOKEN_PEPPER:
            out.append("VS_REFRESH_TOKEN_PEPPER")
        if not self.BACKUP_CODE_PEPPER:
            out.append("VS_BACKUP_CODE_PEPPER")
        if not self.LINK_TOKEN_PEPPER:
            out.append("VS_LINK_TOKEN_PEPPER")
        if not self.FIELD_ENCRYPTION_KEYS:
            out.append("VS_FIELD_ENCRYPTION_KEYS")
        if not self.BLIND_INDEX_PEPPER:
            out.append("VS_BLIND_INDEX_PEPPER")
        return out

    @property
    def trusted_proxies(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        nets = []
        for raw in self.TRUSTED_PROXY_IPS.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                nets.append(ipaddress.ip_network(raw, strict=False))
            except ValueError:
                _log.warning("Ignoring invalid VS_TRUSTED_PROXY_IPS entry %r", raw)
        return nets

    @property
    def cookie_secure(self) -> bool:
        """Refresh cookie carries ``Secure`` everywhere except plain local dev."""
        return self.ENVIRONMENT != Environment.LOCAL

    @property
    def oauth_allowed_redirect_origins(self) -> set[str]:
        origins = {self.PUBLIC_APP_URL.rstrip("/"), *self.cors_origins}
        origins.update(
            o.strip().rstrip("/")
            for o in self.OAUTH_ALLOWED_REDIRECT_ORIGINS.split(",")
            if o.strip()
        )
        return {o for o in origins if o}

    @field_validator("SECRET_KEY")
    @classmethod
    def _secret_strength(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("VS_SECRET_KEY must be at least 32 characters.")
        return v

    @field_validator(
        "REFRESH_TOKEN_PEPPER", "BACKUP_CODE_PEPPER", "LINK_TOKEN_PEPPER", "BLIND_INDEX_PEPPER"
    )
    @classmethod
    def _pepper_strength(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 32:
            raise ValueError("Peppers must be at least 32 characters when set.")
        return v

    def assert_production_ready(self) -> None:
        """Fail fast on insecure defaults when running in production.

        Hard failures raise; softer gaps (derived sub-keys) are logged so the
        operator sees them without an outage.
        """
        if self.OAUTH_MOCK_ENABLED and self.is_production:
            raise RuntimeError(
                "Insecure production configuration: VS_OAUTH_MOCK_ENABLED must be false "
                "in production (the mock IdP is a sign-in bypass)."
            )
        if not self.is_production:
            return
        problems: list[str] = []
        if self.DEBUG:
            problems.append("DEBUG must be false in production")
        if self.JWT_ALGORITHM == "HS256":
            problems.append("Use an asymmetric JWT algorithm (RS256/ES256) in production")
        if not self.JWT_PRIVATE_KEY_PATH or not self.JWT_PUBLIC_KEY_PATH:
            problems.append("VS_JWT_PRIVATE_KEY_PATH and VS_JWT_PUBLIC_KEY_PATH must be set")
        if (
            "change-me" in self.POSTGRES_PASSWORD or self.POSTGRES_PASSWORD == "vidhisangh"  # noqa: S105 - placeholder comparison
        ):
            problems.append("POSTGRES_PASSWORD is a default/placeholder value")
        if not self.cors_origins:
            problems.append("BACKEND_CORS_ORIGINS must be set explicitly in production")
        if not self.RATE_LIMITING_ENABLED:
            problems.append("RATE_LIMITING_ENABLED must be true in production")
        if not self.DB_ROLE_CHECK:
            problems.append("DB_ROLE_CHECK must be true in production")
        if problems:
            raise RuntimeError("Insecure production configuration: " + "; ".join(problems))
        derived = self.derived_secrets_in_use
        if derived:
            _log.warning(
                "Secrets derived from VS_SECRET_KEY instead of set explicitly: %s. "
                "Set them in the production environment (see docs/DEPLOYMENT.md).",
                ", ".join(derived),
            )
        if not self.METRICS_TOKEN:
            _log.warning("VS_METRICS_TOKEN is not set: /metrics relies on the edge proxy alone.")


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()  # type: ignore[call-arg]  # SECRET_KEY comes from the environment


settings = get_settings()
