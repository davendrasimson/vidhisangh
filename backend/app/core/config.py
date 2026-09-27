"""Application configuration.

All settings are sourced from the environment (12-factor). Secrets are never
hard-coded; in production they are injected from a secrets manager. The
``VS_`` prefix namespaces every variable to avoid collisions.
"""

from __future__ import annotations

import secrets
from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import (
    Field,
    PostgresDsn,
    computed_field,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


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
    # (client KYC forms, portal invitations).
    PUBLIC_APP_URL: str = "https://vidhisangh.com"

    # ─── Database ───────────────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "vidhisangh"
    POSTGRES_PASSWORD: str = "vidhisangh"
    POSTGRES_DB: str = "vidhisangh"
    POSTGRES_POOL_SIZE: int = 10
    POSTGRES_MAX_OVERFLOW: int = 20
    DATABASE_URL: str | None = None  # optional explicit async DSN override

    # ─── Redis / Celery ─────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ─── Security / JWT ─────────────────────────────────────────────
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(64))
    JWT_ALGORITHM: Literal["HS256", "RS256", "ES256"] = "HS256"
    JWT_PRIVATE_KEY_PATH: str | None = None
    JWT_PUBLIC_KEY_PATH: str | None = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    # A refresh token presented again within this many seconds of being
    # rotated is a client race (two tabs booting, a reload mid-rotation), not
    # theft: it gets a fresh pair. Beyond it, reuse revokes every session.
    REFRESH_REUSE_GRACE_SECONDS: int = 60
    PASSWORD_MIN_LENGTH: int = 8
    MFA_ISSUER: str = "VidhiSangh"

    # ─── Rate limiting ──────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 120
    # Credential attempts (login, register, OAuth/passkey exchanges) per IP.
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10
    # Token refreshes per IP. A refresh token is an unguessable secret, so this
    # is not a brute-force guard — it only stops a runaway client. It must be
    # generous: a whole firm behind one NAT address shares it, and every hard
    # refresh of every tab spends one.
    REFRESH_RATE_LIMIT_PER_MINUTE: int = 120

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

    # ─── Notifications ──────────────────────────────────────────────
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str = "no-reply@vidhisangh.com"

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
        return self.async_database_url.replace(
            "postgresql+asyncpg", "postgresql+psycopg"
        )

    @field_validator("SECRET_KEY")
    @classmethod
    def _secret_strength(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("VS_SECRET_KEY must be at least 32 characters.")
        return v

    def assert_production_ready(self) -> None:
        """Fail fast on insecure defaults when running in production."""
        if not self.is_production:
            return
        problems: list[str] = []
        if self.DEBUG:
            problems.append("DEBUG must be false in production")
        if self.JWT_ALGORITHM == "HS256" and not self.JWT_PRIVATE_KEY_PATH:
            problems.append("Use an asymmetric JWT algorithm (RS256/ES256) in production")
        if "change-me" in self.POSTGRES_PASSWORD or self.POSTGRES_PASSWORD == "vidhisangh":
            problems.append("POSTGRES_PASSWORD is a default/placeholder value")
        if not self.cors_origins:
            problems.append("BACKEND_CORS_ORIGINS must be set explicitly in production")
        if problems:
            raise RuntimeError("Insecure production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
