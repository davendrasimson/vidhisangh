# VidhiSangh — Security & Privacy

Security is a design constraint, not a feature. This document maps the required
controls to their implementation status. **✅ implemented in Phase 1**,
**🟡 partially / scaffolded**, **⬜ roadmap**.

## Compliance targets
OWASP Top 10 (latest) · OWASP ASVS L2 · SOC 2 Type II controls · GDPR-ready ·
DPDP Act (India)-ready · Principle of Least Privilege · Zero-Trust.

## Authentication & authorization

| Control | Status | Notes |
|---------|:------:|-------|
| Argon2id password hashing | ✅ | OWASP params (64 MiB, t=3, p=2); auto-rehash on policy change. |
| Short-lived JWT access tokens | ✅ | 15 min default; tenant-scoped (`tid` claim). |
| Rotating refresh tokens + reuse detection | ✅ | Opaque, hashed at rest; rotation lineage revokes all sessions on reuse. |
| Account lockout / anti-brute-force | ✅ | Lock after 5 failures; uniform errors + dummy-hash to close timing channels. |
| MFA (TOTP) + hashed backup codes | ✅ | Enrolment, enable, verify; secret encrypted at rest. |
| RBAC (roles → permissions) | ✅ | Data-driven catalog; `require_permission()` route guards. |
| ABAC (resource-level, e.g. own-records) | 🟡 | Hooks defined; per-module policies as modules land. |
| OAuth2 / OIDC social login, OTP, passkeys, biometric | ⬜ | Config placeholders present; providers roadmap. |
| Device & concurrent-session management | 🟡 | `trusted_devices` + per-token device context; UI/roadmap. |

## Transport & storage encryption

| Control | Status | Notes |
|---------|:------:|-------|
| TLS 1.3 in transit | 🟡 | Terminated at NGINX edge (`infra/nginx`); HSTS in prod. |
| Column-level encryption for PII/secrets | ✅ | `EncryptedString` (Fernet) — e.g. MFA secrets. |
| Envelope encryption via KMS/HSM | 🟡 | `crypto._load_key()` is the single swap-point for AWS/Azure/GCP KMS or Vault. |
| Encrypted object storage | 🟡 | S3/MinIO SSE configured at bucket level (infra). |
| Key rotation | 🟡 | Key indirection in place; rotation policy roadmap. |

## Secrets management
✅ No secrets in source — all config via `VS_`-prefixed env vars (`app/core/config.py`).
`assert_production_ready()` fails fast on insecure defaults (DEBUG on, HS256 in
prod, placeholder DB password, empty CORS). 🟡 Cloud secrets-manager wiring
(AWS SM / Azure Key Vault / GCP SM / Vault) is a deployment concern with hooks ready.

## Application security

| Control | Status | Notes |
|---------|:------:|-------|
| Input validation | ✅ | Pydantic v2 on every request; password policy: ≥ 8 characters (`VS_PASSWORD_MIN_LENGTH`, lowered from 12 on 2026-09-27 at the user's request) with upper- and lower-case, a digit and a symbol. |
| SQL-injection prevention | ✅ | Parameterised queries via SQLAlchemy; no string SQL in services. |
| Output encoding / XSS | ✅ | Angular auto-escaping; JSON API; strict API CSP. |
| Security headers (CSP, HSTS, XFO, nosniff, Referrer/Permissions-Policy) | ✅ | `SecurityHeadersMiddleware` + edge NGINX. |
| CORS allow-list | ✅ | Explicit origins; wildcard rejected in prod. |
| Rate limiting / throttling | ✅ | Redis fixed-window; stricter on auth routes; fails open on cache outage. |
| CSRF | ✅ | Bearer-token (not cookie) auth avoids CSRF; SameSite guidance for any cookie use. |
| API versioning | ✅ | `/api/v1` prefix. |
| SSRF mitigation / secure file upload + AV scan / idempotency | ⬜ | Roadmap with the document & integration modules. |

## Multi-tenant isolation
✅ PostgreSQL **row-level security** (`FORCE`) enforces `tenant_id` scoping in the
database, not just the app. The `app.bypass_rls` escape hatch is confined to the
auth service and migrations and is code-reviewed. Access tokens are tenant-bound.
Verified by `tests/test_rls_postgres.py`, which proves the policies enforce
isolation at the DB level (and that `app.bypass_rls` exposes all rows) — it runs
against a real Postgres and is skipped when one is unavailable.

> ⚠️ **Deployment requirement:** the application **must** connect to Postgres as a
> **non-superuser role without `BYPASSRLS`**. PostgreSQL always bypasses RLS for
> superusers and `BYPASSRLS` roles, so a superuser connection (as used in local
> dev, `POSTGRES_USER=postgres`) silently disables all tenant isolation at the DB
> layer, leaving only app-level scoping. Provision a dedicated least-privilege
> application role in every non-local environment.
>
> **How (go-live checklist):**
> 1. Provision the role as a Postgres admin (idempotent, safe to re-run):
>    ```
>    python -m app.scripts.provision_db_role --role vidhisangh_app --password "$VS_APP_DB_PASSWORD"
>    ```
>    It creates `vidhisangh_app` as `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`
>    and grants only `SELECT/INSERT/UPDATE/DELETE` on tables + `USAGE/SELECT` on
>    sequences (no DDL), plus `ALTER DEFAULT PRIVILEGES` so future migrations' tables
>    stay covered. Use `--dry-run` to preview the exact SQL.
> 2. Point the **application** at it: `VS_POSTGRES_USER=vidhisangh_app`,
>    `VS_POSTGRES_PASSWORD=…`.
> 3. Keep running **migrations** as the owning/admin role (the app role has no DDL
>    rights) — e.g. a separate admin DSN for Alembic. Pass that role to
>    `--migrator` so default privileges are attributed correctly.
>
> Verified by `tests/test_rls_app_role.py`, which provisions the role with these
> exact grants and asserts DB-enforced isolation (read + `WITH CHECK` write),
> default-deny with no tenant context, and no DDL — and that the role is neither
> superuser nor `BYPASSRLS`. Runs against real Postgres; skipped when unavailable.

## Audit & monitoring

| Control | Status | Notes |
|---------|:------:|-------|
| Structured, correlatable logs (request-id + tenant) | ✅ | structlog; JSON in prod. |
| Immutable audit log of security events | ⬜ | `audit` module reserved; `audit:read` permission defined. |
| Metrics / health probes | ✅ | `/metrics`, `/health`, `/ready`. |
| Centralised aggregation, anomaly detection, alerting | ⬜ | Deployment/observability roadmap. |

## Privacy (GDPR / DPDP)

| Control | Status |
|---------|:------:|
| Data classification & retention schedules | ⬜ (soft-delete + `deleted_at` groundwork ✅) |
| Consent management | 🟡 (registration terms acceptance ✅) |
| Right to export / delete / anonymise | ⬜ |
| Data-residency routing | 🟡 (`Tenant.region` present) |

## Secure SDLC (CI/CD)
CI (`.github/workflows/ci.yml`, `codeql.yml`) runs: Ruff lint/format, mypy strict,
pytest with coverage, `npm build`, dependency/SCA scan, CodeQL SAST, and container
build. Mandatory code review via branch protection (repo policy).

## Backups & DR
⬜ Automated encrypted backups, PITR, RTO/RPO targets and HA are deployment
concerns; the stateless app + externalised state (Postgres/Redis/S3) make
standard managed-service backup + multi-AZ HA straightforward.

## Reporting
Security issues: security@vidhisangh.com (set up a coordinated-disclosure policy
and `SECURITY.md` at the repo root before public launch).
